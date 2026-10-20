#!/usr/bin/env python3
"""WattWise server - python app.py [--host 127.0.0.1] [--port 8002]

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

from wattwise import __version__  # noqa: E402
from wattwise.engine import Campus, UnknownBuilding  # noqa: E402
from wattwise.solar import SolarInputError  # noqa: E402
from wattwise.whatif import WhatIfError  # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DATA_DIR = os.path.join(HERE, "data")
MAX_BODY = 64 * 1024
CAMPUS = None


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _building(q, required=True):
    vals = q.get("building") or []
    if not vals or not vals[0]:
        if required:
            raise ApiError(400, "query parameter 'building' is required")
        return None
    return vals[0]


def _int(q, name, default, lo, hi):
    vals = q.get(name)
    if not vals:
        return default
    try:
        v = int(vals[0])
    except ValueError:
        raise ApiError(400, "'%s' must be an integer" % name)
    if not lo <= v <= hi:
        raise ApiError(400, "'%s' must be between %d and %d" % (name, lo, hi))
    return v


def get_routes():
    c = CAMPUS
    return {
        "/api/health": lambda q: {"status": "ok", "version": __version__,
                                  "hours": c.ds.n_hours, "buildings": len(c.ds.loads),
                                  "compute_ms": c.compute_ms},
        "/api/overview": lambda q: c.overview(),
        "/api/buildings": lambda q: {"buildings": c.buildings()},
        "/api/series": lambda q: c.series(_building(q), _int(q, "days", 14, 1, 56)),
        "/api/forecast": lambda q: {k: v for k, v in c.series(_building(q), 7).items()
                                    if k in ("building", "name", "backtest", "forecast")},
        "/api/heatmap": lambda q: c.heatmap(_building(q)),
        "/api/anomalies": lambda q: c.anomalies(_building(q, required=False)),
        "/api/leaderboard": lambda q: c.leaderboard(),
        "/api/evaluation": lambda q: c.evaluation(),
    }


def post_routes():
    c = CAMPUS

    def reset(body):
        c.reload(regenerate=True)
        return {"status": "ok", "message": "Demo data regenerated (seed %d)" % c.seed,
                "hours": c.ds.n_hours, "compute_ms": c.compute_ms}
    return {
        "/api/solar": lambda body: c.solar(body),
        "/api/whatif": lambda body: c.whatif(body),
        "/api/demo/reset": reset,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "WattWise/" + __version__

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("WATTWISE_LOG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # -------------------------------------------------------------- helpers
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
        self._send(status, json.dumps(obj, separators=(",", ":")).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _api(self, fn, arg):
        try:
            self._json(200, fn(arg))
        except ApiError as e:
            self._error(e.status, e.message)
        except UnknownBuilding as e:
            self._error(404, "unknown building '%s'" % e.args[0])
        except (SolarInputError, WhatIfError) as e:
            self._error(400, str(e))
        except Exception:  # never crash the server
            traceback.print_exc()
            self._error(500, "internal error")

    # -------------------------------------------------------------- verbs
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if path.startswith("/api/"):
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
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length > MAX_BODY:
            return self._error(413, "request body too large")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "body must be valid JSON")
        if not isinstance(body, dict):
            return self._error(400, "body must be a JSON object")
        return self._api(routes[path], body)

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep) or not os.path.isfile(full):
            return self._send(404, b"Not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    global CAMPUS
    ap = argparse.ArgumentParser(description="WattWise - energy & carbon copilot")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8002)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    CAMPUS = Campus(DATA_DIR)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("")
    print("  WattWise %s - AI energy & carbon copilot for smart campuses" % __version__)
    print("  %d buildings x %d hours analysed in %d ms (forecast, waste, leaderboard)"
          % (len(CAMPUS.ds.loads), CAMPUS.ds.n_hours, CAMPUS.compute_ms))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop.")
    print("")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye - keep saving watts!")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
