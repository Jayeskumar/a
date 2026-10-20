"""Measure everything quoted in REPORT.md. Run:  python -m mindease.evaluation

Writes data/evaluation.json. Numbers come from the hand-labelled sets in eval_sets.py
(written by the team, see that file for the protocol) and from simulation. None of them
come from real students.
"""

import datetime as _dt
import json
import os
import random
import statistics
import sys
import time

from . import (config, counsellor, demo_data, eval_sets, planner, questionnaires, safety,
               sentiment, trends)

LABELS = ["positive", "negative", "neutral"]
SHORT = {"pos": "positive", "neg": "negative", "neu": "neutral"}

NEGATION_PAIRS = [
    ("I am happy", "positive"), ("I am not happy", "negative"),
    ("That was bad", "negative"), ("That was not bad", "positive"),
    ("I feel stressed", "negative"), ("I don't feel stressed", "positive"),
    ("I was anxious", "negative"), ("I wasn't anxious at all", "positive"),
    ("Nalla iruku", "positive"), ("Nalla illa", "negative"),
    ("I enjoyed the class", "positive"), ("I never enjoyed the class", "negative"),
    ("I am not stressed out", "positive"), ("No worries today", "positive"),
    ("I couldn't sleep", "negative"), ("I slept well", "positive"),
]


def _metrics(pairs):
    """pairs: list of (gold, predicted) with labels in LABELS."""
    conf = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in pairs:
        conf[g][p] += 1
    n = len(pairs)
    acc = sum(conf[l][l] for l in LABELS) / n if n else 0.0
    per = {}
    for l in LABELS:
        tp = conf[l][l]
        fp = sum(conf[g][l] for g in LABELS if g != l)
        fn = sum(conf[l][p] for p in LABELS if p != l)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[l] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                  "support": tp + fn}
    flips = sum(1 for g, p in pairs if {g, p} == {"positive", "negative"})
    return {"n": n, "accuracy": round(acc, 3),
            "macro_f1": round(sum(per[l]["f1"] for l in LABELS) / 3, 3),
            "per_class": per, "confusion": conf, "polarity_flips": flips}


def sentiment_eval():
    out = {}
    sets = {"dev": eval_sets.SENTIMENT_DEV, "heldout": eval_sets.SENTIMENT_HELDOUT,
            "fresh": eval_sets.SENTIMENT_FRESH}
    untuned = []
    untuned_base = []
    for name, ds in sets.items():
        pairs, base, errors = [], [], []
        for text, gold in ds:
            g = SHORT[gold]
            r = sentiment.analyse(text, with_tokens=False)
            pairs.append((g, r["label"]))
            base.append((g, sentiment.baseline_label(text)))
            if r["label"] != g:
                errors.append({"text": text, "gold": g, "predicted": r["label"],
                               "compound": r["compound"]})
        m = _metrics(pairs)
        m["baseline_accuracy"] = _metrics(base)["accuracy"]
        m["errors"] = errors
        out[name] = m
        if name != "dev":
            untuned += pairs
            untuned_base += base
    allm = _metrics(untuned)
    allm["baseline_accuracy"] = _metrics(untuned_base)["accuracy"]
    out["untuned_combined"] = allm
    neg_ok = [(t, want, sentiment.analyse(t, with_tokens=False)["label"])
              for t, want in NEGATION_PAIRS]
    out["negation_checks"] = {"passed": sum(1 for _, w, g in neg_ok if w == g),
                              "total": len(neg_ok),
                              "failures": [{"text": t, "want": w, "got": g}
                                           for t, w, g in neg_ok if w != g]}
    return out


def _safety_set(ds, cooc=True):
    tp = fn = fp = tn = 0
    misses, false_alarms = [], []
    for text, gold in ds:
        flagged = safety.detect(text, cooccurrence=cooc)["flagged"]
        if gold and flagged:
            tp += 1
        elif gold:
            fn += 1
            misses.append(text)
        elif flagged:
            fp += 1
            false_alarms.append(text)
        else:
            tn += 1
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "sensitivity": round(tp / (tp + fn), 3) if tp + fn else None,
            "specificity": round(tn / (tn + fp), 3) if tn + fp else None,
            "misses": misses, "false_alarms": false_alarms}


