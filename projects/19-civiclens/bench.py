#!/usr/bin/env python3
"""Offline benchmark for REPORT.md: python bench.py  (takes about a minute, writes data/bench.json)

1. Routing on *unseen complaint templates* (harder than the random incident split)
2. Feature ablation for the routing model
3. MinHash estimation error vs number of permutations
4. Hotspot parameters chosen on two *other* towns (seeds), then scored on the demo town
5. Robustness: every headline metric on three different random towns
6. Latency: full pipeline per complaint, in-process and over HTTP
"""

import json
import os
import random
import statistics
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from civiclens import config as C  # noqa: E402
from civiclens import metrics as M  # noqa: E402
from civiclens.dedup import MinHasher  # noqa: E402
from civiclens.engine import Engine  # noqa: E402
from civiclens.features import TfidfVectorizer  # noqa: E402
from civiclens.models import MultinomialNB, OneVsRest  # noqa: E402
from civiclens.text import jaccard  # noqa: E402

DEPT = {d: i for i, d in enumerate(C.DEPT_CODES)}


def routing_unseen_templates(E):
    """Hold out one template per (issue, language) that has >= 2 templates; train on the rest."""
    cs = E.complaints
    by = {}
    for c in cs:
        if c["tpl"] == "vague":
            continue
        key, lang, idx = c["tpl"].rsplit(":", 2)
        by.setdefault((key, lang), set()).add(int(idx))
    held = {"%s:%s:%d" % (k[0], k[1], max(v)) for k, v in by.items() if len(v) >= 2}
    te = [i for i, c in enumerate(cs) if c["tpl"] in held]
    tr = [i for i, c in enumerate(cs) if c["tpl"] not in held and c["tpl"] != "vague"]
    y = [DEPT[c["dept"]] for c in cs]
    yt = [y[i] for i in te]
    out = {"held_out_templates": len(held), "n_train": len(tr), "n_test": len(te), "ablation": []}
    for blocks, label in ((("w",), "words only"), (("w", "c"), "words + grapheme n-grams"),
                          (("w", "k"), "words + concepts"), (("w", "c", "k"), "all three (served)")):
        vec = TfidfVectorizer(blocks=blocks).fit([E.terms[i] for i in tr])
        X = {i: vec.transform_one(E.terms[i]) for i in tr + te}
        lr = OneVsRest(8, vec.n_features, epochs=C.LR_EPOCHS, lr=C.LR_RATE, l2=C.LR_L2, seed=C.SEED).fit([X[i] for i in tr], [y[i] for i in tr])
        nb = MultinomialNB(8, vec.n_features, C.NB_ALPHA).fit([vec.counts_one(E.terms[i]) for i in tr], [y[i] for i in tr])
        pl = [lr.predict(X[i]) for i in te]
        pn = [nb.predict(vec.counts_one(E.terms[i])) for i in te]
        row = {"features": label, "lr_accuracy": round(M.accuracy(yt, pl), 3), "lr_macro_f1": round(M.macro_f1(yt, pl, 8), 3),
               "nb_accuracy": round(M.accuracy(yt, pn), 3), "nb_macro_f1": round(M.macro_f1(yt, pn, 8), 3)}
        out["ablation"].append(row)
    out.update({k: v for k, v in out["ablation"][-1].items() if k != "features"})
    return out


def ablation(E):
    y = [DEPT[c["dept"]] for c in E.complaints]
    out = []
    for blocks, label in ((("w",), "words only"), (("w", "c"), "words + grapheme n-grams"),
                          (("w", "k"), "words + concepts"), (("w", "c", "k"), "words + grapheme n-grams + concepts")):
        vec = TfidfVectorizer(blocks=blocks).fit([E.terms[i] for i in E.tr])
        Xtr = [vec.transform_one(E.terms[i]) for i in E.tr]
        Xte = [vec.transform_one(E.terms[i]) for i in E.te]
        t = time.time()
        lr = OneVsRest(8, vec.n_features, epochs=C.LR_EPOCHS, lr=C.LR_RATE, l2=C.LR_L2, seed=C.SEED).fit(Xtr, [y[i] for i in E.tr])
        secs = time.time() - t
        yt = [y[i] for i in E.te]
        p = [lr.predict(x) for x in Xte]
        ta = [k for k, i in enumerate(E.te) if E.complaints[i]["lang"] == "ta"]
        out.append({"features": label, "n_features": vec.n_features, "accuracy": round(M.accuracy(yt, p), 3),
                    "macro_f1": round(M.macro_f1(yt, p, 8), 3),
                    "tamil_accuracy": round(M.accuracy([yt[k] for k in ta], [p[k] for k in ta]), 3), "train_s": round(secs, 2)})
    return out


