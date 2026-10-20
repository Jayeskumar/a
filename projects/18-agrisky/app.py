"""AgriSky - drone-based crop health maps and precision spraying.

Run:  python app.py [--host 127.0.0.1] [--port 8018]
Pure Python 3.9+ standard library; works fully offline.
"""
import argparse
import datetime as _dt
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from agrisky import config, field, indices, prescription, report  # noqa: E402
from agrisky.pipeline import STORE, InputError  # noqa: E402
from agrisky.planner import PlanError  # noqa: E402

STATIC = os.path.join(ROOT, "static")
DATA = os.path.join(ROOT, "data")
SAMPLE = os.path.join(DATA, "sample_flights.json")
METRICS = os.path.join(DATA, "metrics.json")
MAX_BODY = 64 * 1024
N_FLIGHTS = len(config.FLIGHT_DAYS)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
    ".json": "application/json; charset=utf-8", ".ico": "image/x-icon",
}


# ------------------------------------------------------------------ input helpers
def _num(src, key, lo, hi, default, integer=False):
    raw = src.get(key, default)
    if raw is None or raw == "":
        raw = default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise InputError("%s must be a number" % key)
    if v != v or v < lo or v > hi:
        raise InputError("%s must be between %s and %s" % (key, lo, hi))
    if integer:
        if v != int(v):
            raise InputError("%s must be a whole number" % key)
        return int(v)
    return v


def _choice(src, key, options, default):
    v = src.get(key, default)
    if v not in options:
        raise InputError("%s must be one of: %s" % (key, ", ".join(options)))
    return v


def _common(src):
    seed = _num(src, "seed", 0, 1000000, config.DEFAULT_SEED, integer=True)
    flight = _num(src, "flight", 1, N_FLIGHTS, N_FLIGHTS, integer=True)
    k = _num(src, "k", 2, 8, config.KMEANS_K, integer=True)
    return seed, flight - 1, k


def _mission_params(src):
    return {
        "swath": _num(src, "swath", 1, 10, config.DRONE_SWATH_M, integer=True),
        "tank": _num(src, "tank", 0.5, 40, config.DRONE_TANK_L),
        "endurance_s": _num(src, "endurance", 60, 3600, config.DRONE_ENDURANCE_S),
        "spray_speed": _num(src, "speed", 1, 10, config.DRONE_SPRAY_SPEED_MS),
        "orient": _choice(src, "orient", ("auto", "h", "v"), "auto"),
    }


# ------------------------------------------------------------------ API handlers
def api_meta(body, q):
    return {
        "app": "AgriSky", "tagline": "Drone crop-health maps and precision spraying",
        "crop": config.CROP, "field": {"width": config.FIELD_W, "height": config.FIELD_H,
                                       "cell_m": config.CELL_M},
        "flights": [{"flight": i + 1, "day": d, "das": config.DAS_AT_FIRST_FLIGHT + d}
                    for i, d in enumerate(config.FLIGHT_DAYS)],
        "classes": [{"id": c, **config.CLASS_INFO[c]} for c in config.CLASSES],
        "indices": indices.INDEX_INFO, "products": prescription.PRODUCTS,
        "defaults": {"seed": config.DEFAULT_SEED, "k": config.KMEANS_K,
                     "swath": config.DRONE_SWATH_M, "tank": config.DRONE_TANK_L,
                     "endurance": config.DRONE_ENDURANCE_S, "speed": config.DRONE_SPRAY_SPEED_MS,
                     "home": list(config.HOME_XY)},
        "rules": [
            {"rule": "water", "if": "NDWI > %.2f" % config.RULE_WATER_NDWI},
            {"rule": "soil", "if": "NDVI < %.2f" % config.RULE_SOIL_NDVI},
            {"rule": "waterlogging", "if": "NDWI ≥ ref + %.2f and Red ≤ %.2f × ref"
             % (config.RULE_WATERLOG_NDWI_DELTA, config.RULE_WATERLOG_RED_RATIO)},
            {"rule": "pest", "if": "NIR ≤ %.2f × ref and Red ≥ %.2f × ref, or NDVI falling %.2f/week "
             "faster than the field" % (config.RULE_PEST_NIR_RATIO, config.RULE_PEST_RED_RATIO,
                                        -2 * config.RULE_ACTIVE_DECLINE_WEEK)},
            {"rule": "nitrogen", "if": "NDRE ≤ %.2f × ref" % config.RULE_N_NDRE_RATIO},
            {"rule": "healthy", "if": "none of the above"}],
        "assumptions": {
            "urea_rs_per_kg": round(config.UREA_PRICE_RS_PER_KG, 2),
            "urea_base_kg_ha": config.UREA_BASE_KG_HA,
            "pesticide_l_ha": config.PESTICIDE_PRODUCT_L_HA,
            "pesticide_rs_per_l": config.PESTICIDE_PRICE_RS_PER_L,
            "spray_volume_l_ha": config.SPRAY_VOLUME_L_HA,
            "pest_buffer_m": config.PEST_BUFFER_M, "water_no_spray_m": config.WATER_NO_SPRAY_M},
    }


