#!/usr/bin/env python3
"""CivicLens - AI triage and analytics for citizen complaints.

Run:  python app.py [--host 127.0.0.1] [--port 8019]
Standard library only. Serves static/ at / and a JSON API under /api/.
"""

import argparse
import json
import math
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from civiclens import config as C  # noqa: E402
from civiclens import datagen  # noqa: E402
from civiclens.engine import Engine  # noqa: E402

STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
MAX_BODY = 64 * 1024
MAX_TEXT = 1000
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".ico": "image/x-icon", ".json": "application/json", ".csv": "text/csv; charset=utf-8"}

ENGINE = None
ENDPOINTS = {
    ("GET", "/api/health"), ("GET", "/api/summary"), ("GET", "/api/town"), ("GET", "/api/queue"),
    ("POST", "/api/analyze"), ("POST", "/api/complaints"), ("POST", "/api/demo/reset"), ("GET", "/api/demo/samples"),
    ("GET", "/api/map"), ("GET", "/api/hotspots"), ("GET", "/api/heatgrid"), ("GET", "/api/emerging"),
    ("GET", "/api/sla"), ("GET", "/api/at-risk"), ("GET", "/api/wards"), ("GET", "/api/models"),
    ("GET", "/api/topics"), ("GET", "/api/complaints.csv"),
}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _num(qs, key, default, lo, hi, integer=False):
    v = qs.get(key, [None])[0]
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except ValueError:
        raise ApiError(400, "%s must be a number" % key)
    if math.isnan(x) or x < lo or x > hi:
        raise ApiError(400, "%s must be between %s and %s" % (key, lo, hi))
    return int(x) if integer else x


def _dept(qs):
    d = (qs.get("dept", [""])[0] or "").strip().upper()
    if not d or d == "ALL":
        return None
    if d not in C.DEPT_CODES:
        raise ApiError(400, "unknown dept '%s' (use one of %s)" % (d, ", ".join(C.DEPT_CODES)))
    return d


def _complaint_body(body):
    if not isinstance(body, dict):
        raise ApiError(400, "JSON object expected")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ApiError(400, "'text' is required")
    if len(text) > MAX_TEXT:
        raise ApiError(400, "'text' is too long (max %d characters)" % MAX_TEXT)
    lat, lon = body.get("lat"), body.get("lon")
    if lat is None and lon is None and body.get("ward"):
        w = ENGINE.ward_by_code.get(str(body["ward"]).upper())
        if not w:
            raise ApiError(400, "unknown ward '%s'" % body["ward"])
        lat, lon = w["center"]
    if lat is not None or lon is not None:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            raise ApiError(400, "'lat' and 'lon' must be numbers")
        b = ENGINE.town()["bounds"]
        if not (b[0] - 0.01 <= lat <= b[2] + 0.01 and b[1] - 0.01 <= lon <= b[3] + 0.01):
            raise ApiError(400, "location is outside %s (lat %.3f-%.3f, lon %.3f-%.3f)" % (C.TOWN_NAME, b[0], b[2], b[1], b[3]))
        x, y = datagen.to_xy(lat, lon)
        x = min(max(x, 1.0), C.GRID_COLS * 1000.0 * C.WARD_KM - 1.0)
        y = min(max(y, 1.0), C.GRID_ROWS * 1000.0 * C.WARD_KM - 1.0)
        lat, lon = datagen.to_latlon(x, y)
    channel = body.get("channel") or "App"
    if channel not in [c for c, _ in C.CHANNELS]:
        raise ApiError(400, "unknown channel '%s'" % channel)
    return text, lat, lon, channel


