"""HTTP latency benchmark: python bench.py  -> adds "http" to data/metrics.json.

Starts the server in-process on a free port, warms the cache once, then times each endpoint.
"""
import json
import os
import statistics
import threading
import time
import urllib.request

os.environ["AGRISKY_QUIET"] = "1"
import app  # noqa: E402

N = 15


def main():
    httpd = app.make_server("127.0.0.1", 0)
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    t0 = time.perf_counter()
    app.warm_cache()
    cold = time.perf_counter() - t0
    mission_body = json.dumps({"flight": 5, "tank": 3, "swath": 5}).encode()
    cases = [
        ("GET /api/scene (all layers, flight 5)", "/api/scene?flight=5", None),
        ("GET /api/zones", "/api/zones?flight=5", None),
        ("GET /api/change", "/api/change?flight=5", None),
        ("GET /api/prescription", "/api/prescription?flight=5&product=urea", None),
        ("POST /api/mission (new params, uncached first)", "/api/mission", mission_body),
        ("GET /api/report", "/api/report?flight=5", None),
        ("GET /api/export/prescription.csv", "/api/export/prescription.csv?flight=5", None),
        ("GET /api/export/prescription.geojson", "/api/export/prescription.geojson?flight=5", None),
    ]
    out = {"cold_start_s": round(cold, 2), "requests": N, "endpoints": {}}
    for name, path, body in cases:
        times = []
        size = 0
        for _ in range(N):
            req = urllib.request.Request(base + path, data=body)
            if body:
                req.add_header("Content-Type", "application/json")
            t = time.perf_counter()
            with urllib.request.urlopen(req) as r:
                size = len(r.read())
            times.append((time.perf_counter() - t) * 1000)
        out["endpoints"][name] = {"median_ms": round(statistics.median(times), 1),
                                  "first_ms": round(times[0], 1),
                                  "max_ms": round(max(times), 1), "bytes": size}
        print("%-48s median %6.1f ms  first %6.1f ms  %7d bytes" %
              (name, statistics.median(times), times[0], size))
    httpd.shutdown()
    httpd.server_close()
    path = os.path.join(app.DATA, "metrics.json")
    m = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    m["http"] = out
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1, ensure_ascii=False)
    print("cold start (5 flights analysed + missions): %.2fs; wrote %s" % (cold, path))


if __name__ == "__main__":
    main()
