"""Reproducible evaluation for REPORT.md.

    python -m schemesetu.evaluate                    # writes data/evaluation.json
    python -m schemesetu.evaluate --http http://127.0.0.1:8011   # also time live API calls

Measures, on the 4 demo families + a hold-out synthetic population (different
seed from the one the answer priors are learnt from):
  * questions asked per household for each selection strategy vs the full form
  * correctness: final decisions identical to evaluating the complete profile
  * how much of a family's eligibility is already known after k questions
  * search hit@1 / hit@3 on a hand-written bilingual query set
  * latency of evaluate / next-question / search / full simulation
"""
import argparse
import json
import os
import statistics
import sys
import time

from . import config, synth
from .engine import Engine

SEARCH_QUERIES = [
    ("பயிர் காப்பீடு", ["pmfby"]),
    ("pension for widow", ["ignwps"]),
    ("house", ["pmay_g"]),
    ("கழிப்பறை", ["sbm_g"]),
    ("gas cylinder", ["ujjwala"]),
    ("scholarship for college girl", ["pudhumai_penn"]),
    ("முதியோர் ஓய்வூதியம்", ["ignoaps"]),
    ("crop loan", ["kcc"]),
    ("hospital treatment", ["pm_jay", "cmchis"]),
    ("100 days work", ["mgnrega"]),
    ("கர்ப்பிணி பெண்", ["pmmvy"]),
    ("விபத்துக் காப்பீடு", ["pmsby"]),
    ("soil test", ["soil_health_card"]),
    ("மகளிர் உரிமைத் தொகை", ["kmut"]),
    ("self help group loan", ["nrlm_shg"]),
    ("farmer pension", ["pm_kmy"]),
    ("life insurance", ["pmjjby"]),
    ("disabled pension", ["igndps"]),
    ("விவசாயி நிதி உதவி", ["pm_kisan"]),
    ("வீடு கட்ட உதவி", ["pmay_g"]),
    ("கைம்பெண் ஓய்வூதியம்", ["ignwps"]),
    ("மருத்துவக் காப்பீடு", ["pm_jay", "cmchis"]),
    ("எரிவாயு இணைப்பு", ["ujjwala"]),
    ("கல்வி உதவித்தொகை கல்லூரி", ["post_matric_scst", "pudhumai_penn", "nmmss"]),
]

LABELS = {"ig": "Greedy information gain", "resolve": "Greedy expected-resolved", "static": "Fixed order + skip logic"}


def _ms(fn, reps):
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def _summ(xs):
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]
    return {"mean": round(statistics.mean(xs), 2), "p95": round(p95, 2), "max": round(xs[-1], 2)}


def questionnaire_eval(engine, households):
    out = []
    full = len(engine.cat.atomic)
    for strat in ("ig", "resolve", "static"):
        qs, ok = [], 0
        for p in households:
            sim = engine.selector.simulate(p, strat)
            qs.append(len(sim["steps"]))
            ok += engine.statuses(p) == engine.statuses(sim["profile"])
        out.append({"strategy": strat, "label": LABELS[strat], "mean": round(statistics.mean(qs), 2),
                    "median": statistics.median(qs), "min": min(qs), "max": max(qs),
                    "accuracy": round(ok / float(len(households)), 4),
                    "saving_vs_full_form": round(1 - statistics.mean(qs) / full, 3)})
    return out


def discovery_curve(engine, households, ks=(4, 6, 8, 10, 12, 15)):
    """After k questions (IG order): share of schemes decided and of eligible schemes confirmed."""
    rows = dict((k, [[], []]) for k in ks)
    n = len(engine.cat.schemes)
    for p in households:
        steps = engine.selector.simulate(p)["steps"]
        final = engine.statuses(p)
        elig = [s for s, v in final.items() if v == "eligible"]
        for k in ks:
            prof = dict((st["id"], st["answer"]) for st in steps[:k] if st["answer"] is not None)
            cur = engine.statuses(prof)
            rows[k][0].append(sum(1 for v in cur.values() if v != "possibly") / float(n))
            rows[k][1].append(sum(1 for s in elig if cur[s] == "eligible") / float(max(1, len(elig))))
    return [{"k": k, "decided": round(statistics.mean(rows[k][0]), 3),
             "eligible_confirmed": round(statistics.mean(rows[k][1]), 3)} for k in ks]


def search_eval(engine):
    h1 = h3 = 0
    rows = []
    for q, want in SEARCH_QUERIES:
        res = engine.search(q, 3)["results"]
        ids = [r["id"] for r in res]
        a1 = bool(ids) and ids[0] in want
        a3 = any(i in want for i in ids)
        h1 += a1
        h3 += a3
        rows.append({"query": q, "expected": want, "got": ids, "hit1": a1})
    n = float(len(SEARCH_QUERIES))
    return {"queries": len(SEARCH_QUERIES), "hit_at_1": round(h1 / n, 3), "hit_at_3": round(h3 / n, 3), "rows": rows}


