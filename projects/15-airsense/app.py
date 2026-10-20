#!/usr/bin/env python3
"""AirSense server - python app.py [--host 127.0.0.1] [--port 8015]

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

from airsense import __version__, config, health  # noqa: E402
from airsense.engine import BadRequest, Network, NotFound  # noqa: E402
from airsense.health import ProfileError  # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DATA_DIR = os.path.join(HERE, "data")
MAX_BODY = 32 * 1024
NET = None
_FRAMES_CACHE = {}


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


def _str(q, name, default=None, required=False):
    vals = q.get(name) or []
    if not vals or vals[0] == "":
        if required:
            raise ApiError(400, "query parameter '%s' is required" % name)
        return default
    return vals[0]


def _num(q, name, lo, hi, default=None, integer=False, required=False):
    v = _str(q, name, required=required)
    if v is None:
        return default
    try:
        x = int(v) if integer else float(v)
    except ValueError:
        raise ApiError(400, "'%s' must be %s" % (name, "an integer" if integer else "a number"))
    if x != x or not lo <= x <= hi:
        raise ApiError(400, "'%s' must be between %s and %s" % (name, lo, hi))
    return x


def _hour(q):
    return _num(q, "hour", 0, NET.n - 1, None, integer=True)


def _frames(q):
    key = id(NET.clean)
    if key not in _FRAMES_CACHE:
        _FRAMES_CACHE.clear()
        _FRAMES_CACHE[key] = json.dumps(NET.frames(), separators=(",", ":")).encode("utf-8")
    return _FRAMES_CACHE[key]


def _forecast(q):
    sid = _str(q, "id")
    prof = _str(q, "profile", "general")
    if sid:
        return NET.forecast_view(sid=sid, profile=prof)
    x = _num(q, "x", 0, config.MAP_W_KM)
    y = _num(q, "y", 0, config.MAP_H_KM)
    if x is None or y is None:
        raise ApiError(400, "give ?id=<sensor> or ?x=<km>&y=<km>")
    return NET.forecast_view(x=x, y=y, profile=prof)


def _estimate(q):
    x = _num(q, "x", -1e6, 1e6, required=True)
    y = _num(q, "y", -1e6, 1e6, required=True)
    return NET.estimate(x, y, _hour(q))


def _advice(q):
    a = _num(q, "aqi", 0, 500, integer=True, required=True)
    return health.advice(a, _str(q, "profile", "general"))


def get_routes():
    n = NET
    return {
        "/api/health": lambda q: dict(n.health_info(), version=__version__),
        "/api/meta": lambda q: n.meta_view(),
        "/api/frames": _frames,
        "/api/summary": lambda q: n.summary_now(_hour(q)),
        "/api/sensor": lambda q: n.sensor_view(_str(q, "id", required=True)),
        "/api/estimate": _estimate,
        "/api/grid": lambda q: n.grid_view(_hour(q), _str(q, "method", "kriging"), _str(q, "field", "pm25"),
                                           _num(q, "nx", 4, 80, 40, True), _num(q, "ny", 3, 60, 30, True)),
        "/api/forecast": _forecast,
        "/api/faults": lambda q: n.faults_view(),
        "/api/sources": lambda q: n.sources_view(),
        "/api/evaluation": lambda q: n.evaluation(),
        "/api/advice": _advice,
    }


def post_routes():
    n = NET

    def reset(body):
        global NET
        fresh = Network(DATA_DIR, regenerate=True)   # build aside, then swap atomically
        NET = fresh
        _FRAMES_CACHE.clear()
        return {"status": "ok", "message": "Demo data regenerated (seed %d) and every model re-run"
                % fresh.meta["seed"], "compute_ms": fresh.compute_ms}

    return {
        "/api/aqi": lambda body: n.aqi_calc(body),
        "/api/demo/reset": reset,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "AirSense/" + __version__

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("AIRSENSE_LOG"):
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
        body = obj if isinstance(obj, bytes) else json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status, msg):
        self._json(status, {"error": msg, "status": status})

    def _api(self, fn, arg):
        try:
            self._json(200, fn(arg))
        except ApiError as e:
            self._error(e.status, e.message)
        except NotFound as e:
            self._error(404, "unknown sensor '%s'" % e.args[0])
        except (BadRequest, ProfileError) as e:
            self._error(400, str(e))
        except Exception:  # never crash the server
            traceback.print_exc()
            self._error(500, "internal error")

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
        if length < 0 or length > MAX_BODY:
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
    global NET
    ap = argparse.ArgumentParser(description="AirSense - hyperlocal air quality")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8015)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    print("\n  AirSense %s - loading sensor network and training models..." % __version__)
    NET = Network(DATA_DIR)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    h = NET.headline()
    print("  Hyperlocal air quality: know before you breathe")
    print("  %d sensors + %d reference stations x %d hours processed in %d ms"
          % (len(NET.sensors), len(NET.refs), NET.n, NET.compute_ms))
    print("  calibration error -%.0f%% | faults P/R %.0f%%/%.0f%% | forecast MAE %.1f vs %.1f persistence"
          % (h["calibration_rmse_reduction_pct"], h["fault_precision"] * 100, h["fault_recall"] * 100,
             h["forecast_mae"], h["persistence_mae"]))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye - breathe easy!")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