def minhash_error(E):
    rng = random.Random(5)
    n = len(E.complaints)
    pairs = []
    for i in range(n):                       # candidate-like pairs: same predicted dept, nearby in time
        for j in range(max(0, i - 40), i):
            if E.complaints[i]["pred_dept"] == E.complaints[j]["pred_dept"]:
                pairs.append((i, j))
    pairs = rng.sample(pairs, min(3000, len(pairs)))
    out = []
    for k in (16, 32, 64, 128):
        mh = MinHasher(k, seed=11)
        sig = {}
        errs = []
        for i, j in pairs:
            for a in (i, j):
                if a not in sig:
                    sig[a] = mh.signature(E.shingles[a])
            errs.append(abs(MinHasher.similarity(sig[i], sig[j]) - jaccard(E.shingles[i], E.shingles[j])))
        out.append({"permutations": k, "mae": round(sum(errs) / len(errs), 4), "p95_error": round(M.percentile(errs, 0.95), 3)})
    return out


def hotspot_grid(E):
    grid = []
    for eps in (100, 120, 140, 160):
        for mp in range(7, 15):
            h = E.hotspots(None, eps, mp)
            persistent = [p for p in E.planted if p["kind"] == "persistent"]
            found = {c["planted"] for c in h["clusters"] if c["planted"]}
            prec = sum(1 for c in h["clusters"] if c["planted"]) / float(len(h["clusters"])) if h["clusters"] else 0.0
            rec = sum(1 for p in persistent if p["id"] in found) / float(len(persistent))
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            grid.append({"eps": eps, "min_pts": mp, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                         "clusters": len(h["clusters"])})
    return grid


def headline(E):
    r = E.routing_eval["models"]
    u = E.urgency_eval["variants"]["combined"]
    return {"complaints": len(E.complaints), "routing_lr_acc": r["lr"]["accuracy"], "routing_lr_f1": r["lr"]["macro_f1"],
            "routing_nb_acc": r["nb"]["accuracy"], "urgency_acc": u["accuracy"], "p1_recall": u["p1_recall"],
            "dup_f1": E.dup_eval["pairwise"]["f1"], "dup_precision": E.dup_eval["pairwise"]["precision"],
            "dup_recall": E.dup_eval["pairwise"]["recall"], "hotspot_precision": E.hotspot_eval["precision"],
            "hotspot_recall": E.hotspot_eval["persistent_recall"], "surges_found": len(E.emerging_eval["surges_detected"]),
            "false_flags": E.emerging_eval["false_flags"], "breach_auc": E.breach_eval["auc"],
            "build_s": E.timings["total_build_s"]}


def latency(E):
    cs = E.complaints
    texts = [(cs[i]["text"], cs[i]["lat"], cs[i]["lon"], cs[i]["channel"]) for i in E.te[:300]]
    ms = []
    for t in texts:
        t0 = time.perf_counter()
        E.analyze(*t, record=False)
        ms.append((time.perf_counter() - t0) * 1000)
    import app
    app.ENGINE = E
    srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    port = srv.server_address[1]
    http_ms = []
    for t in texts[:150]:
        body = json.dumps({"text": t[0], "lat": t[1], "lon": t[2], "channel": t[3]}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:%d/api/analyze" % port, data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req) as r:
            r.read()
        http_ms.append((time.perf_counter() - t0) * 1000)
    srv.shutdown()
    return {"n": len(ms), "pipeline_p50_ms": round(statistics.median(ms), 2), "pipeline_p95_ms": round(M.percentile(ms, 0.95), 2),
            "http_p50_ms": round(statistics.median(http_ms), 2), "http_p95_ms": round(M.percentile(http_ms, 0.95), 2)}


def main():
    t_all = time.time()
    res = {}
    print("building the demo town (seed %d) ..." % C.SEED, flush=True)
    E = Engine(replay=False)
    res["headline_seed_%d" % C.SEED] = headline(E)
    print("routing on unseen templates ...", flush=True)
    res["routing_unseen_templates"] = routing_unseen_templates(E)
    print("feature ablation ...", flush=True)
    res["routing_ablation"] = ablation(E)
    print("MinHash error ...", flush=True)
    res["minhash_error"] = minhash_error(E)
    print("latency ...", flush=True)
    res["latency"] = latency(E)
    demo_grid = hotspot_grid(E)
    val = {}
    for seed in (C.SEED + 1, C.SEED + 2):
        print("validation town seed %d ..." % seed, flush=True)
        V = Engine(replay=False, seed=seed)
        res["headline_seed_%d" % seed] = headline(V)
        for g in hotspot_grid(V):
            val.setdefault((g["eps"], g["min_pts"]), []).append(g["f1"])
    best = max(val.items(), key=lambda kv: (sum(kv[1]) / len(kv[1]), -kv[0][1]))
    (eps, mp), f1s = best
    on_demo = next(g for g in demo_grid if g["eps"] == eps and g["min_pts"] == mp)
    res["hotspot_param_selection"] = {"chosen_on_validation": {"eps": eps, "min_pts": mp, "mean_val_f1": round(sum(f1s) / len(f1s), 3)},
                                      "score_on_demo_town": on_demo,
                                      "default_on_demo_town": next(g for g in demo_grid if g["eps"] == C.DBSCAN_EPS_M and g["min_pts"] == C.DBSCAN_MIN_PTS)}
    res["total_s"] = round(time.time() - t_all, 1)
    with open(os.path.join(HERE, "data", "bench.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
