"""KrishiMitra - a smart farming advisor in the farmer's own language.

Run:  python app.py [--host 127.0.0.1] [--port 8005]
Pure Python 3.9+ standard library; works fully offline.
"""
import argparse
import datetime as _dt
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from krishimitra import (advisor, config, cropcal, dataset, fertiliser,  # noqa: E402
                         irrigation, market, weather)
from krishimitra.advisor import InputError  # noqa: E402
from krishimitra.recommender import get_model  # noqa: E402

STATIC = os.path.join(ROOT, "static")
MAX_BODY = 64 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
    ".json": "application/json; charset=utf-8", ".ico": "image/x-icon",
}


def _crop(value):
    if value not in config.CROPS:
        raise InputError("crop must be one of: %s" % ", ".join(config.CROPS))
    return value


def api_recommend(body, q):
    return get_model().recommend(advisor.soil_inputs(body))


def api_fertiliser(body, q):
    crop = _crop(body.get("crop"))
    n = advisor.num(body, "N", *config.FEATURE_LIMITS["N"])
    p = advisor.num(body, "P", *config.FEATURE_LIMITS["P"])
    k = advisor.num(body, "K", *config.FEATURE_LIMITS["K"])
    ph = advisor.num(body, "ph", *config.FEATURE_LIMITS["ph"], default=7.0)
    area = advisor.num(body, "area_acres", 0.05, 10000, 1.0)
    return fertiliser.advise(crop, n, p, k, ph, area)


def api_irrigation(body, q):
    crop = _crop(body.get("crop"))
    lat = advisor.num(body, "lat", -60, 60, 11.0)
    area = advisor.num(body, "area_acres", 0.05, 10000, 1.0)
    soil = advisor.choice(body, "soil", config.SOIL_TYPES, "red")
    method = advisor.choice(body, "method", config.IRRIGATION_METHODS, "flood")
    start = advisor.date_field(body, "start_date", _dt.date.today())
    sowing = advisor.date_field(body, "sowing_date", start - _dt.timedelta(days=20))
    rf = advisor.num(body, "rain_factor", 0, 5, 1.0)
    fc, src = advisor.forecast_field(body, lat, start, rf)
    out = irrigation.plan(crop, lat, sowing, start, fc, soil, method, area)
    out["forecast_source"] = src
    return out


def api_market(body, q):
    crop = _crop(q.get("crop", "rice"))
    as_of = advisor.date_field(q, "date", _dt.date.today())
    try:
        return market.analyse(crop, as_of)
    except ValueError as e:
        raise InputError(str(e))


def api_calendar(body, q):
    crop = _crop(q.get("crop", "rice"))
    today = advisor.date_field(q, "today", _dt.date.today())
    sowing = advisor.date_field(q, "sowing_date", today)
    return cropcal.calendar(crop, sowing, today)


def api_et0(body, q):
    lat = advisor.num(q, "lat", -66, 66, 11.0)
    doy = int(advisor.num(q, "doy", 1, 366, _dt.date.today().timetuple().tm_yday))
    tmin = advisor.num(q, "tmin", -20, 45, 22)
    tmax = advisor.num(q, "tmax", -10, 55, 33)
    ra = irrigation.extraterrestrial_radiation(lat, doy)
    return {"lat": lat, "doy": doy, "tmin": tmin, "tmax": tmax,
            "dr": round(irrigation.inverse_distance(doy), 4),
            "declination_rad": round(irrigation.declination(doy), 4),
            "ra_mj_m2_day": round(ra, 2),
            "et0_mm_day": round(irrigation.hargreaves_et0(tmin, tmax, ra), 2)}


def api_forecast(body, q):
    lat = advisor.num(q, "lat", -60, 60, 11.0)
    start = advisor.date_field(q, "date", _dt.date.today())
    rf = advisor.num(q, "rain_factor", 0, 5, 1.0)
    return {"source": "synthetic", "days": weather.synth_forecast(lat, start, 7, rf)}


GET_ROUTES = {
    "/api/health": lambda b, q: {"status": "ok", "app": "KrishiMitra",
                                 "time": _dt.datetime.now().isoformat(timespec="seconds")},
    "/api/meta": lambda b, q: advisor.meta(),
    "/api/presets": lambda b, q: {"presets": config.PRESETS},
    "/api/model": lambda b, q: get_model().metrics,
    "/api/market": api_market,
    "/api/calendar": api_calendar,
    "/api/et0": api_et0,
    "/api/forecast": api_forecast,
}
POST_ROUTES = {
    "/api/recommend": api_recommend,
    "/api/fertiliser": api_fertiliser,
    "/api/irrigation": api_irrigation,
    "/api/advise": lambda b, q: advisor.advise(b),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "KrishiMitra/1.0"

    def log_message(self, fmt, *args):     # keep the console quiet but useful
        if os.environ.get("KM_QUIET"):
            return
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    def _send(self, status, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status, msg):
        self._send(status, {"error": msg, "status": status})

    def _query(self):
        parsed = urlparse(self.path)
        return parsed.path, {k: v[-1] for k, v in parse_qs(parsed.query).items()}

    def _dispatch(self, routes, body):
        path, q = self._query()
        fn = routes.get(path)
        if fn is None:
            other = POST_ROUTES if routes is GET_ROUTES else GET_ROUTES
            if path in other:
                return self._error(405, "method not allowed for %s" % path)
            return self._error(404, "unknown endpoint: %s" % path)
        try:
            self._send(200, fn(body, q))
        except InputError as e:
            self._error(400, str(e))
        except Exception as e:  # never crash the server on bad input
            sys.stderr.write("  internal error: %r\n" % (e,))
            self._error(500, "internal error")

    def do_GET(self):
        path, _ = self._query()
        if path.startswith("/api/"):
            return self._dispatch(GET_ROUTES, {})
        self._static(path)

    do_HEAD = do_GET

    def do_POST(self):
        path, _ = self._query()
        if not path.startswith("/api/"):
            return self._error(405, "POST only allowed on /api/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length > MAX_BODY:
            return self._error(413, "request body too large")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "body must be valid JSON")
        if not isinstance(body, dict):
            return self._error(400, "JSON body must be an object")
        self._dispatch(POST_ROUTES, body)

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(STATIC + os.sep) or not os.path.isfile(full):
            return self._error(404, "not found")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as fh:
            self._send(200, fh.read(), CONTENT_TYPES.get(ext, "application/octet-stream"))


def make_server(host, port):
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description="KrishiMitra smart farming advisor")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8005)
    args = ap.parse_args(argv)

    csv_path = dataset.default_csv_path()
    if not os.path.exists(csv_path):
        dataset.write_csv(csv_path)
    t0 = time.perf_counter()
    m = get_model().metrics
    print("Trained GNB + Random Forest (%d trees) in %.2fs - hold-out accuracy GNB %.1f%%, RF %.1f%%"
          % (m["rf_trees"], time.perf_counter() - t0, m["gnb_accuracy"] * 100,
             m["rf_accuracy"] * 100))
    httpd = make_server(args.host, args.port)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 62)
    print("  KrishiMitra - smart farming advisor (English / Tamil)")
    print("  Open  http://%s:%d/  in your browser" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP on a phone)")
    print("  Press Ctrl+C to stop.")
    print("=" * 62)
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping KrishiMitra. Vanakkam!")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
