#!/usr/bin/env python3
"""PlaceIQ - placement analytics that tells every student what to fix next.

Run:  python app.py [--host 127.0.0.1] [--port 8006]
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

from placeiq import config as C  # noqa: E402
from placeiq import data  # noqa: E402
from placeiq.engine import Engine  # noqa: E402

STATIC = os.path.join(HERE, "static")
MAX_BODY = 4 * 1024 * 1024
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".ico": "image/x-icon", ".json": "application/json", ".csv": "text/csv; charset=utf-8"}

ENGINE = None


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _float(qs, key, default, lo=None, hi=None):
    v = qs.get(key, [None])[0]
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except ValueError:
        raise ApiError(400, "%s must be a number" % key)
    if math.isnan(x) or (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ApiError(400, "%s must be between %s and %s" % (key, lo, hi))
    return x


def _str(qs, key):
    v = qs.get(key, [None])[0]
    return v.strip() if v else None


def _features_from(body):
    if not isinstance(body, dict):
        raise ApiError(400, "JSON object expected")
    src = body.get("features", body)
    if not isinstance(src, dict):
        raise ApiError(400, "'features' must be an object")
    x, problems = [], []
    for name, label, lo, hi, _ in C.FEATURES:
        v = src.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                problems.append("%s is missing or not a number" % name)
                continue
        if math.isnan(v) or v < lo or v > hi:
            problems.append("%s must be between %s and %s" % (name, lo, hi))
            continue
        x.append(float(v))
    if problems:
        raise ApiError(400, "; ".join(problems))
    return x


class Handler(BaseHTTPRequestHandler):
    server_version = "PlaceIQ/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, fmt % args))

    # ---------------------------------------------------------------- output
    def _send(self, status, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, allow_nan=False).encode("utf-8")
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
        self._send(status, obj, "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json({"error": message, "status": status}, status)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad Content-Length")
        if n > MAX_BODY:
            raise ApiError(413, "request body too large (max 4 MB)")
        return self.rfile.read(n) if n > 0 else b""

    def _json_body(self):
        raw = self._body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "body must be valid JSON")

    # ---------------------------------------------------------------- routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        url = urlparse(self.path)
        path, qs = url.path, parse_qs(url.query)
        try:
            if path.startswith("/api/"):
                with ENGINE.lock:
                    self._api(method, path, qs)
            elif method in ("GET", "HEAD"):
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
        dept, batch = _str(qs, "dept"), _str(qs, "batch")
        if dept and dept != "ALL" and dept not in C.DEPARTMENTS:
            raise ApiError(400, "unknown dept '%s'" % dept)
        get = method in ("GET", "HEAD")
        if path == "/api/health" and get:
            return self._json({"ok": True, "product": "PlaceIQ", "rows": len(E.rows), "time": time.time()})
        if path == "/api/dataset" and get:
            info = E.dataset_info()
            limit = int(_float(qs, "limit", 20, 0, 5000))
            info["sample"] = E.students(dept, batch, limit=limit)[:limit] if limit else []
            return self._json(info)
        if path == "/api/demo" and method == "POST":
            t = time.time()
            info = E.load_demo()
            info["message"] = "Demo cohort loaded and models retrained in %.1fs." % (time.time() - t)
            return self._json(info)
        if path == "/api/upload" and method == "POST":
            ctype = (self.headers.get("Content-Type") or "").lower()
            filename = _str(qs, "filename") or "upload.csv"
            if "json" in ctype:
                body = self._json_body()
                text = body.get("csv") if isinstance(body, dict) else None
                filename = (body.get("filename") if isinstance(body, dict) else None) or filename
                if not isinstance(text, str):
                    raise ApiError(400, "JSON body needs a 'csv' string")
            else:
                try:
                    text = self._body().decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise ApiError(400, "CSV must be UTF-8 text")
            ok, report, msg = E.load_csv(text, os.path.basename(str(filename))[:80])
            res = {"ok": ok, "message": msg, "report": report}
            if ok:
                res["dataset"] = E.dataset_info()
            return self._json(res, 200 if ok else 422)
        if path == "/api/sample.csv" and get:
            return self._send(200, data.to_csv(data.generate()), "text/csv; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="placeiq_demo_students.csv"'})
        if path == "/api/eda" and get:
            return self._json(E.eda())
        if path == "/api/model" and get:
            return self._json(E.model_info())
        if path == "/api/fairness" and get:
            return self._json(E.fairness(_float(qs, "threshold", 0.5, 0.01, 0.99)))
        if path == "/api/dashboard" and get:
            return self._json(E.dashboard(dept, batch, _float(qs, "threshold", C.DEFAULT_RISK_THRESHOLD, 0.01, 0.99)))
        if path == "/api/students" and get:
            limit = int(_float(qs, "limit", 1000, 1, 20000))
            return self._json({"students": E.students(dept, batch, _str(qs, "q"), limit)})
        if path.startswith("/api/student/") and get:
            sid = unquote(path[len("/api/student/"):])
            res = E.student(sid, _float(qs, "target", C.TARGET_PROBABILITY, 0.05, 0.95))
            if res is None:
                raise ApiError(404, "no student with id '%s'" % sid)
            return self._json(res)
        if path == "/api/predict" and method == "POST":
            body = self._json_body()
            x = _features_from(body)
            target = body.get("target", C.TARGET_PROBABILITY) if isinstance(body, dict) else C.TARGET_PROBABILITY
            if not isinstance(target, (int, float)) or not 0.05 <= target <= 0.95:
                raise ApiError(400, "target must be between 0.05 and 0.95")
            return self._json(E.explain_vector(x, float(target)))
        if path == "/api/at-risk" and get:
            thr = _float(qs, "threshold", C.DEFAULT_RISK_THRESHOLD, 0.01, 0.99)
            inc = _str(qs, "include_placed") in ("1", "true", "yes")
            rows = E.at_risk(thr, dept, batch, inc)
            return self._json({"threshold": thr, "count": len(rows), "students": rows})
        if path == "/api/at-risk.csv" and get:
            thr = _float(qs, "threshold", C.DEFAULT_RISK_THRESHOLD, 0.01, 0.99)
            inc = _str(qs, "include_placed") in ("1", "true", "yes")
            return self._send(200, E.at_risk_csv(thr, dept, batch, inc), "text/csv; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="placeiq_at_risk.csv"'})
        if path == "/api/clusters" and get:
            k = int(_float(qs, "k", C.DEFAULT_K, 2, 6))
            res = dict(E.clusters(k))
            res.pop("assignments", None)
            return self._json(res)
        if path.startswith("/api/"):
            known = {"/api/health", "/api/dataset", "/api/demo", "/api/upload", "/api/sample.csv", "/api/eda",
                     "/api/model", "/api/fairness", "/api/dashboard", "/api/students", "/api/predict",
                     "/api/at-risk", "/api/at-risk.csv", "/api/clusters"}
            if path in known or path.startswith("/api/student/"):
                raise ApiError(405, "method %s not allowed on %s" % (method, path))
            raise ApiError(404, "unknown endpoint %s" % path)


def main():
    global ENGINE
    ap = argparse.ArgumentParser(description="PlaceIQ placement analytics server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8006)
    args = ap.parse_args()
    t = time.time()
    print("PlaceIQ: generating demo cohort and training models ...", flush=True)
    ENGINE = Engine()
    ev = ENGINE.eval
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print("\n  =====================================================")
    print("   PlaceIQ - placement analytics that tells every")
    print("             student what to fix next")
    print("  -----------------------------------------------------")
    print("   %d students | test accuracy %.1f%% | ROC-AUC %.3f" % (len(ENGINE.rows), 100 * ev["accuracy"], ev["roc_auc"]))
    print("   ready in %.1fs" % (time.time() - t))
    print("   Open  http://%s:%d/" % (shown, args.port))
    if args.host == "0.0.0.0":
        print("   (listening on all interfaces - use this laptop's LAN IP from a phone)")
    print("   Ctrl+C to stop")
    print("  =====================================================\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nPlaceIQ stopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
