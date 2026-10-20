"""MindEase - a private, early-support companion for student mental wellbeing.

Run:  python app.py [--host 127.0.0.1] [--port 8016]
Standard library only. Supportive screening & self-help prototype - NOT a diagnostic tool.
"""

import argparse
import datetime as _dt
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

from mindease import (config, evaluation, planner, questionnaires, resources,  # noqa: E402
                      safety, sentiment, talk_script)
from mindease.store import Store  # noqa: E402

STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
MAX_BODY = 64 * 1024
# Explicit types: the Windows registry can map .js to text/plain.
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".json": "application/json; charset=utf-8", ".ico": "image/x-icon"}

STORE = None
_STORE_LOCK = threading.Lock()
_EVAL = {"result": None}
_EVAL_LOCK = threading.Lock()


def get_store():
    global STORE
    with _STORE_LOCK:
        if STORE is None:
            STORE = Store(os.path.join(DATA, "state.json"))
        return STORE


def get_evaluation():
    """Serve data/evaluation.json if present, else compute (no HTTP part) and cache."""
    with _EVAL_LOCK:
        if _EVAL["result"] is None:
            path = os.path.join(DATA, "evaluation.json")
            try:
                with open(path, encoding="utf-8") as f:
                    _EVAL["result"] = json.load(f)
            except (OSError, ValueError):
                _EVAL["result"] = evaluation.evaluate(include_http=False)
        return _EVAL["result"]


class ApiError(Exception):
    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


class Handler(BaseHTTPRequestHandler):
    server_version = "MindEase/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("MINDEASE_LOG"):
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
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "body must be valid JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return self.headers.get("X-Demo-Token", "").strip()

    def _counsellor(self):
        sess = get_store().session(self._token())
        if not sess:
            raise ApiError(401, "counsellor sign-in required (demo PIN on the login card)")
        return sess

    def _dispatch(self, method):
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                return self._api(method, url.path, parse_qs(url.query))
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method not allowed")
            return self._static(url.path)
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
        store = get_store()

        def need(*methods):
            if method not in methods and not (method == "HEAD" and "GET" in methods):
                raise ApiError(405, "method not allowed")

        def guard(fn, *args):
            try:
                return fn(*args)
            except ValueError as e:
                detail = e.args[0] if e.args else str(e)
                if isinstance(detail, dict):
                    raise ApiError(400, "invalid input", detail)
                raise ApiError(409 if "already" in str(detail) else 400, str(detail))
            except KeyError:
                raise ApiError(404, "not found")
            except PermissionError as e:
                raise ApiError(401, str(e))

        if path == "/api/health":
            need("GET")
            return self._send(200, {"status": "ok", "product": "MindEase",
                                    "today": store.today().isoformat()})
        if path == "/api/questionnaires":
            need("GET")
            return self._send(200, questionnaires.definitions())
        if path == "/api/screening":
            need("POST")
            return self._send(200, guard(store.add_screening, self._json_body()))
        if path == "/api/student":
            need("GET")
            return self._send(200, store.student())
        if path == "/api/consent":
            need("POST")
            return self._send(200, {"consent": guard(store.set_consent, self._json_body())})
        if path == "/api/journal":
            need("POST")
            return self._send(201, guard(store.add_journal, self._json_body()))
        m = re.fullmatch(r"/api/journal/(j\d{1,6})", path)
        if m:
            need("DELETE")
            if not store.delete_journal(m.group(1)):
                raise ApiError(404, "entry not found")
            return self._send(200, {"deleted": m.group(1)})
        if path == "/api/analyze":
            need("POST")
            body = self._json_body()
            text = body.get("text")
            if not isinstance(text, str) or len(text) > 1000:
                raise ApiError(400, "invalid input", {"text": "text up to 1000 characters"})
            t0 = time.perf_counter()
            res = {"sentiment": sentiment.analyse(text), "safety": safety.detect(text)}
            res["compute_ms"] = round((time.perf_counter() - t0) * 1e3, 3)
            if res["safety"]["flagged"]:
                reason = "someone_else" if res["safety"]["category"] == "someone_else" \
                    else "journal"
                res["support"] = resources.support_screen(reason, res["safety"]["level"])
            return self._send(200, res)
        if path == "/api/trends":
            need("GET")
            return self._send(200, store.student()["trends"])
        if path == "/api/planner":
            need("POST")
            body = self._json_body()
            return self._send(200, guard(planner.plan, body, store.today()))
        if path == "/api/script":
            need("POST")
            return self._send(200, guard(talk_script.generate, self._json_body()))
        if path == "/api/script/options":
            need("GET")
            return self._send(200, talk_script.options())
        if path == "/api/resources":
            need("GET")
            return self._send(200, resources.all_resources())
        if path == "/api/support":
            need("GET")
            reason = query.get("reason", ["general"])[0]
            level = query.get("level", ["urgent"])[0]
            if reason not in ("general", "item9", "journal", "script", "someone_else") or \
                    level not in ("urgent", "concern"):
                raise ApiError(400, "unknown reason or level")
            return self._send(200, resources.support_screen(reason, level))
        if path == "/api/support/contact":
            need("POST")
            return self._send(200, guard(store.request_contact, self._json_body()))
        if path == "/api/demo/reset":
            need("POST")
            return self._send(200, store.reset_demo())
        if path == "/api/student/erase":
            need("POST")
            return self._send(200, store.erase_student())
        if path == "/api/counsellor/login":
            need("POST")
            return self._send(200, guard(store.login, self._json_body()))
        if path == "/api/counsellor/logout":
            need("POST")
            store.logout(self._token())
            return self._send(200, {"ok": True})
        if path == "/api/counsellor/dashboard":
            need("GET")
            sess = self._counsellor()
            data = store.dashboard()
            data["viewer"] = {"name": sess["name"], "role": sess["role"]}
            return self._send(200, data)
        m = re.fullmatch(r"/api/counsellor/alerts/(A\d{1,6})/(ack|followup)", path)
        if m:
            need("POST")
            sess = self._counsellor()
            body = self._json_body()
            fn = store.acknowledge if m.group(2) == "ack" else store.follow_up
            return self._send(200, {"alert": guard(fn, m.group(1), sess["name"],
                                                   body.get("note"))})
        m = re.fullmatch(r"/api/counsellor/contacts/(C\d{1,6})/done", path)
        if m:
            need("POST")
            sess = self._counsellor()
            return self._send(200, {"contact": guard(store.mark_contacted, m.group(1),
                                                     sess["name"])})
        if path == "/api/evaluation":
            need("GET")
            return self._send(200, get_evaluation())
        raise ApiError(404, "unknown endpoint")


def main(argv=None):
    ap = argparse.ArgumentParser(description="MindEase student wellbeing companion")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8016)
    args = ap.parse_args(argv)
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print("Could not start on %s:%d (%s). Is another copy running? Try --port 8026."
              % (args.host, args.port, exc))
        return 1
    server.daemon_threads = True
    get_store()
    threading.Thread(target=get_evaluation, daemon=True).start()
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 64)
    print("  MindEase - a private, early-support companion for students")
    print("  PHQ-9 / GAD-7 check-ins, mood journal, trends, self-help toolkit")
    print("  Open:  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Counsellor demo PIN: %s" % config.DEMO_COUNSELLOR_PIN)
    print("  Screening & self-help only - NOT a diagnosis.  Help: Tele-MANAS 14416, "
          "emergency 112")
    print("  Ctrl+C to stop.  (%s)" % _dt.date.today().isoformat())
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MindEase.")
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