class Handler(BaseHTTPRequestHandler):
    server_version = "CivicLens/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
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

    def _json(self, obj, status=200):
        self._send(status, _clean(obj))

    def _error(self, status, message):
        self._json({"error": message, "status": status}, status)

    def _json_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad Content-Length")
        if n > MAX_BODY:
            raise ApiError(413, "request body too large (max 64 KB)")
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "body must be valid UTF-8 JSON")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        url = urlparse(self.path)
        path, qs = url.path.rstrip("/") or "/", parse_qs(url.query)
        try:
            if path.startswith("/api/"):
                with ENGINE.lock:
                    self._api(method, path, qs)
            elif method == "GET":
                self._static(path)
            else:
                raise ApiError(405, "method not allowed")
        except ApiError as e:
            self._error(e.status, e.message)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # never crash the server on bad input
            sys.stderr.write("  ! internal error: %r\n" % e)
            try:
                self._error(500, "internal error: %s" % e.__class__.__name__)
            except Exception:
                pass

    def _static(self, path):
        rel = unquote(path).lstrip("/") or "index.html"
        full = os.path.realpath(os.path.join(STATIC, rel))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            raise ApiError(404, "not found")
        with open(full, "rb") as f:
            body = f.read()
        self._send(200, body, MIME.get(os.path.splitext(full)[1], "application/octet-stream"))

    def _api(self, method, path, qs):
        E = ENGINE
        if path.startswith("/api/complaint/"):
            if method != "GET":
                raise ApiError(405, "method %s not allowed on %s" % (method, path))
            cid = unquote(path[len("/api/complaint/"):]).strip().upper()
            c = E.get(cid)
            if c is None:
                raise ApiError(404, "no complaint with id '%s'" % cid)
            return self._json(E.public(c, full=True))
        if (method, path) not in ENDPOINTS:
            if any(p == path for _, p in ENDPOINTS):
                raise ApiError(405, "method %s not allowed on %s" % (method, path))
            raise ApiError(404, "unknown endpoint %s" % path)

        if path == "/api/health":
            return self._json({"ok": True, "product": "CivicLens", "complaints": len(E.all_complaints()),
                               "build_s": E.timings.get("total_build_s"), "time": time.time()})
        if path == "/api/summary":
            return self._json(E.summary())
        if path == "/api/town":
            return self._json(E.town())
        if path == "/api/queue":
            pr = _num(qs, "priority", None, 1, 4, integer=True)
            status = (qs.get("status", [""])[0] or "").lower() or None
            if status not in (None, "open", "all"):
                raise ApiError(400, "status must be 'open' or 'all'")
            q = (qs.get("q", [""])[0] or "").strip()[:80] or None
            rows = E.queue(_num(qs, "limit", 40, 1, 500, integer=True), _dept(qs), pr, status, q)
            return self._json({"now": datagen.iso(E.clock), "count": len(rows), "complaints": rows})
        if path in ("/api/analyze", "/api/complaints"):
            text, lat, lon, channel = _complaint_body(self._json_body())
            res = E.analyze(text, lat, lon, channel, record=(path == "/api/complaints"))
            return self._json(res, 201 if path == "/api/complaints" else 200)
        if path == "/api/demo/reset":
            E.reset_live()
            return self._json({"ok": True, "message": "Live complaints cleared; back to the %d-complaint demo stream." % len(E.complaints)})
        if path == "/api/demo/samples":
            return self._json({"samples": E.demo_samples()})
        if path == "/api/map":
            weeks = _num(qs, "weeks", None, 1, C.N_WEEKS, integer=True)
            return self._json(E.map_points(_dept(qs), weeks))
        if path == "/api/hotspots":
            eps = _num(qs, "eps", C.DBSCAN_EPS_M, 30, 600)
            mp = _num(qs, "min_pts", C.DBSCAN_MIN_PTS, 2, 60, integer=True)
            weeks = _num(qs, "weeks", None, 1, C.N_WEEKS, integer=True)
            res = dict(E.hotspots(_dept(qs), eps, mp, weeks))
            res["evaluation"] = E.hotspot_eval
            return self._json(res)
        if path == "/api/heatgrid":
            return self._json(E.heatgrid(_dept(qs)))
        if path == "/api/emerging":
            wk = _num(qs, "week", C.N_WEEKS, C.EMERGING_BASELINE_WEEKS + 1, C.N_WEEKS, integer=True)
            return self._json({"week": wk, "flags": E.emerging(wk), "evaluation": E.emerging_eval,
                               "week_start": datagen.iso((wk - 1) * 7)[:10]})
        if path == "/api/sla":
            return self._json(E.sla())
        if path == "/api/at-risk":
            return self._json(E.at_risk(_num(qs, "limit", 30, 1, 500, integer=True)))
        if path == "/api/wards":
            return self._json({"wards": E.wards_ranking()})
        if path == "/api/models":
            return self._json(E.models())
        if path == "/api/topics":
            k = _num(qs, "k", None, C.TOPIC_K_RANGE[0], C.TOPIC_K_RANGE[1], integer=True)
            return self._json(E.topics(k))
        if path == "/api/complaints.csv":
            rows = [E.public(c) for c in E.all_complaints()]
            cols = ["id", "ts", "text", "lang", "channel", "ward", "lat", "lon", "dept", "conf", "priority",
                    "dup_of", "root", "status", "age_days", "sla_days", "breached"]
            import csv
            import io
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(cols)
            for r in rows:
                w.writerow(["" if r.get(k) is None else r.get(k) for k in cols])
            return self._send(200, "﻿" + buf.getvalue(), "text/csv; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="civiclens_triaged.csv"'})
        raise ApiError(404, "unknown endpoint %s" % path)


def _clean(o):
    """Make any NaN / inf JSON-safe."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def main():
    global ENGINE
    ap = argparse.ArgumentParser(description="CivicLens complaint triage server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8019)
    args = ap.parse_args()
    t = time.time()
    print("CivicLens: generating the demo complaint stream and training models ...", flush=True)
    os.makedirs(DATA, exist_ok=True)
    if not os.path.exists(os.path.join(DATA, "complaints.csv")):
        datagen.write_files(DATA)
    ENGINE = Engine(data_dir=DATA)
    r = ENGINE.routing_eval["models"]["lr"]
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("\n  ======================================================")
    print("   CivicLens - AI triage & analytics for citizen complaints")
    print("  ------------------------------------------------------")
    print("   %d complaints | routing acc %.1f%% | duplicate F1 %.2f" % (
        len(ENGINE.complaints), 100 * r["accuracy"], ENGINE.dup_eval["pairwise"]["f1"]))
    print("   ready in %.1fs" % (time.time() - t))
    print("   Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("   (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("   Ctrl+C to stop")
    print("  ======================================================\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nCivicLens stopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
