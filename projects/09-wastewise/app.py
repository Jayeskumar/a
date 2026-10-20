#!/usr/bin/env python3
"""WasteWise server - python app.py [--host 127.0.0.1] [--port 8009]

Standard library only. Serves the dashboard from static/ and a JSON API under /api/.
"""

import argparse
import json
import mimetypes
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wastewise import __version__  # noqa: E402
from wastewise.engine import BadRequest, Engine, NotFound  # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DATA_DIR = os.path.join(HERE, "data")
MAX_BODY = 32 * 1024
ENGINE = None


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _q(q, name, default=None):
    vals = q.get(name)
    return vals[0] if vals and vals[0] != "" else default


def _num(q, name, lo, hi, cast=float):
    v = _q(q, name)
    if v is None:
        return None
    try:
        x = cast(v)
    except ValueError:
        raise ApiError(400, "'%s' must be a number" % name)
    if not lo <= x <= hi:
        raise ApiError(400, "'%s' must be between %s and %s" % (name, lo, hi))
    return x


def _required(q, name):
    v = _q(q, name)
    if v is None:
        raise ApiError(400, "query parameter '%s' is required" % name)
    return v


def get_routes():
    e = ENGINE
    return {
        "/api/health": lambda q: dict(e.health(), version=__version__),
        "/api/town": lambda q: e.town_json(),
        "/api/state": lambda q: e.state_json(),
        "/api/plan": lambda q: e.plan_json(),
        "/api/forecast": lambda q: e.forecast_json(_required(q, "bin").upper()),
        "/api/simulate": lambda q: e.month_json(_num(q, "days", 7, 90, int)),
        "/api/evaluation": lambda q: e.evaluation_json(),
        "/api/classify": lambda q: e.classify_json(_required(q, "item")),
        "/api/leaderboard": lambda q: e.leaderboard_json(),
        "/api/impact": lambda q: e.impact_json(_num(q, "diesel", 40, 250),
                                               _num(q, "bins", 10, 100000, int),
                                               _num(q, "kmpl", 1, 15)),
    }


def post_routes():
    e = ENGINE
    return {
        "/api/classify": lambda b: e.classify_json((b or {}).get("item")),
        "/api/report": lambda b: e.report_json(b),
        "/api/sim/advance": lambda b: e.advance(b),
        "/api/sim/reset": lambda b: e.reset(),
        "/api/demo": lambda b: e.demo(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "WasteWise/" + __version__

    def log_message(self, fmt, *args):  # quiet unless asked
        if os.environ.get("WASTEWISE_LOG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _api(self, fn, arg):
        try:
            self._json(200, fn(arg))
        except ApiError as ex:
            self._error(ex.status, ex.message)
        except BadRequest as ex:
            self._error(400, str(ex))
        except NotFound as ex:
            self._error(404, str(ex))
        except Exception:  # never crash the server
            traceback.print_exc()
            self._error(500, "internal error")

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if path.startswith("/api/") or path == "/api":
            routes = get_routes()
            if path in routes:
                return self._api(routes[path], parse_qs(url.query))
            if path in post_routes():
                return self._error(405, "use POST for %s" % path)
            return self._error(404, "no such endpoint: %s" % path)
        return self._static(url.path)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        routes = post_routes()
        if path not in routes:
            if path in get_routes():
                return self._error(405, "use GET for %s" % path)
            return self._error(404, "no such endpoint: %s" % path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if n < 0 or n > MAX_BODY:
            return self._error(413, "body too large (max %d bytes)" % MAX_BODY)
        raw = self.rfile.read(n) if n else b""
        body = {}
        if raw.strip():
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return self._error(400, "body must be valid JSON")
        if not isinstance(body, dict):
            return self._error(400, "body must be a JSON object")
        return self._api(routes[path], body)

    def _static(self, raw_path):
        rel = raw_path.split("?", 1)[0].lstrip("/") or "index.html"
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        root = os.path.realpath(STATIC_DIR)
        if not (full == root or full.startswith(root + os.sep)):
            return self._error(403, "forbidden")
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            return self._error(404, "not found: /%s" % rel)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def make_server(host, port, data_dir=None):
    global ENGINE
    ENGINE = Engine(data_dir or DATA_DIR)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description="WasteWise - smart bins & optimised collection routes")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to allow phones on the LAN")
    ap.add_argument("--port", type=int, default=8009)
    args = ap.parse_args(argv)
    try:
        httpd = make_server(args.host, args.port)
    except OSError as ex:
        print("Could not start on %s:%d - %s" % (args.host, args.port, ex))
        return 1
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("\n  WasteWise %s - smart bins & optimised collection routes" % __version__)
    print("  %d bins, %d trucks, town ready in %.0f ms" % (
        len(ENGINE.town.bins), len(ENGINE.town.trucks), ENGINE.startup_ms))
    print("  Open  http://%s:%d/   (Ctrl+C to stop)\n" % (shown, args.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Bye - keep your city clean!")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
