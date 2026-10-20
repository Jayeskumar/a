#!/usr/bin/env python3
"""NeuroCanvas server - python app.py [--host 127.0.0.1] [--port 8014]

Draw a digit, watch a neural network think. Standard library only.
Serves the UI from static/ and a JSON API under /api/.
"""

import argparse
import json
import mimetypes
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from neurocanvas import __version__                        # noqa: E402
from neurocanvas.service import ConflictError, Service     # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DATA_DIR = os.path.join(HERE, "data")
MAX_BODY = 2 * 1024 * 1024      # a raw 512x512 bitmap as JSON fits comfortably
SVC = None


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _finite(o):
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


def _one(q, name, default=None):
    vals = q.get(name)
    return vals[0] if vals else default


def get_routes(q):
    s = SVC
    return {
        "/api/health": s.health,
        "/api/model": s.model_info,
        "/api/weights": s.weights,
        "/api/evaluation": s.evaluation,
        "/api/samples": lambda: s.samples(_one(q, "digit"), _one(q, "n"), _one(q, "split", "train"),
                                          _one(q, "offset")),
        "/api/demo": lambda: s.demo(_one(q, "digit"), _one(q, "seed"), _one(q, "style", "hand")),
        "/api/train/status": s.train_status,
        "/api/teach": s.teach_list,
    }


def post_routes(body):
    s = SVC
    return {
        "/api/predict": lambda: s.predict(body),
        "/api/explain": lambda: s.explain(body),
        "/api/train/start": lambda: s.train_start(body),
        "/api/train/stop": s.train_stop,
        "/api/train/adopt": s.train_adopt,
        "/api/model/reset": s.reset_model,
        "/api/teach/add": lambda: s.teach_add(body),
        "/api/teach/delete": lambda: s.teach_delete(body),
        "/api/teach/clear": s.teach_clear,
        "/api/teach/demo": s.teach_demo,
        "/api/teach/finetune": lambda: s.teach_finetune(body),
    }


POST_ONLY = {"/api/predict", "/api/explain", "/api/train/start", "/api/train/stop", "/api/train/adopt",
             "/api/model/reset", "/api/teach/add", "/api/teach/delete", "/api/teach/clear",
             "/api/teach/demo", "/api/teach/finetune"}
GET_ONLY = {"/api/health", "/api/model", "/api/weights", "/api/evaluation", "/api/samples", "/api/demo",
            "/api/train/status", "/api/teach"}


class Handler(BaseHTTPRequestHandler):
    server_version = "NeuroCanvas/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("NEUROCANVAS_LOG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    def _send(self, status, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):   # the browser went away mid-response
            self.close_connection = True

    def _json(self, status, obj):
        try:
            text = json.dumps(obj, separators=(",", ":"), allow_nan=False)
        except ValueError:                        # NaN/inf (e.g. a diverged run) -> null
            text = json.dumps(_finite(obj), separators=(",", ":"))
        self._send(status, text, "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _run(self, fn):
        try:
            self._json(200, fn())
        except ApiError as e:
            self._error(e.status, e.message)
        except ConflictError as e:
            self._error(409, str(e))
        except KeyError as e:
            self._error(404, "not found: %s" % (e.args[0] if e.args else ""))
        except (ValueError, TypeError) as e:
            self._error(400, str(e))
        except Exception:
            traceback.print_exc()
            self._error(500, "internal error")

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if path.startswith("/api/"):
            routes = get_routes(parse_qs(url.query))
            if path in routes:
                return self._run(routes[path])
            if path in POST_ONLY:
                return self._error(405, "use POST for %s" % path)
            return self._error(404, "no such endpoint: %s" % path)
        return self._static(url.path)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length < 0 or length > MAX_BODY:
            self.close_connection = True          # body left unread: do not reuse the socket
            return self._error(413, "request body too large (max %d bytes)" % MAX_BODY)
        raw = self.rfile.read(length) if length else b""
        if path in GET_ONLY:
            return self._error(405, "use GET for %s" % path)
        body = {}
        if raw.strip():
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return self._error(400, "body must be valid JSON")
        routes = post_routes(body)
        if path not in routes:
            return self._error(404, "no such endpoint: %s" % path)
        return self._run(routes[path])

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not full.startswith(STATIC_DIR + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NeuroCanvas - draw a digit, watch a neural network think")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8014)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")

    global SVC
    t0 = time.perf_counter()
    print("NeuroCanvas %s - loading digits and network..." % __version__, flush=True)
    SVC = Service(DATA_DIR)
    info = SVC.model_info()
    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("could not listen on %s:%d (%s)" % (args.host, args.port, e))
        return 1
    httpd.daemon_threads = True
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    bar = "=" * 60
    print(bar)
    print("  NeuroCanvas - draw a digit, watch a neural network think")
    print("  network %s (%s, %d weights), %d synthetic digits"
          % ("-".join(map(str, info["sizes"])), info["activation"], info["n_params"], len(SVC.ds)))
    print("  ready in %.1f s  ->  http://%s:%d/" % (time.perf_counter() - t0, shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - open it from a phone on the same Wi-Fi)")
    print("  Ctrl+C to stop")
    print(bar, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        SVC.live.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
