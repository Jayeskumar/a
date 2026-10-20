"""Offline evaluation of PulseGuard on the simulated ward (numbers used in REPORT.md).

For each seed the whole 24 h ward is replayed through the same PatientMonitor the live
server uses. Measured:
  * lead time of the trend early warning vs. a plain continuous NEWS2>=5 threshold alert,
    and vs. a paper-chart 4-hourly observation round reaching NEWS2>=5,
  * false alerts on non-deteriorating patients (stable + improving),
  * effect of SpO2 Scale 2 on the COPD patient (red scores avoided),
  * scoring latency.

Run: python -m pulseguard.evaluation   (writes data/evaluation.json)
"""

import json
import os
import statistics
import sys
import time

from . import config, news2, simulator
from .alerts import PatientMonitor

EVAL_SEEDS = list(range(1, 31))        # trend thresholds were tuned on these seeds
HOLDOUT_SEEDS = list(range(101, 131))  # never used for tuning: honest out-of-sample check
HOLDOUT_KEYS = ("deteriorating_episodes", "detected_by_trend_before_threshold",
                "lead_vs_threshold_h", "lead_vs_manual_h", "false_alerts_before_onset",
                "stable_patient_days", "stable_trend_alerts",
                "stable_trend_alerts_per_patient_day",
                "stable_only_threshold_medium_plus_alerts")


def replay(profile, readings):
    mon = PatientMonitor()
    events = []
    scored = []
    for r in readings:
        s, ev = mon.ingest(r)
        scored.append(s)
        events.extend(ev)
    return scored, events


def _first(scored, pred):
    for s in scored:
        if pred(s):
            return s["t"]
    return None


def analyse_patient(profile, readings):
    scored, events = replay(profile, readings)
    out = {"id": profile["id"], "name": profile["name"], "kind": profile["kind"]}
    trend_alerts = [e for e in events if e["type"] == "trend"]
    thr_alerts = [e for e in events if e["type"] == "threshold"]
    if profile["kind"] == "deteriorating":
        onset = profile["onset_h"]
        t_thr = _first(scored, lambda s: s["score"] >= config.NEWS2_MEDIUM_THRESHOLD)
        t_red = _first(scored, lambda s: s["band_rank"] >= 1)
        t_manual = _first(scored, lambda s: s["score"] >= config.NEWS2_MEDIUM_THRESHOLD and
                          s["step"] % (config.MANUAL_ROUND_HOURS * config.STEPS_PER_HOUR) == 0)
        early_true = [e["t"] for e in trend_alerts if e["t"] >= onset]
        false_before = [e["t"] for e in trend_alerts if e["t"] < onset] + \
                       [e["t"] for e in thr_alerts if e["t"] < onset]
        t_trend = early_true[0] if early_true else None
        t_pg = min([x for x in (t_trend, t_thr) if x is not None], default=None)
        out.update(onset_h=round(onset, 2), t_threshold=t_thr, t_red=t_red,
                   t_manual=t_manual, t_trend=t_trend, t_pulseguard=t_pg,
                   lead_vs_threshold=(None if t_thr is None or t_pg is None
                                      else t_thr - t_pg),
                   lead_vs_manual=(None if t_manual is None or t_pg is None
                                   else t_manual - t_pg),
                   threshold_vs_manual=(None if t_manual is None or t_thr is None
                                        else t_manual - t_thr),
                   false_alerts_before_onset=len(false_before),
                   trend_fired_before_threshold=(t_trend is not None and t_thr is not None
                                                 and t_trend < t_thr))
    else:
        out.update(trend_alerts=len(trend_alerts),
                   threshold_alerts=len(thr_alerts),
                   threshold_medium_plus=len([e for e in thr_alerts
                                              if e["band"] in ("medium", "high")]),
                   max_score=max(s["score"] for s in scored))
    if profile["scale"] == 2:
        s1_red = 0
        s2_red = 0
        for r in readings:
            alt = dict(r, scale=1)
            if news2.calculate(alt)["band_rank"] >= 1:
                s1_red += 1
            if news2.calculate(r)["band_rank"] >= 1:
                s2_red += 1
        out.update(scale1_red_readings=s1_red, scale2_red_readings=s2_red,
                   readings=len(readings))
    return out


def run_seed(seed, jitter=True):
    ward = simulator.generate_ward(seed=seed, jitter=jitter)
    return [analyse_patient(w["profile"], w["readings"]) for w in ward]


def _summary(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"n": len(vals), "median": round(statistics.median(vals), 2),
            "mean": round(statistics.mean(vals), 2), "min": round(min(vals), 2),
            "max": round(max(vals), 2)}


def measure_latency(n=20000):
    obs = {"rr": 22, "spo2": 94, "o2": False, "sbp": 104, "hr": 112, "acvpu": "A",
           "temp": 38.4, "scale": 1}
    t0 = time.perf_counter()
    for _ in range(n):
        news2.calculate(obs)
    per_score_us = (time.perf_counter() - t0) / n * 1e6
    ward = simulator.generate_ward()
    t0 = time.perf_counter()
    mons = [PatientMonitor() for _ in ward]
    count = 0
    for w, m in zip(ward, mons):
        for r in w["readings"]:
            m.ingest(r)
            count += 1
    per_ingest_us = (time.perf_counter() - t0) / count * 1e6
    return {"news2_score_us": round(per_score_us, 2),
            "score_plus_trend_us": round(per_ingest_us, 2),
            "readings_timed": count}


