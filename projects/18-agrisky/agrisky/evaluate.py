"""Offline evaluation: python -m agrisky.evaluate  ->  data/metrics.json

* Zone classification accuracy vs the generator's ground truth, per cell, on the demo seed
  (used while tuning the rules) and on HOLDOUT_SEEDS that were never looked at while tuning
  (each seed is a new field layout, pest corner, speed and noise).
* Pest spread-rate estimate vs the generator's true front speed.
* Chemical savings of the variable-rate prescription vs uniform application.
* Coverage-path quality: coverage exactness, overspray, path efficiency, turn minimisation.
* Latency of each pipeline stage.
"""
import json
import os
import statistics
import sys
import time

from . import config, planner
from .pipeline import Store
from .field import W, H

HOLDOUT_SEEDS = list(range(101, 121))
CONTROL_SEEDS = list(range(201, 211))     # fields generated with no pest outbreak at all


def _pool(acc_list):
    k = len(config.CLASSES)
    m = [[0] * k for _ in range(k)]
    for a in acc_list:
        for i in range(k):
            for j in range(k):
                m[i][j] += a["matrix"][i][j]
    per = {}
    for i, c in enumerate(config.CLASSES):
        tp = m[i][i]
        fp = sum(m[r][i] for r in range(k)) - tp
        fn = sum(m[i]) - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": round(p, 4), "recall": round(r, 4),
                  "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "support": tp + fn}
    total = sum(sum(row) for row in m)
    return {"accuracy": round(sum(m[i][i] for i in range(k)) / total, 4), "per_class": per,
            "matrix": m, "classes": list(config.CLASSES)}


def evaluate_seed(store, seed):
    als = store.all_analyses(seed)
    last = len(als) - 1
    ch = store.change(seed, last)
    rx_p = store.prescription(seed, last, "pesticide")
    rx_u = store.prescription(seed, last, "urea")
    m_vra = store.mission(seed, last, "pesticide", "vra")
    m_uni = store.mission(seed, last, "pesticide", "uniform")
    first_red = None
    for k in range(len(als)):
        c = store.change(seed, k)
        if c["spread"]["alert"]["level"] == "red":
            first_red = {"flight": k + 1, "day": als[k]["day"],
                         "pest_pct_crop": c["spread"]["series"][-1]["pct_crop"],
                         "truth_m2": c["truth"]["series"][-1]["area_m2"]}
            break
    est = ch["spread"].get("front_speed_m_day")
    true = ch["truth"]["front_speed_m_day"]
    return {
        "seed": seed,
        "acc_by_flight": [a["accuracy"]["accuracy"] for a in als],
        "macro_f1_by_flight": [a["accuracy"]["macro_f1"] for a in als],
        "acc_objs": [a["accuracy"] for a in als],
        "zones_by_flight": [len(a["zones"]) for a in als],
        "front_speed_est": est, "front_speed_true": true,
        "front_speed_err_pct": round(100.0 * abs(est - true) / true, 1) if est else None,
        "alert": ch["spread"]["alert"]["level"],
        "first_red_alert": first_red,
        "pesticide_saved_pct": rx_p["savings"]["pct"], "urea_saved_pct": rx_u["savings"]["pct"],
        "rs_saved": round(rx_p["savings"]["rs"] + rx_u["savings"]["rs"], 1),
        "vra": m_vra["totals"], "uniform": m_uni["totals"],
        "timing_ms": [a["timing_ms"]["total"] for a in als],
    }


def control_study():
    """False alarms: run the full pipeline on pest-free fields."""
    from . import analysis as an
    from . import change, field
    out = []
    for seed in CONTROL_SEEDS:
        data = field.generate(seed, pest=False)
        prev, als = None, []
        for f in data["flights"]:
            a = an.analyse_flight(f, prev, seed=seed)
            als.append(a)
            prev = dict(f)
            prev["features"] = a["features"]
        masks = [[c == "pest" for c in a["cell_class"]] for a in als]
        crop = sum(1 for c in als[-1]["cell_class"] if c in config.CROP_CLASSES)
        levels = []
        for k in range(len(als)):
            rates = [z["ndvi_rate_week"] for z in als[k]["zones"]
                     if z["label"] == "pest" and z.get("spreading")]
            sp = change.spread([a["day"] for a in als[:k + 1]], masks[:k + 1], crop,
                               min(rates) if rates else None)
            levels.append(sp["alert"]["level"])
        out.append({"seed": seed, "pest_cells": [sum(m) for m in masks], "alerts": levels,
                    "accuracy": [a["accuracy"]["accuracy"] for a in als]})
    return out


