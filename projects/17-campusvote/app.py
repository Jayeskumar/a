"""CampusVote HTTP server (Python standard library only).

    python app.py                      # http://127.0.0.1:8017/
    python app.py --host 0.0.0.0       # let phones on the same Wi-Fi vote
    python app.py --fresh-keys         # generate new (non-demo) RSA keys on first run
"""

import argparse
import json
import mimetypes
import os
import re
import socket
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from campusvote import attacks, config, demo, security
from campusvote.election import ElectionService
from campusvote.util import Conflict, Forbidden, NotFound, ValidationError, atomic_write_json

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")

SERVICE = None
SERVER_INFO = {"host": "127.0.0.1", "port": config.DEFAULT_PORT, "lan_ip": "127.0.0.1"}


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "CampusVote/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Deliberately no client IP: the server must not be able to link a ballot to a device.
        sys.stderr.write("  %s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def log_request(self, code="-", size="-"):
        path = urlparse(self.path).path
        if path.startswith("/api/") and self.command in ("GET", "HEAD") and path in (
                "/api/stats", "/api/health", "/api/election"):
            return  # dashboard polling would flood the console
        self.log_message('"%s %s" %s', self.command, path, code)

    # -- helpers ---------------------------------------------------------
    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, msg):
        self._send(status, {"error": msg, "status": status})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValidationError("bad Content-Length")
        if n < 0 or n > config.MAX_BODY_BYTES:
            raise ValidationError("request body too large")
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("body must be valid JSON")
        if not isinstance(data, dict):
            raise ValidationError("body must be a JSON object")
        return data

    def _admin(self, body=None):
        SERVICE.check_admin(self.headers.get("X-Admin-Key") or (body or {}).get("admin_key"))

    # -- dispatch --------------------------------------------------------
    def do_HEAD(self):
        self._dispatch("GET")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _not_allowed(self):
        self._error(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = _not_allowed

    def _dispatch(self, method):
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                return self._api(method, url.path, parse_qs(url.query))
            if method != "GET":
                return self._error(405, "method not allowed")
            return self._static(url.path)
        except ValidationError as exc:
            self._error(400, str(exc))
        except Forbidden as exc:
            self._error(403, str(exc))
        except NotFound as exc:
            self._error(404, str(exc))
        except Conflict as exc:
            self._error(409, str(exc))
        except Exception:  # never crash the server
            traceback.print_exc()
            self._error(500, "internal error")

    def _api(self, method, path, qs):
        S = SERVICE
        if method == "GET":
            if path == "/api/health":
                return self._send(200, {"ok": True, "service": "campusvote", "phase": S.phase})
            if path == "/api/info":
                info = {"product": config.PRODUCT, "tagline": config.TAGLINE, "protocol": config.PROTOCOL,
                        "port": SERVER_INFO["port"], "lan": SERVER_INFO["host"] == "0.0.0.0",
                        "vote_url": "http://%s:%d/#vote" % (SERVER_INFO["lan_ip"] if SERVER_INFO["host"] == "0.0.0.0"
                                                          else SERVER_INFO["host"], SERVER_INFO["port"]),
                        "demo_admin_key": config.ADMIN_KEY if S.state.get("demo") and
                        config.ADMIN_KEY == "ksrce-admin-2026" else None}
                return self._send(200, info)
            if path == "/api/election":
                return self._send(200, S.election_info())
            if path == "/api/stats":
                return self._send(200, S.stats())
            if path == "/api/board":
                with S.lock:
                    try:
                        S.flush_if_due()
                    except Conflict:
                        pass
                    data = S.stored_board_bytes()  # what is on disk - exactly what an auditor gets
                extra = {"Content-Disposition": 'attachment; filename="board-%s.json"' % (S.eid or "empty")} \
                    if qs.get("download") else None
                return self._send(200, data, extra=extra)
            if path == "/api/board/verify":
                return self._send(200, S.verify())
            if path == "/api/results":
                return self._send(200, S.results())
            m = re.match(r"^/api/receipt/([0-9a-fA-F]{16,64})$", path)
            if m:
                return self._send(200, S.receipt(m.group(1)))
            if path == "/api/link":
                seq = qs.get("seq", [""])[0]
                return self._send(200, S.linkability(int(seq) if seq.isdigit() else None))
            if path == "/api/security":
                return self._send(200, {"threats": security.THREATS, "limits": security.LIMITS,
                                        "attacks": sorted(attacks.ATTACKS)})
            if path == "/api/demo/voter":
                return self._send(200, S.demo_voter())
            if path == "/api/sample/roster.csv":
                p = os.path.join(DATA, "sample_roster.csv")
                if not os.path.exists(p):
                    raise NotFound("sample roster not generated yet")
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "text/csv; charset=utf-8")
            return self._error(404, "unknown endpoint")
        if method != "POST":
            return self._error(405, "method not allowed")
        body = self._body()
        if path == "/api/login":
            return self._send(200, S.login(body.get("reg_no"), body.get("code")))
        if path == "/api/issue":
            return self._send(200, S.issue(body.get("session"), body.get("blinded")))
        if path == "/api/ballot":
            return self._send(202, S.cast(body))
        if path.startswith("/api/admin/") or path.startswith("/api/demo/") or path.startswith("/api/attack/"):
            self._admin(body)
        if path == "/api/admin/election":
            posts = body.get("posts")
            return self._send(201, S.create_election(body.get("title"), posts, body.get("opens"), body.get("closes")))
        if path == "/api/admin/roster":
            return self._send(201, S.upload_roster(body.get("csv")))
        if path == "/api/admin/phase":
            return self._send(200, S.set_phase(str(body.get("phase", ""))))
        if path == "/api/admin/simulate":
            try:
                n = int(body.get("count", 10))
            except (TypeError, ValueError):
                raise ValidationError("count must be an integer")
            return self._send(200, S.simulate(n))
        if path == "/api/admin/flush":
            with S.lock:
                return self._send(200, {"posted": S.flush_pool(force=True)})
        if path == "/api/admin/unlock":
            return self._send(200, S.unlock(body.get("reg_no")))
        if path == "/api/demo/reset":
            return self._send(200, demo.build_demo(S))
        if path == "/api/attack/restore":
            return self._send(200, S.restore())
        m = re.match(r"^/api/attack/([a-z_]{3,30})$", path)
        if m:
            return self._send(200, attacks.run(S, m.group(1)))
        return self._error(404, "unknown endpoint")

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def make_service(fresh_keys=False):
    os.makedirs(DATA, exist_ok=True)
    kp = os.path.join(DATA, "keys.json")
    if not os.path.exists(kp):
        if fresh_keys:
            print("  generating fresh 2048-bit RSA keys (Miller-Rabin, pure Python)...")
            keys = None  # ElectionService generates and stores them with secrets
        else:
            print("  generating deterministic DEMO keys (seed %d)..." % config.DEMO_SEED)
            keys = demo.demo_keys()
            out = {k: v.private_dict() for k, v in keys.items()}
            out["_note"] = "DEMO KEYS (deterministic, seed %d) - never use for a real election." % config.DEMO_SEED
            atomic_write_json(kp, out)
    svc = ElectionService(DATA)
    if not svc.manifest:
        print("  building the demo election (200 students, 152 ballots)...")
        demo.build_demo(svc)
    return svc