def safety_eval():
    sets = {"heldout_direct": eval_sets.SAFETY_HELDOUT,
            "fresh_indirect": eval_sets.SAFETY_FRESH,
            "check3": eval_sets.SAFETY_CHECK3}
    out = {name: _safety_set(ds) for name, ds in sets.items()}
    out["ablation_no_cooccurrence"] = {name: _safety_set(ds, cooc=False)
                                       for name, ds in sets.items()}
    out["first_run_history"] = {
        "heldout_direct": "24/24 caught, 0/22 false alarms (phrase rules only)",
        "fresh_indirect": "0/12 caught, 1/8 false alarm (phrase rules only) - this "
                          "motivated the co-occurrence layer and 6 new phrase rules",
        "check3": "8/10 caught, 0/10 false alarms (first run with co-occurrence layer)",
    }
    # item-9 rule: every combination of item 9 > 0 must show support, whatever the total
    combos = 0
    ok = 0
    for item9 in range(4):
        for other in range(4):
            answers = [other] * 8 + [item9]
            r = questionnaires.score("phq9", answers)
            combos += 1
            ok += r["support"]["show"] == (item9 > 0)
    out["item9_rule"] = {"combinations": combos, "correct": ok}
    return out


def _sim_series(rng, n_days, dip_from=None, delta=0.0, mu=3.8, sigma=0.7):
    vals = []
    for d in range(n_days):
        m = mu - (delta if dip_from is not None and d >= dip_from else 0.0)
        vals.append(max(1, min(5, int(round(rng.gauss(m, sigma))))))
    return vals


def _fires(series_vals, start_date):
    rows = [{"date": (start_date + _dt.timedelta(days=i)).isoformat(), "mood": v,
             "sleep": None, "sentiment": None} for i, v in enumerate(series_vals)]
    d = trends.detect_metric(rows, "mood")
    if not d.get("ready"):
        return {"rule": False, "run3": False, "cusum": False, "slope": False}
    return {"rule": trends.dip_decision(d), "run3": d["dip_run"]["length"] >= 3,
            "cusum": d["cusum"]["alarm_date"] is not None,
            "slope": bool((d["slope"] or {}).get("significant_down"))}


def trend_eval(n=300, seed=101):
    """Simulated 28-day mood journals: 21 normal days, then 7 days with or without a dip.

    Seed 7 was used to choose the rule and h (tuning); seed 101 is the held-out report."""
    rng = random.Random(seed)
    start = _dt.date(2026, 1, 1)
    base_days, mon = 21, 7
    out = {"seed": seed, "n_series_per_condition": n, "baseline_days": base_days,
           "watch_days": mon,
           "mood_model": "integer mood = round(N(3.8, 0.7)) clipped to 1-5", "conditions": {}}
    for label, delta in (("no_dip", 0.0), ("dip_1.0", 1.0), ("dip_1.5", 1.5)):
        det = {"rule": 0, "run3": 0, "cusum": 0, "slope": 0}
        delays = []
        for _ in range(n):
            vals = _sim_series(rng, base_days + mon, dip_from=base_days if delta else None,
                               delta=delta)
            first = {k: None for k in det}
            for k in range(1, mon + 1):
                f = _fires(vals[:base_days + k], start)
                for key in det:
                    if f[key] and first[key] is None:
                        first[key] = k
            for key in det:
                if first[key] is not None:
                    det[key] += 1
            if first["rule"] is not None:
                delays.append(first["rule"])
        cond = {key: round(det[key] / n, 3) for key in det}
        cond["median_delay_days"] = statistics.median(delays) if delays else None
        out["conditions"][label] = cond
    out["note"] = ("'rule' is what the app uses (CUSUM alarm + latest 2 days below usual). "
                   "run3 / cusum / slope are each detector alone. For no_dip, each value is "
                   "the share of journals with any alert in a 7-day window, i.e. a "
                   "false-alarm rate per week.")
    out["superseded_rule"] = ("first version: run >= 3 OR (CUSUM h=4 + 2-day run) OR (slope + "
                              "2-day run) - tuning seed 7: 21% false alarms/week, 78% of "
                              "1-point dips, 96% of 1.5-point dips")
    return out


def _time(fn, reps):
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps


