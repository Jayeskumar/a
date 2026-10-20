"""BloodLink demo server (Python standard library only).

    python app.py [--host 127.0.0.1] [--port 8010]
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bloodlink.eligibility import ProfileError  # noqa: E402
from bloodlink.service import BadRequest, NotFound, Service  # noqa: E402

STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
MAX_BODY = 64 * 1024
DONOR_RE = re.compile(r"^/api/donors/(D-\d{4})(/availability)?$")

SERVICE = None


class Handler(BaseHTTPRequestHandler):
    server_version = "BloodLink/1.0"
    service = None  # set in main() / tests

    def log_message(self, fmt, *args):
        if os.environ.get("BLOODLINK_QUIET"):
            return
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    # -- helpers ---------------------------------------------------------------
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, msg):
        self._send(status, {"error": msg, "status": status})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise BadRequest("bad Content-Length")
        if n < 0 or n > MAX_BODY:
            raise BadRequest("request body too large")
        raw = self.rfile.read(n) if n else b""
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BadRequest("body must be valid JSON")
        if not isinstance(data, dict):
            raise BadRequest("body must be a JSON object")
        return data

    # -- dispatch --------------------------------------------------------------
    def do_HEAD(self):
        self._dispatch("GET")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._error(405, "method not allowed")

    do_DELETE = do_PATCH = do_PUT

    def _dispatch(self, method):
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                return self._api(method, url.path, parse_qs(url.query))
            if method != "GET":
                return self._error(405, "method not allowed")
            return self._static(url.path)
        except (BadRequest, ProfileError) as exc:
            self._error(400, str(exc))
        except NotFound as exc:
            self._error(404, str(exc))
        except Exception:  # never crash the server
            traceback.print_exc()
            self._error(500, "internal error")

    def _api(self, method, path, qs):
        S = self.service

        def q(name, default=""):
            return qs.get(name, [default])[0][:80]

        if method == "GET":
            if path == "/api/health":
                return self._send(200, {"ok": True, "service": "bloodlink", "donors": len(S.donors)})
            if path == "/api/meta":
                return self._send(200, S.meta())
            if path == "/api/compatibility":
                return self._send(200, S.compatibility())
            if path == "/api/map":
                return self._send(200, S.map_points())
            if path == "/api/donors":
                try:
                    limit = int(q("limit", "50"))
                except ValueError:
                    raise BadRequest("limit must be an integer")
                return self._send(200, S.donors_list(q("q"), q("group"), limit))
            m = DONOR_RE.match(path)
            if m and not m.group(2):
                return self._send(200, S.donor(m.group(1)))
            if path == "/api/evaluate":
                return self._send(200, S.evaluate(q("n", "200"), q("seed", "11"), q("factor", "") or None))
            if path == "/api/inventory":
                return self._send(200, S.inventory())
            if path == "/api/inventory/month":
                return self._send(200, S.month(q("seeds", "20")))
            if path == "/api/activity":
                return self._send(200, {"activity": S.activity})
            return self._error(404, "unknown endpoint")
        if method == "POST":
            body = self._body()
            if path == "/api/match":
                return self._send(200, S.match(body))
            if path == "/api/simulate":
                return self._send(200, S.simulate(body))
            if path == "/api/broadcast":
                return self._send(200, S.broadcast(body))
            if path == "/api/eligibility":
                return self._send(200, S.self_check(body))
            m = DONOR_RE.match(path)
            if m and m.group(2):
                return self._send(200, S.set_availability(m.group(1), body))
            if path == "/api/inventory/issue":
                return self._send(200, S.issue(body))
            if path == "/api/inventory/transfers/apply":
                return self._send(200, S.apply_transfers())
            if path == "/api/demo/reset":
                return self._send(200, S.reset())
            return self._error(404, "unknown endpoint")
        return self._error(405, "method not allowed")

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def make_server(host="127.0.0.1", port=8010, data_dir=DATA):
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    Handler.service = Service(data_dir)
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description="BloodLink demo server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args(argv)
    httpd = make_server(args.host, args.port)
    S = Handler.service
    threading.Thread(target=S.warm_up, daemon=True).start()
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 64)
    print("  BloodLink - Find the right blood donor in minutes, not hours")
    print("  %d synthetic donors, %d blood banks, %d red-cell units in stock" % (
        len(S.donors), len(S.net.stock), sum(len(v) for v in S.net.stock.values())))
    print("  Open   http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Prototype only: transfusion decisions follow cross-matching by blood bank staff.")
    print("  Ctrl+C to stop")
    print("=" * 64)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
