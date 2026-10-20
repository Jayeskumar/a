"""PulseGuard - early warning for patient deterioration (NEWS2 + trend detection).

Run:  python app.py [--host 127.0.0.1] [--port 8003]
Standard library only. Decision-support prototype - not a medical device.
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pulseguard import config, evaluation, news2  # noqa: E402
from pulseguard.ward import Ward  # noqa: E402

STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
MAX_BODY = 64 * 1024
# Explicit types: Windows registry can map .js to text/plain, which breaks module loading.
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".json": "application/json; charset=utf-8", ".ico": "image/x-icon"}

WARD = Ward()
_EVAL = {"result": None, "error": None}
_EVAL_LOCK = threading.Lock()


def get_evaluation():
    """Run the offline evaluation once (about a second) and cache it in memory."""
    with _EVAL_LOCK:
        if _EVAL["result"] is None:
            try:
                result = evaluation.evaluate()
                result["sensitivity"] = evaluation.sensitivity()
                result["holdout"] = evaluation.holdout()
                _EVAL["result"] = result
            except Exception as exc:  # never crash the server
                _EVAL["error"] = str(exc)
                return None
        return _EVAL["result"]


class ApiError(Exception):
    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


class Handler(BaseHTTPRequestHandler):
    server_version = "PulseGuard/1.0"

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("PULSEGUARD_LOG"):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------ helpers
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json_body(self):
        length = self.headers.get("Content-Length")
        try:
            length = int(length or 0)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "body must be valid JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data

    def _dispatch(self, method):
        url = urlparse(self.path)
        path = url.path
        query = parse_qs(url.query)
        try:
            if path.startswith("/api/"):
                return self._api(method, path, query)
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method not allowed")
            return self._static(path)
        except ApiError as e:
            body = {"error": e.message}
            if e.details:
                body["details"] = e.details
            self._send(e.status, body)
        except Exception as e:  # last-resort guard: never crash on bad input
            self._send(500, {"error": "internal error", "detail": str(e)})

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # ------------------------------------------------------------ static
    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            raise ApiError(404, "not found")
        full = os.path.join(STATIC, rel)
        if not os.path.isfile(full):
            raise ApiError(404, "not found")
        ext = os.path.splitext(full)[1].lower()
        ctype = TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    # ------------------------------------------------------------ API
    def _api(self, method, path, query):
        def need(*methods):
            if method not in methods and not (method == "HEAD" and "GET" in methods):
                raise ApiError(405, "method not allowed")

        if path == "/api/health":
            need("GET")
            return self._send(200, {"status": "ok", "product": "PulseGuard",
                                    "clock": WARD.summary()["clock"]})
        if path == "/api/ward":
            need("GET")
            return self._send(200, WARD.summary())
        if path == "/api/sim":
            need("POST")
            body = self._json_body()
            try:
                state = WARD.control(str(body.get("action", "")), speed=body.get("speed"),
                                     hours=body.get("hours"))
            except ValueError as e:
                raise ApiError(400, str(e))
            return self._send(200, {"clock": state})
        if path == "/api/alerts":
            need("GET")
            unacked = query.get("unacked", ["0"])[0] in ("1", "true", "yes")
            WARD.sync()
            return self._send(200, {"alerts": WARD.alert_list(unacked_only=unacked)})
        m = re.fullmatch(r"/api/alerts/(\d+)/ack", path)
        if m:
            need("POST")
            body = self._json_body()
            alert = WARD.acknowledge(int(m.group(1)), by=body.get("by", "Nurse"))
            if alert is None:
                raise ApiError(404, "alert not found")
            return self._send(200, {"alert": alert})
        m = re.fullmatch(r"/api/patients/([A-Za-z0-9_-]{1,16})", path)
        if m:
            need("GET")
            detail = WARD.patient_detail(m.group(1))
            if detail is None:
                raise ApiError(404, "patient not found")
            return self._send(200, detail)
        m = re.fullmatch(r"/api/patients/([A-Za-z0-9_-]{1,16})/observations", path)
        if m:
            need("POST")
            obs, errors = news2.validate(self._json_body())
            if errors:
                raise ApiError(400, "invalid observation", errors)
            result = WARD.add_observation(m.group(1), obs)
            if result is None:
                raise ApiError(404, "patient not found")
            return self._send(201, {"reading": result["reading"],
                                    "alerts": result["alerts"],
                                    "result": news2.calculate(obs)})
        if path == "/api/news2":
            need("POST")
            obs, errors = news2.validate(self._json_body())
            if errors:
                raise ApiError(400, "invalid observation", errors)
            t0 = time.perf_counter()
            result = news2.calculate(obs)
            result["compute_us"] = round((time.perf_counter() - t0) * 1e6, 1)
            return self._send(200, result)
        if path == "/api/news2/reference":
            need("GET")
            return self._send(200, news2.reference())
        if path == "/api/handover":
            need("GET")
            data = WARD.handover()
            if query.get("format", [""])[0] == "text":
                return self._send(200, data["text"], "text/plain; charset=utf-8")
            return self._send(200, data)
        if path == "/api/evaluation":
            need("GET")
            res = get_evaluation()
            if res is None:
                raise ApiError(500, "evaluation failed: %s" % _EVAL["error"])
            return self._send(200, res)
        raise ApiError(404, "unknown endpoint")


def main(argv=None):
    ap = argparse.ArgumentParser(description="PulseGuard ward early-warning demo")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8003)
    args = ap.parse_args(argv)
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print("Could not start on %s:%d (%s). Is another copy running? Try --port 8013."
              % (args.host, args.port, exc))
        return 1
    server.daemon_threads = True
    threading.Thread(target=get_evaluation, daemon=True).start()  # warm the cache
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 62)
    print("  PulseGuard - early warning for patient deterioration")
    print("  NEWS2 (RCP 2017) + trend detection, simulated 12-bed ward")
    print("  Open:  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Decision-support prototype - NOT a medical device.  Ctrl+C to stop.")
    print("=" * 62)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PulseGuard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