def api_flights(body, q):
    seed, _, k = _common(q)
    return {"seed": seed, "flights": STORE.flights_summary(seed, k)}


def api_scene(body, q):
    seed, fi, k = _common(q)
    out = STORE.scene(seed, fi, k, _mission_params(q))
    out["flight_no"] = fi + 1
    return out


def api_field(body, q):
    seed, fi, _ = _common(q)
    f = STORE.field(seed)["flights"][fi]
    idx = indices.compute_all(f["bands"])
    return {"seed": seed, "flight": fi + 1, "day": f["day"], "width": field.W,
            "height": field.H, "scale": 1000, "bands": list(config.BANDS),
            "classes": list(config.CLASSES),
            "layers": {**{b: [int(round(v * 1000)) for v in f["bands"][b]] for b in config.BANDS},
                       **{n: [int(round(v * 1000)) for v in idx[n]] for n in indices.INDEX_NAMES}},
            "truth": f["truth"]}


def api_zones(body, q):
    seed, fi, k = _common(q)
    a = STORE.analysis(seed, fi, k)
    return {"seed": seed, "flight": fi + 1, "day": a["day"], "k": k,
            "kmeans": {kk: v for kk, v in a["kmeans"].items() if kk != "labels"},
            "raw_zone_count": a["raw_zone_count"], "zones": a["zones"],
            "reference": a["reference"], "accuracy": a["accuracy"], "timing_ms": a["timing_ms"],
            "zone_grid": a["zones_grid"]}


def api_change(body, q):
    seed, fi, k = _common(q)
    base = _num(q, "base", 1, N_FLIGHTS, max(1, fi), integer=True) - 1
    if fi > 0 and base >= fi:
        raise InputError("base must be an earlier flight than flight")
    ch = STORE.change(seed, fi, k, base if fi > 0 else None)
    out = dict(ch)
    out["flight"] = fi + 1
    if ch.get("diff"):
        d = dict(ch["diff"])
        d["relative"] = [int(round(v * 1000)) for v in d["relative"]]
        d.pop("diff", None)
        d["scale"] = 1000
        out["diff"] = d
        out["base"] = base + 1
    return out


def api_prescription(body, q):
    seed, fi, k = _common(q)
    product = _choice(q, "product", tuple(prescription.PRODUCTS), "pesticide")
    buf = _num(q, "buffer", 0, 10, config.PEST_BUFFER_M, integer=True)
    rx = STORE.prescription(seed, fi, product, k, buf)
    out = {kk: v for kk, v in rx.items() if kk != "payload_per_m2"}
    out["flight"] = fi + 1
    return out


def api_mission(body, q):
    src = dict(q)
    src.update(body or {})
    seed, fi, k = _common(src)
    product = _choice(src, "product", tuple(prescription.PRODUCTS), "pesticide")
    kind = _choice(src, "plan", ("vra", "uniform"), "vra")
    buf = _num(src, "buffer", 0, 10, config.PEST_BUFFER_M, integer=True)
    params = _mission_params(src)
    try:
        m = STORE.mission(seed, fi, product, kind, k, buf, **params)
    except PlanError as e:
        raise InputError(str(e))
    out = {kk: v for kk, v in m.items() if kk != "coverage"}
    out["flight"] = fi + 1
    return out


def api_report(body, q):
    seed, fi, k = _common(q)
    s = STORE.scene(seed, fi, k)
    return {"seed": seed, "flight": fi + 1, "day": s["day"], "das": s["das"],
            "report": s["report"], "zones": [
                {kk: z[kk] for kk in ("id", "label", "area_m2", "pct_field", "ndvi", "ndre",
                                      "why", "confidence")} for z in s["zones"]],
            "prescriptions": s["prescriptions"],
            "mission": {kk: s["mission"][kk]["totals"] for kk in ("vra", "uniform")},
            "change": {"alert": s["change"]["spread"]["alert"],
                       "series": s["change"]["spread"]["series"]}}