def turn_study(store, seed, product="pesticide"):
    """Auto orientation vs forced east-west / north-south passes on the same targets."""
    last = len(store.all_analyses(seed)) - 1
    rx = store.prescription(seed, last, product)
    target = [r > 0 for r in rx["cell_rate"]]
    out = {}
    if not any(target):
        return None
    for o in ("auto", "h", "v"):
        res = planner.plan(target, rx["payload_per_m2"], W, H, orient=o)
        out[o] = {"turns": res["totals"]["turns"], "time_s": res["totals"]["flight_time_s"],
                  "distance_m": res["totals"]["distance_m"]}
    return out


def main(argv=None):
    t_start = time.perf_counter()
    store = Store()
    t0 = time.perf_counter()
    demo = evaluate_seed(store, config.DEFAULT_SEED)
    cold_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    store.scene(config.DEFAULT_SEED, 4)
    scene_warm = (time.perf_counter() - t0) * 1000
    hold = []
    for s in HOLDOUT_SEEDS:
        hold.append(evaluate_seed(store, s))
        store.analyses.clear()
        store.fields.clear()
        store.missions.clear()
        sys.stdout.write(".")
        sys.stdout.flush()
    print()
    accs = [a for h in hold for a in h["acc_by_flight"]]
    accs_hist = [a for h in hold for a in h["acc_by_flight"][1:]]
    f1s = [a for h in hold for a in h["macro_f1_by_flight"]]
    pooled = _pool([o for h in hold for o in h["acc_objs"]])
    errs = [h["front_speed_err_pct"] for h in hold if h["front_speed_err_pct"] is not None]
    turn_res = {}
    for product in ("pesticide", "urea"):
        turns = {o: [] for o in ("auto", "h", "v")}
        times = {o: [] for o in ("auto", "h", "v")}
        for s in HOLDOUT_SEEDS[:10]:
            ts = turn_study(store, s, product)
            if ts:
                for o in ts:
                    turns[o].append(ts[o]["turns"])
                    times[o].append(ts[o]["time_s"])
            store.analyses.clear()
            store.fields.clear()
        turn_res[product] = {o: {"turns_mean": round(statistics.mean(turns[o]), 2),
                                 "time_s_mean": round(statistics.mean(times[o]), 1)}
                             for o in turns if turns[o]}
    # whole-field blanket plan on the demo field
    a = store.analysis(config.DEFAULT_SEED, 4)
    from .prescription import no_spray_mask
    blocked = no_spray_mask(a["cell_class"])
    tgt = [c in config.CROP_CLASSES and not blocked[i] for i, c in enumerate(a["cell_class"])]
    rate = [config.SPRAY_VOLUME_L_HA / config.M2_PER_HA] * len(tgt)
    turn_res["whole_field_demo"] = {}
    for o in ("auto", "h", "v"):
        res = planner.plan(tgt, rate, W, H, orient=o)
        turn_res["whole_field_demo"][o] = {"turns_mean": res["totals"]["turns"],
                                           "time_s_mean": res["totals"]["flight_time_s"]}
    timing = [t for h in hold for t in h["timing_ms"]]
    ctrl = control_study()
    firsts = [h["first_red_alert"] for h in hold if h["first_red_alert"]]
    exact = all(h["vra"]["covered_multi"] == 0 and h["vra"]["missed"] == 0 and
                h["uniform"]["covered_multi"] == 0 and h["uniform"]["missed"] == 0 for h in hold)
    metrics = {
        "generated_by": "python -m agrisky.evaluate",
        "demo_seed": {k: v for k, v in demo.items() if k != "acc_objs"},
        "demo_confusion": _pool(demo["acc_objs"]),
        "holdout": {
            "seeds": HOLDOUT_SEEDS, "flights": len(accs),
            "accuracy_mean": round(statistics.mean(accs), 4),
            "accuracy_min": round(min(accs), 4),
            "accuracy_flight1_mean": round(statistics.mean(h["acc_by_flight"][0] for h in hold), 4),
            "accuracy_with_history_mean": round(statistics.mean(accs_hist), 4),
            "macro_f1_mean": round(statistics.mean(f1s), 4),
            "pooled": pooled,
            "front_speed_err_pct_mean": round(statistics.mean(errs), 1) if errs else None,
            "front_speed_err_pct_max": round(max(errs), 1) if errs else None,
            "red_alerts_last_flight": sum(1 for h in hold if h["alert"] == "red"),
            "first_red_alert_day_mean": round(statistics.mean(f["day"] for f in firsts), 1) if firsts else None,
            "first_red_alert_flight_counts": {str(k): sum(1 for f in firsts if f["flight"] == k)
                                              for k in range(1, 6)},
            "pest_pct_crop_at_first_alert_mean": round(statistics.mean(f["pest_pct_crop"] for f in firsts), 2) if firsts else None,
            "pesticide_saved_pct_mean": round(statistics.mean(h["pesticide_saved_pct"] for h in hold), 1),
            "urea_saved_pct_mean": round(statistics.mean(h["urea_saved_pct"] for h in hold), 1),
            "rs_saved_mean": round(statistics.mean(h["rs_saved"] for h in hold), 0),
            "vra_sorties_mean": round(statistics.mean(h["vra"]["sorties"] for h in hold), 2),
            "uniform_sorties_mean": round(statistics.mean(h["uniform"]["sorties"] for h in hold), 2),
            "vra_flight_time_s_mean": round(statistics.mean(h["vra"]["flight_time_s"] for h in hold), 1),
            "uniform_flight_time_s_mean": round(statistics.mean(h["uniform"]["flight_time_s"] for h in hold), 1),
            "vra_overspray_pct_mean": round(statistics.mean(h["vra"]["overspray_pct"] for h in hold), 1),
            "vra_path_eff_mean": round(statistics.mean(h["vra"]["path_efficiency"] for h in hold), 3),
            "vra_infield_eff_mean": round(statistics.mean(h["vra"]["infield_efficiency"] for h in hold), 3),
            "uniform_path_eff_mean": round(statistics.mean(h["uniform"]["path_efficiency"] for h in hold), 3),
            "coverage_exact_all": exact,
            "per_seed": [{k: v for k, v in h.items() if k not in ("acc_objs", "vra", "uniform")}
                         for h in hold],
        },
        "control_no_pest": {
            "seeds": CONTROL_SEEDS, "flights": sum(len(c["alerts"]) for c in ctrl),
            "red_alerts": sum(c["alerts"].count("red") for c in ctrl),
            "flights_with_false_pest_cells": sum(1 for c in ctrl for n in c["pest_cells"] if n > 0),
            "false_pest_cells_total": sum(sum(c["pest_cells"]) for c in ctrl),
            "accuracy_mean": round(statistics.mean(a for c in ctrl for a in c["accuracy"]), 4),
            "per_seed": ctrl},
        "turn_minimisation": turn_res,
        "latency_ms": {
            "analyse_flight_median": round(statistics.median(timing), 1),
            "analyse_flight_p90": round(sorted(timing)[int(0.9 * len(timing))], 1),
            "demo_all_flights_cold": round(cold_ms, 1),
            "scene_warm": round(scene_warm, 1),
            "plan_vra_ms": store.mission(config.DEFAULT_SEED, 4, "pesticide", "vra")["plan_ms"],
            "plan_uniform_ms": store.mission(config.DEFAULT_SEED, 4, "pesticide", "uniform")["plan_ms"],
        },
        "eval_seconds": round(time.perf_counter() - t_start, 1),
    }
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "metrics.json")
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except ValueError:
            old = {}
    if "http" in old:
        metrics["http"] = old["http"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=1, ensure_ascii=False)
    h = metrics["holdout"]
    print("hold-out accuracy %.2f%% (min %.2f%%), macro-F1 %.3f, front-speed error %.1f%%"
          % (100 * h["accuracy_mean"], 100 * h["accuracy_min"], h["macro_f1_mean"],
             h["front_speed_err_pct_mean"] or -1))
    print("saved: pesticide %.1f%%, urea %.1f%%; sorties VRA %.2f vs uniform %.2f; exact coverage: %s"
          % (h["pesticide_saved_pct_mean"], h["urea_saved_pct_mean"], h["vra_sorties_mean"],
             h["uniform_sorties_mean"], exact))
    c = metrics["control_no_pest"]
    print("control (no pest): %d red alerts in %d flights, %d false pest cells; first real alert "
          "on day %s at %.2f%% of crop" % (c["red_alerts"], c["flights"], c["false_pest_cells_total"],
                                           h["first_red_alert_day_mean"],
                                           h["pest_pct_crop_at_first_alert_mean"] or -1))
    print("wrote", path)
    return metrics


if __name__ == "__main__":
    main()