def latency_eval(engine, pop):
    demo = synth.DEMO_HOUSEHOLDS[0]["profile"]
    partial = dict((k, demo[k]) for k in list(demo)[:5])
    return {
        "evaluate_ms": _summ(_ms(lambda: engine.evaluate(demo), 200)),
        "next_question_ms": _summ(_ms(lambda: engine.next_question({}), 30) + _ms(lambda: engine.next_question(partial), 30)),
        "search_ms": _summ([m for q, _ in SEARCH_QUERIES for m in _ms(lambda: engine.search(q, 5), 10)]),
        "simulate_household_ms": _summ([_ms(lambda: engine.selector.simulate(p), 1)[0] for p in pop[:30]]),
        "village_dashboard_ms": None,
    }


def http_eval(base):
    """Round-trip latency of live API calls (server must be running)."""
    from urllib.request import Request, urlopen

    def call(path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as r:
            r.read()

    prof = synth.DEMO_HOUSEHOLDS[1]["profile"]
    return {
        "GET /api/health": _summ(_ms(lambda: call("/api/health"), 50)),
        "POST /api/next (empty)": _summ(_ms(lambda: call("/api/next", {"profile": {}}), 30)),
        "POST /api/evaluate": _summ(_ms(lambda: call("/api/evaluate", {"profile": prof}), 50)),
        "GET /api/search": _summ(_ms(lambda: call("/api/search?q=%E0%AE%AA%E0%AE%AF%E0%AE%BF%E0%AE%B0%E0%AF%8D"), 50)),
        "POST /api/simulate (demo)": _summ(_ms(lambda: call("/api/simulate", {"demo": "demo-farmer"}), 10)),
        "GET /api/village": _summ(_ms(lambda: call("/api/village"), 20)),
    }


def run(data_dir, http=None):
    t0 = time.perf_counter()
    engine = Engine(data_dir)
    pop = synth.population(config.EVAL_POPULATION, config.EVAL_SEED)
    demo = [d["profile"] for d in synth.DEMO_HOUSEHOLDS]
    allh = demo + pop
    elig = [sum(1 for v in engine.statuses(p).values() if v == "eligible") for p in allh]
    village_hh = engine.demo_village_households()
    vt = _ms(lambda: engine.village_dashboard(village_hh), 20)
    res = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "catalogue": {"schemes": len(engine.cat.schemes), "full_form": len(engine.cat.atomic),
                      "gates": len(engine.cat.gates), "inferences": len(engine.cat.inferences),
                      "per_scheme_fields": sum(len(s["facts"]) for s in engine.cat.schemes)},
        "questionnaire": {
            "households": len(allh), "full_form": len(engine.cat.atomic),
            "per_scheme_fields": sum(len(s["facts"]) for s in engine.cat.schemes),
            "population_note": "4 demo families + %d synthetic households (seed %d); answer priors learnt from a separate population (seed %d, n=%d)."
                               % (len(pop), config.EVAL_SEED, config.PRIOR_SEED, config.PRIOR_POPULATION),
            "strategies": questionnaire_eval(engine, allh),
            "demo": [{"id": d["id"], "questions": len(engine.selector.simulate(d["profile"])["steps"]),
                      "eligible": sum(1 for v in engine.statuses(d["profile"]).values() if v == "eligible")}
                     for d in synth.DEMO_HOUSEHOLDS],
            "discovery_curve": discovery_curve(engine, allh),
            "avg_eligible_schemes": round(statistics.mean(elig), 2),
        },
        "search": search_eval(engine),
        "latency": latency_eval(engine, pop),
        "engine_startup_ms": engine.startup_ms,
    }
    res["latency"]["village_dashboard_ms"] = _summ(vt)
    res["latency"]["village_households"] = len(village_hh)
    if http:
        res["http"] = http_eval(http)
    res["eval_seconds"] = round(time.perf_counter() - t0, 2)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", help="base URL of a running server to time live API calls")
    ap.add_argument("--out", help="output path (default data/evaluation.json)")
    a = ap.parse_args(argv)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(here, "data")
    res = run(data_dir, a.http)
    out = a.out or os.path.join(data_dir, "evaluation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    q = res["questionnaire"]
    for s in q["strategies"]:
        print("%-28s mean %.2f  median %s  max %d  accuracy %.0f%%" % (s["label"], s["mean"], s["median"], s["max"], 100 * s["accuracy"]))
    print("full form: %d fields; separate per-scheme checks: %d fields" % (q["full_form"], q["per_scheme_fields"]))
    print("search hit@1 %.0f%%  hit@3 %.0f%%" % (100 * res["search"]["hit_at_1"], 100 * res["search"]["hit_at_3"]))
    print("latency evaluate %.2f ms, next question %.2f ms" % (res["latency"]["evaluate_ms"]["mean"], res["latency"]["next_question_ms"]["mean"]))
    print("wrote", out)


if __name__ == "__main__":
    sys.exit(main())
