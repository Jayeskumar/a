"""CertChain HTTP server (stdlib only).

    python app.py [--host 127.0.0.1] [--port 8004]
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from certchain import config, security
from certchain.records import ValidationError
from certchain.service import CertChainService, Conflict, NotFound

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")

SERVICE = None
CERT_ID_RE = re.compile(r"^[A-Za-z0-9\-]{3,40}$")


class Handler(BaseHTTPRequestHandler):
    server_version = "CertChain/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

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
        if n > config.MAX_BODY_BYTES:
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

    def _base_url(self):
        host = self.headers.get("Host") or "%s:%s" % self.server.server_address[:2]
        if not re.match(r"^[A-Za-z0-9.\-:\[\]]{1,100}$", host):
            host = "127.0.0.1"
        return "http://" + host

    def _cert_id(self, raw):
        if not CERT_ID_RE.match(raw or ""):
            raise ValidationError("invalid certificate id")
        return raw.upper()

    # -- dispatch --------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _not_allowed(self):
        self._error(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = _not_allowed

    def _dispatch(self, method):
        url = urlparse(self.path)
        path = url.path
        try:
            if path.startswith("/api/"):
                return self._api(method, path, parse_qs(url.query))
            if method != "GET":
                return self._error(405, "method not allowed")
            return self._static(path)
        except ValidationError as exc:
            self._error(400, str(exc))
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
                return self._send(200, {"ok": True, "service": "certchain"})
            if path == "/api/stats":
                return self._send(200, S.stats())
            if path == "/api/institutions":
                return self._send(200, {"institutions": S.institutions(),
                                        "cert_types": config.CERT_TYPES})
            if path == "/api/chain":
                return self._send(200, S.chain_summary())
            m = re.match(r"^/api/block/(\d{1,6})$", path)
            if m:
                return self._send(200, S.block(int(m.group(1))))
            if path == "/api/certificates":
                return self._send(200, {"certificates": S.certificates(qs.get("q", [""])[0][:60])})
            m = re.match(r"^/api/certificate/([^/]+)$", path)
            if m:
                return self._send(200, S.certificate(self._cert_id(m.group(1)), self._base_url()))
            m = re.match(r"^/api/certificate/([^/]+)/qr\.svg$", path)
            if m:
                data = S.certificate(self._cert_id(m.group(1)), self._base_url())
                return self._send(200, data["qr_svg"], "image/svg+xml")
            m = re.match(r"^/api/verify/([^/]+)$", path)
            if m:
                return self._send(200, S.verify(cert_id=self._cert_id(m.group(1)),
                                                code=qs.get("code", [""])[0][:20]))
            if path == "/api/validate":
                return self._send(200, S.validate())
            if path == "/api/security":
                return self._send(200, {"threats": security.THREATS, "limits": security.LIMITS})
            if path == "/api/sample.csv":
                with open(os.path.join(DATA, "sample_bulk.csv"), "rb") as f:
                    return self._send(200, f.read(), "text/csv; charset=utf-8")
            return self._error(404, "unknown endpoint")
        if method == "POST":
            body = self._body()
            if path == "/api/issue":
                return self._send(201, S.issue(str(body.get("issuer_id", "")), body))
            if path == "/api/issue/bulk":
                return self._send(201, S.bulk_issue(str(body.get("issuer_id", "")), body.get("csv")))
            if path == "/api/verify":
                bundle = body.get("bundle")
                if isinstance(bundle, str):
                    try:
                        bundle = json.loads(bundle)
                    except ValueError:
                        raise ValidationError("bundle is not valid JSON")
                cid = body.get("cert_id")
                if bundle is None:
                    cid = self._cert_id(str(cid or "").strip())
                code = body.get("code")
                return self._send(200, S.verify(cert_id=cid, bundle=bundle,
                                                code=str(code)[:20] if code else None))
            if path == "/api/revoke":
                return self._send(201, S.revoke(str(body.get("issuer_id", "")),
                                                self._cert_id(str(body.get("cert_id", "")).strip()),
                                                body.get("reason")))
            if path == "/api/tamper":
                cid = body.get("cert_id")
                return self._send(200, S.tamper(str(body.get("mode", "edit")),
                                                self._cert_id(str(cid)) if cid else None))
            if path == "/api/restore":
                return self._send(200, S.restore())
            if path == "/api/demo/reset":
                return self._send(200, S.reset_demo())
            return self._error(404, "unknown endpoint")
        return self._error(405, "method not allowed")

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    global SERVICE
    ap = argparse.ArgumentParser(description="CertChain demo server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8004)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    SERVICE = CertChainService(DATA)
    st = SERVICE.stats()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 62)
    print("  CertChain - Tamper-proof academic credentials, verified in seconds")
    print("  Ledger: %d blocks, %d certificates, chain %s" % (
        st["blocks"], st["certificates"], "VALID" if st["chain_valid"] else "BROKEN"))
    print("  Open   http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop")
    print("=" * 62)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
