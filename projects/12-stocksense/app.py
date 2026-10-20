"""StockSense - demand forecasting and smart reordering for neighbourhood stores.

    python app.py [--host 127.0.0.1] [--port 8012]

Python 3.9+ standard library only. Serves the dashboard from static/ and a JSON API under /api/.
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from stocksense import config
from stocksense.dataset import ValidationError
from stocksense.engine import Engine

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
ENGINE = None
SKU_PATH = re.compile(r"^/api/sku/([A-Za-z0-9 _\-./&%]{1,80})$")

API_LIST = [
    ("GET", "/api/health", "liveness + dataset info"),
    ("GET", "/api/summary?service=0.95", "KPI tiles, accuracy, simulation headline, festival alert"),
    ("GET", "/api/trend", "store revenue history + 28-day forecast with 80% band"),
    ("GET", "/api/skus", "SKU list with class, chosen model and status"),
    ("GET", "/api/sku/<SKU>?service=0.95", "drill-down: history, all model forecasts, leaderboard, policy"),
    ("GET", "/api/leaderboard", "backtest leaderboard per model and per SKU + hold-out accuracy"),
    ("GET", "/api/reorder?service=0.95", "today's reorder list with risk and rupee impact"),
    ("GET", "/api/whatif?service=0.95", "service level vs cost trade-off curve"),
    ("GET", "/api/abcxyz", "ABC-XYZ matrix, Pareto curve, per-cell strategy"),
    ("GET", "/api/basket?min_support=0.02&min_confidence=0.3", "Apriori rules + shelf suggestions"),
    ("GET", "/api/simulation?service=0.95", "gut-feel vs StockSense over the last 90 days"),
    ("GET", "/api/festivals", "upcoming festival demand plan"),
    ("GET", "/api/sample.csv", "sample upload file (date,sku,qty,stockout,promo)"),
    ("POST", "/api/upload", "upload sales CSV (text/csv body or JSON {csv})"),
    ("POST", "/api/demo", "reload the deterministic demo dataset"),
    ("POST", "/api/stock", "set stock on hand: JSON {sku, on_hand, on_order}"),
]


def _service(qs):
    raw = (qs.get("service") or [""])[0].strip()
    if not raw:
        return config.SERVICE_LEVEL
    try:
        v = float(raw)
    except ValueError:
        raise ValidationError("service must be a number like 0.95")
    if v > 1:
        v /= 100.0
    if not 0.5 <= v <= 0.999:
        raise ValidationError("service level must be between 0.50 and 0.999")
    return round(v, 4)


def _float(qs, key, default, lo, hi):
    raw = (qs.get(key) or [""])[0].strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        raise ValidationError("%s must be a number" % key)
    if not lo <= v <= hi:
        raise ValidationError("%s must be between %s and %s" % (key, lo, hi))
    return v


class Handler(BaseHTTPRequestHandler):
    server_version = "StockSense/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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

    def _raw_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValidationError("bad Content-Length")
        if n < 0 or n > config.MAX_UPLOAD_BYTES + 1024:
            raise ValidationError("request body too large (limit %d MB)" % (config.MAX_UPLOAD_BYTES // 2 ** 20))
        return self.rfile.read(n) if n else b""

    def _json_body(self):
        raw = self._raw_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("body must be valid JSON")
        if not isinstance(data, dict):
            raise ValidationError("body must be a JSON object")
        return data

    def do_HEAD(self):
        self._dispatch("GET")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._error(405, "method not allowed")

    do_DELETE = do_PATCH = do_PUT

    def _dispatch(self, method):
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                return self._api(method, url.path, parse_qs(url.query))
            if method != "GET":
                return self._error(405, "method not allowed")
            return self._static(url.path)
        except ValidationError as exc:
            self._error(400, str(exc))
        except Exception:  # never crash the server on bad input
            traceback.print_exc()
            self._error(500, "internal error")

    def _api(self, method, path, qs):
        a = ENGINE.analysis
        if method == "GET":
            if path == "/api/health":
                return self._send(200, {"ok": True, "service": "stocksense", "source": a.ds.source,
                                        "skus": len(a.ds.skus), "days": a.ds.n, "today": a.today.isoformat(),
                                        "build_seconds": a.build_seconds, "endpoints": [
                                            {"method": m, "path": p, "desc": d} for m, p, d in API_LIST]})
            if path == "/api/summary":
                return self._send(200, a.summary(_service(qs)))
            if path == "/api/trend":
                return self._send(200, a.trend())
            if path == "/api/skus":
                return self._send(200, {"skus": a.skus(_service(qs))})
            m = SKU_PATH.match(path)
            if m:
                sku = unquote(m.group(1))
                detail = a.sku_detail(sku, _service(qs))
                if detail is None:
                    return self._error(404, "unknown SKU %r" % sku[:40])
                return self._send(200, detail)
            if path == "/api/leaderboard":
                return self._send(200, a.leaderboard())
            if path == "/api/reorder":
                return self._send(200, a.plan(_service(qs)))
            if path == "/api/whatif":
                return self._send(200, a.whatif(_service(qs)))
            if path == "/api/abcxyz":
                return self._send(200, a.abc)
            if path == "/api/basket":
                sup = _float(qs, "min_support", config.MIN_SUPPORT, 0.005, 0.5)
                conf = _float(qs, "min_confidence", config.MIN_CONFIDENCE, 0.05, 1.0)
                return self._send(200, a.basket(round(sup, 4), round(conf, 4)))
            if path == "/api/simulation":
                return self._send(200, a.simulation(_service(qs)))
            if path == "/api/festivals":
                return self._send(200, {"today": a.today.isoformat(), "festivals": a.festival_plan()})
            if path == "/api/sample.csv":
                return self._send(200, ENGINE.sample_csv(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="stocksense_sample.csv"'})
            return self._error(404, "unknown endpoint")
        if method == "POST":
            if path == "/api/upload":
                ctype = (self.headers.get("Content-Type") or "").lower()
                if "json" in ctype:
                    text = self._json_body().get("csv")
                    if not isinstance(text, str):
                        raise ValidationError("JSON body must contain a 'csv' string")
                else:
                    try:
                        text = self._raw_body().decode("utf-8-sig")
                    except UnicodeDecodeError:
                        raise ValidationError("CSV must be UTF-8 text")
                t0 = time.time()
                new = ENGINE.load_csv(text)
                return self._send(200, {"ok": True, "skus": len(new.ds.skus), "days": new.ds.n,
                                        "start": new.ds.dates[0].isoformat(), "end": new.ds.dates[-1].isoformat(),
                                        "warnings": new.ds.warnings, "seconds": round(time.time() - t0, 2),
                                        "stockouts_detected": sum(new.ds.detected.values())
                                        if not new.ds.stockout_given else None})
            if path == "/api/demo":
                new = ENGINE.load_demo()
                return self._send(200, {"ok": True, "skus": len(new.ds.skus), "days": new.ds.n,
                                        "seconds": new.build_seconds})
            if path == "/api/stock":
                body = self._json_body()
                sku = body.get("sku")
                if not isinstance(sku, str) or sku not in a.ds.items:
                    raise ValidationError("unknown sku")
                vals = []
                for key in ("on_hand", "on_order"):
                    v = body.get(key, 0)
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1e6:
                        raise ValidationError("%s must be a number between 0 and 1,000,000" % key)
                    vals.append(int(v))
                ENGINE.set_stock(sku, vals[0], vals[1])
                return self._send(200, {"ok": True, "sku": sku, "on_hand": vals[0], "on_order": vals[1]})
            return self._error(404, "unknown endpoint")
        return self._error(405, "method not allowed")

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = os.path.normpath(unquote(path).lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            return self._error(404, "not found")
        full = os.path.join(STATIC, rel)
        if not os.path.isfile(full):
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


def main(argv=None):
    global ENGINE
    ap = argparse.ArgumentParser(description="StockSense demo server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8012)
    args = ap.parse_args(argv)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    t0 = time.time()
    print("StockSense: building forecasts, backtests and simulation ...", flush=True)
    ENGINE = Engine(DATA)
    a = ENGINE.analysis
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("\n  StockSense - %s" % config.TAGLINE)
    print("  %d SKUs x %d days analysed in %.1fs (4 models, rolling backtests, 90-day simulation)"
          % (len(a.ds.skus), a.ds.n, time.time() - t0))
    print("  Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("  (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("  Ctrl+C to stop.\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