def api_indices(body, q):
    for b in ("green", "red", "nir"):
        if body.get(b) is None:
            raise InputError("%s reflectance (0-1) is required" % b)
    vals = {b: _num(body, b, 0, 1, 0.0) for b in config.BANDS}
    return {"inputs": vals, "indices": {k: round(v, 4) for k, v in indices.cell_indices(
        vals["green"], vals["red"], vals["rededge"], vals["nir"]).items()},
        "formulas": {k: v["formula"] for k, v in indices.INDEX_INFO.items()}}


def api_metrics(body, q):
    if not os.path.exists(METRICS):
        return {"available": False, "hint": "run: python -m agrisky.evaluate"}
    with open(METRICS, encoding="utf-8") as fh:
        m = json.load(fh)
    m.get("holdout", {}).pop("per_seed", None)
    m["available"] = True
    return m


def _export_parts(q):
    seed, fi, k = _common(q)
    a = STORE.analysis(seed, fi, k)
    return a, STORE.prescription(seed, fi, "pesticide", k), STORE.prescription(seed, fi, "urea", k)


def export_csv(body, q):
    a, p, u = _export_parts(q)
    name = "agrisky_prescription_flight%d.csv" % (a["index"] + 1)
    return ("text/csv; charset=utf-8", report.prescription_csv(a, p, u).encode("utf-8"), name)


def export_geojson(body, q):
    a, p, u = _export_parts(q)
    name = "agrisky_prescription_flight%d.geojson" % (a["index"] + 1)
    data = json.dumps(report.prescription_geojson(a, p, u), ensure_ascii=False).encode("utf-8")
    return ("application/geo+json; charset=utf-8", data, name)


GET_ROUTES = {
    "/api/health": lambda b, q: {"status": "ok", "app": "AgriSky",
                                 "time": _dt.datetime.now().isoformat(timespec="seconds")},
    "/api/meta": api_meta,
    "/api/flights": api_flights,
    "/api/scene": api_scene,
    "/api/field": api_field,
    "/api/zones": api_zones,
    "/api/change": api_change,
    "/api/prescription": api_prescription,
    "/api/mission": api_mission,
    "/api/report": api_report,
    "/api/metrics": api_metrics,
    "/api/export/prescription.csv": export_csv,
    "/api/export/prescription.geojson": export_geojson,
}
POST_ROUTES = {
    "/api/mission": api_mission,
    "/api/indices": api_indices,
}
FILE_ROUTES = {"/api/export/prescription.csv", "/api/export/prescription.geojson"}


class Handler(BaseHTTPRequestHandler):
    server_version = "AgriSky/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("AGRISKY_QUIET"):
            return
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    def _send(self, status, payload, ctype="application/json; charset=utf-8", filename=None):
        data = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
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
            res = fn(body, q)
            if path in FILE_ROUTES:
                ctype, data, name = res
                return self._send(200, data, ctype, filename=name if q.get("download") else None)
            self._send(200, res)
        except (InputError, PlanError) as e:
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
        if length < 0:
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


def ensure_data():
    os.makedirs(DATA, exist_ok=True)
    if not os.path.exists(SAMPLE):
        field.write_sample(SAMPLE)


def warm_cache():
    """Pre-compute the demo field so the first click in the UI is instant."""
    t0 = time.perf_counter()
    STORE.scene(config.DEFAULT_SEED, N_FLIGHTS - 1)
    return time.perf_counter() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description="AgriSky drone crop-health and spraying planner")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8018)
    args = ap.parse_args(argv)
    ensure_data()
    httpd = make_server(args.host, args.port)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("=" * 64)
    print("  AgriSky - drone crop-health maps and precision spraying")
    print("  Open  http://%s:%d/  in your browser" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP on a phone)")
    print("  Press Ctrl+C to stop.")
    print("=" * 64)
    sys.stdout.flush()

    def _warm():
        dt = warm_cache()
        print("  Demo field analysed (5 flights, zones, change, prescription, missions) in %.1fs"
              % dt)
        sys.stdout.flush()
    threading.Thread(target=_warm, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AgriSky. Nandri!")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