def latency_eval():
    texts = [t for t, _ in eval_sets.SENTIMENT_HELDOUT] + \
        [e[2] for e in demo_data.ANANYA_JOURNAL]
    state = demo_data.build_state(end_date=demo_data.FIXED_END_DATE)
    journal = state["student"]["journal"]
    k = [0]

    def one_text():
        k[0] = (k[0] + 1) % len(texts)
        return texts[k[0]]

    plan_body = {"exams": [{"subject": "Maths", "date": "2026-11-02", "confidence": 2},
                           {"subject": "Physics", "date": "2026-11-04", "confidence": 3},
                           {"subject": "Electronics", "date": "2026-11-06", "confidence": 4}],
                 "start_date": "2026-10-23", "hours_per_day": 4, "start_time": "17:30"}
    res = {
        "sentiment_analyse_us": _time(lambda: sentiment.analyse(one_text()), 3000) * 1e6,
        "safety_detect_us": _time(lambda: safety.detect(one_text()), 3000) * 1e6,
        "phq9_score_us": _time(lambda: questionnaires.score(
            "phq9", [1, 2, 0, 1, 3, 0, 1, 2, 0]), 20000) * 1e6,
        "trends_analyse_21d_ms": _time(lambda: trends.analyse(journal), 200) * 1e3,
        "counsellor_dashboard_ms": _time(lambda: counsellor.dashboard(
            json.loads(json.dumps(state)), "2026-10-23"), 50) * 1e3,
        "planner_14d_ms": _time(lambda: planner.plan(plan_body,
                                                     today=_dt.date(2026, 10, 23)), 50) * 1e3,
    }
    return {k2: round(v, 2) for k2, v in res.items()}


def http_latency(reps=200):
    """Round-trip latency of the real HTTP handler on localhost (temp state file)."""
    import tempfile
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    import app  # noqa: E402
    from .store import Store
    tmp = tempfile.mkdtemp()
    app.STORE = Store(os.path.join(tmp, "state.json"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    body = json.dumps({"text": "Romba stressed. Skipped lunch to study and still feel "
                               "behind"}).encode()

    def post():
        r = urllib.request.Request(base + "/api/analyze", data=body, method="POST",
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r).read()

    def get():
        urllib.request.urlopen(base + "/api/student").read()

    out = {}
    for name, fn in (("post_analyze", post), ("get_student", get)):
        times = []
        for _ in range(reps):
            t0 = time.perf_counter()
            fn()
            times.append((time.perf_counter() - t0) * 1e3)
        times.sort()
        out[name + "_ms"] = {"median": round(statistics.median(times), 2),
                             "p95": round(times[int(0.95 * len(times)) - 1], 2)}
    srv.shutdown()
    srv.server_close()
    return out


def evaluate(include_http=False):
    res = {"sentiment": sentiment_eval(), "safety": safety_eval(),
           "trends": trend_eval(seed=101), "trends_tuning": trend_eval(seed=7),
           "latency": latency_eval(), "python": sys.version.split()[0]}
    if include_http:
        res["http"] = http_latency()
    return res


def main():
    res = evaluate(include_http=True)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "data", "evaluation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    s = res["sentiment"]
    print("Sentiment accuracy: dev %.0f%%, held-out %.0f%%, fresh %.0f%%, untuned "
          "combined %.0f%% (baseline %.0f%%)" % (
              100 * s["dev"]["accuracy"], 100 * s["heldout"]["accuracy"],
              100 * s["fresh"]["accuracy"], 100 * s["untuned_combined"]["accuracy"],
              100 * s["untuned_combined"]["baseline_accuracy"]))
    print("Negation checks: %d/%d" % (s["negation_checks"]["passed"],
                                      s["negation_checks"]["total"]))
    for name in ("heldout_direct", "fresh_indirect", "check3"):
        x = res["safety"][name]
        print("Safety %-15s sensitivity %d/%d  false alarms %d/%d" % (
            name, x["tp"], x["tp"] + x["fn"], x["fp"], x["fp"] + x["tn"]))
    print("Trend detector:", json.dumps(res["trends"]["conditions"]))
    print("Latency:", json.dumps(res["latency"]))
    print("HTTP:", json.dumps(res["http"]))
    print("wrote", path)


if __name__ == "__main__":
    main()
