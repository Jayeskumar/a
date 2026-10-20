"""Measure model accuracy and per-request latency; writes data/metrics.json.

Run from the project folder:  python -m krishimitra.evaluate
"""
import datetime as _dt
import json
import os
import platform
import statistics
import threading
import time
import urllib.request

from . import config, dataset, fertiliser, irrigation, market, recommender, weather
from .advisor import advise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _timeit(fn, n):
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 3), "n": n}


def confusion_summary(model, Xte, yte, k=6):
    pairs = {}
    per_crop = {c: [0, 0, 0] for c in config.CROPS}
    for x, t in zip(Xte, yte):
        p = model.rf.predict(x)
        g = model.gnb.predict(x)
        per_crop[t][0] += int(p == t)
        per_crop[t][1] += int(g == t)
        per_crop[t][2] += 1
        if p != t:
            pairs[(t, p)] = pairs.get((t, p), 0) + 1
    worst = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return ({c: {"rf": round(v[0] / float(v[2]), 3), "gnb": round(v[1] / float(v[2]), 3)}
             for c, v in per_crop.items()},
            [{"true": a, "predicted": b, "count": c} for (a, b), c in worst])


def http_latency(body, n):
    import app  # local import: app.py lives in the project root
    httpd = app.make_server("127.0.0.1", 0)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    data = json.dumps(body).encode()

    def post(path, payload):
        r = urllib.request.Request(base + path, data=payload,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=10) as resp:
            resp.read()

    rec_payload = json.dumps({f: body[f] for f in config.FEATURES}).encode()
    post("/api/advise", data)   # warm-up
    out = {
        "POST /api/advise": _timeit(lambda: post("/api/advise", data), n),
        "POST /api/recommend": _timeit(lambda: post("/api/recommend", rec_payload), n),
    }
    httpd.shutdown()
    httpd.server_close()
    return out


def main():
    os.environ.setdefault("KM_QUIET", "1")
    t0 = time.perf_counter()
    model = recommender.CropRecommender()
    train_s = time.perf_counter() - t0
    recommender._model = model          # reuse for advise() / HTTP timing
    X, y = dataset.generate()
    _, _, Xte, yte = dataset.stratified_split(X, y)
    per_crop, confused = confusion_summary(model, Xte, yte)

    p = config.PRESETS[0]
    inputs = p["inputs"]
    x = [inputs[f] for f in config.FEATURES]
    today = _dt.date(2026, 10, 20)
    sow = today - _dt.timedelta(days=p["sowing_days_ago"])
    fc = weather.synth_forecast(p["lat"], today)
    body = dict(inputs, lat=p["lat"], soil=p["soil"], method=p["method"],
                area_acres=p["area_acres"], sowing_date=sow.isoformat(),
                start_date=today.isoformat())
    n = 300
    latency = {
        "gnb.predict_proba": _timeit(lambda: model.gnb.predict_proba(x), n),
        "rf.predict_proba (30 trees)": _timeit(lambda: model.rf.predict_proba(x), n),
        "recommend (both models + explanation)": _timeit(lambda: model.recommend(inputs), n),
        "fertiliser.advise": _timeit(lambda: fertiliser.advise("groundnut", 28, 55, 38, 6.9, 2), n),
        "irrigation.plan (7 days)": _timeit(
            lambda: irrigation.plan("groundnut", p["lat"], sow, today, fc, "red", "drip", 2), n),
        "market.analyse": _timeit(lambda: market.analyse("groundnut", today), n),
        "advise (all modules)": _timeit(lambda: advise(body, today=today), n),
    }
    latency.update(http_latency(body, 100))
    m = dict(model.metrics)
    m.update({
        "full_training_s": round(train_s, 3),
        "per_crop_accuracy": per_crop,
        "most_confused_rf": confused,
        "latency": latency,
        "machine": "%s, Python %s" % (platform.platform(terse=True), platform.python_version()),
        "measured_on": _dt.date.today().isoformat(),
    })
    out = os.path.join(ROOT, "data", "metrics.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)
    print("GNB hold-out accuracy   %.2f%%" % (m["gnb_accuracy"] * 100))
    print("RF  hold-out accuracy   %.2f%%  (OOB %.2f%%)" % (m["rf_accuracy"] * 100, m["rf_oob_accuracy"] * 100))
    print("Blend hold-out accuracy %.2f%%" % (m["blend_accuracy"] * 100))
    print("Top-3 accuracy GNB %.2f%%, RF %.2f%%" % (m["gnb_top3_accuracy"] * 100, m["rf_top3_accuracy"] * 100))
    print("Training: GNB %.1f ms, RF %.1f ms" % (m["gnb_train_ms"], m["rf_train_ms"]))
    for k, v in latency.items():
        print("  %-40s median %7.3f ms   p95 %7.3f ms" % (k, v["median_ms"], v["p95_ms"]))
    print("most confused (RF):", confused)
    print("wrote", out)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    main()