def main(argv=None):
    global SERVICE
    ap = argparse.ArgumentParser(description="CampusVote demo server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    ap.add_argument("--fresh-keys", action="store_true", help="generate new random keys if data/keys.json is missing")
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    SERVICE = make_service(args.fresh_keys)
    SERVER_INFO.update({"host": args.host, "port": args.port, "lan_ip": lan_ip()})
    st = SERVICE.stats()
    rep = SERVICE.verify()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 66)
    print("  CampusVote - %s" % config.TAGLINE)
    print("  Election %s | phase %s | %d/%d tokens, %d ballots" % (
        st["election"]["eid"], st["phase"], st["tokens_issued"], st["eligible"], st["ballots"]))
    print("  Bulletin board: %d entries, %s" % (st["board"]["entries"], rep["verdict"]))
    if SERVICE.halted:
        print("  WARNING: %s" % SERVICE.halted)
    print("  Open   http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  Phones on the same Wi-Fi: http://%s:%d/#vote" % (SERVER_INFO["lan_ip"], args.port))
    print("  Admin key (demo): %s" % ("set via CAMPUSVOTE_ADMIN_KEY" if config.ADMIN_KEY != "ksrce-admin-2026"
                                       else config.ADMIN_KEY))
    print("  Ctrl+C to stop")
    print("=" * 66)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