def evaluate(seeds=None):
    seeds = seeds or EVAL_SEEDS
    det, stable = [], []
    copd = []
    for seed in seeds:
        for row in run_seed(seed):
            row["seed"] = seed
            (det if row["kind"] == "deteriorating" else stable).append(row)
            if "scale1_red_readings" in row:
                copd.append(row)
    demo = run_seed(config.DEFAULT_SEED, jitter=False)
    hours = config.SCENARIO_HOURS
    n_stable_days = len(stable) * hours / 24.0
    total_false_trend = sum(r["trend_alerts"] for r in stable)
    total_false_thr = sum(r["threshold_medium_plus"] for r in stable)
    per_patient = {}
    for r in det:
        per_patient.setdefault(r["name"], []).append(r)
    res = {
        "seeds": len(seeds),
        "scenario_hours": hours,
        "deteriorating_episodes": len(det),
        "detected_by_trend_before_threshold": sum(1 for r in det
                                                  if r["trend_fired_before_threshold"]),
        "lead_vs_threshold_h": _summary([r["lead_vs_threshold"] for r in det]),
        "lead_vs_manual_h": _summary([r["lead_vs_manual"] for r in det]),
        "threshold_vs_manual_h": _summary([r["threshold_vs_manual"] for r in det]),
        "per_patient": {name: {
            "lead_vs_threshold_h": _summary([r["lead_vs_threshold"] for r in rows]),
            "lead_vs_manual_h": _summary([r["lead_vs_manual"] for r in rows]),
        } for name, rows in per_patient.items()},
        "false_alerts_before_onset": sum(r["false_alerts_before_onset"] for r in det),
        "stable_patient_days": round(n_stable_days, 1),
        "stable_trend_alerts": total_false_trend,
        "stable_threshold_medium_plus_alerts": total_false_thr,
        "stable_only_patient_days": round(len([r for r in stable if r["kind"] == "stable"])
                                          * hours / 24.0, 1),
        "stable_only_trend_alerts": sum(r["trend_alerts"] for r in stable
                                        if r["kind"] == "stable"),
        "stable_only_threshold_alerts": sum(r["threshold_alerts"] for r in stable
                                            if r["kind"] == "stable"),
        "stable_only_threshold_medium_plus_alerts": sum(
            r["threshold_medium_plus"] for r in stable if r["kind"] == "stable"),
        "improving_trend_alerts": sum(r["trend_alerts"] for r in stable
                                      if r["kind"] == "improving"),
        "stable_trend_alerts_per_patient_day": round(total_false_trend / n_stable_days, 3),
        "copd_scale1_red_readings": sum(r["scale1_red_readings"] for r in copd),
        "copd_scale2_red_readings": sum(r["scale2_red_readings"] for r in copd),
        "copd_readings": sum(r["readings"] for r in copd),
        "demo_ward": demo,
        "latency": measure_latency(),
    }
    return res


SENSITIVITY = [
    # (label, overrides) - how the lead-time / false-alert trade-off moves with the knobs.
    ("Shipped settings", {}),
    ("Shorter horizon (2 h)", {"TREND_HORIZON_H": 2.0}),
    ("Looser fit (R2 >= 0.4)", {"TREND_MIN_R2": 0.4}),
    ("No confirmation (1 reading)", {"TREND_CONFIRM_READINGS": 1}),
    ("Longer window (16 readings)", {"TREND_WINDOW": 16}),
]


def holdout():
    res = evaluate(seeds=HOLDOUT_SEEDS)
    out = {k: res[k] for k in HOLDOUT_KEYS}
    out["seeds"] = "%d-%d" % (HOLDOUT_SEEDS[0], HOLDOUT_SEEDS[-1])
    return out


def sensitivity(seeds=None):
    seeds = seeds or EVAL_SEEDS
    rows = []
    for label, overrides in SENSITIVITY:
        saved = {k: getattr(config, k) for k in overrides}
        try:
            for k, v in overrides.items():
                setattr(config, k, v)
            det, fa, days = [], 0, 0
            for seed in seeds:
                for r in run_seed(seed):
                    if r["kind"] == "deteriorating":
                        det.append(r)
                    else:
                        fa += r["trend_alerts"]
                        days += config.SCENARIO_HOURS / 24.0
            rows.append({"label": label, "overrides": overrides,
                         "lead_vs_threshold_median_h": _summary(
                             [r["lead_vs_threshold"] for r in det])["median"],
                         "trend_first": sum(r["trend_fired_before_threshold"] for r in det),
                         "episodes": len(det),
                         "false_trend_alerts": fa,
                         "false_per_patient_day": round(fa / days, 3)})
        finally:
            for k, v in saved.items():
                setattr(config, k, v)
    return rows


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = evaluate()
    result["sensitivity"] = sensitivity()
    result["holdout"] = holdout()
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "data", "evaluation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    printable = {k: v for k, v in result.items() if k != "demo_ward"}
    print(json.dumps(printable, indent=1, ensure_ascii=False))
    print("wrote", path)
