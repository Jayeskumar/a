"""Waste / anomaly detection with a robust hour-of-week baseline.

For each building and each of the 168 hours of the week we take every reading
in the history and compute

    baseline = median(x)            spread = MAD(x) = median(|x - baseline|)
    z        = 0.6745 * (x - baseline) / max(MAD, 5% of baseline, 0.25 kWh)

(the Iglewicz-Hoaglin modified z-score; 0.6745 makes MAD comparable to a
standard deviation). An hour is flagged as waste when z > 3.5 AND the excess is
both > 2 kWh and > 30% of baseline. Flagged hours separated by at most one
hour are merged into events of >= 2 hours. Holidays are compared with the
Sunday baseline. Median/MAD are used instead of mean/std because the waste we
are hunting would otherwise inflate the very baseline it is compared with.
"""

from . import config
from .dataset import BUILDING_BY_ID, HOLIDAYS
from .stats import mad, median

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def how_key(ts):
    """Hour-of-week index 0..167 (holidays use the Sunday slot)."""
    wd = 6 if ts.date() in HOLIDAYS else ts.weekday()
    return wd * 24 + ts.hour


def baseline(timestamps, y):
    """{hour_of_week: (median, mad)}"""
    groups = {}
    for t, v in zip(timestamps, y):
        groups.setdefault(how_key(t), []).append(v)
    out = {}
    for k, vals in groups.items():
        m = median(vals)
        out[k] = (m, mad(vals, m))
    return out


def robust_z(x, med, spread):
    scale = max(spread, 0.05 * med, 0.25)
    return 0.6745 * (x - med) / scale


def fmt_time(ts):
    h = ts.hour
    hh = "12 AM" if h == 0 else ("12 PM" if h == 12 else
                                 ("%d AM" % h if h < 12 else "%d PM" % (h - 12)))
    return "%s %s %d %s" % (hh, _DAYS[ts.weekday()], ts.day, ts.strftime("%b"))


def classify(building, ts):
    """Rule-based likely cause. Returns (rule id, plain-language cause)."""
    h = ts.hour
    weekend = ts.weekday() >= 5 or ts.date() in HOLIDAYS
    residential = building["type"] == "Residential"
    if h >= 22 or h < 6:
        if building["type"] == "Services":
            return ("after_hours", "After-hours load - kitchen equipment (wet grinders, "
                                   "water heaters, exhaust fans) left on after closing.")
        if residential:
            return ("night_load", "Unusual night-time load - ACs/geysers or common-area "
                                  "lights left running.")
        return ("after_hours", "After-hours load - computers, lights or AC were left on "
                               "after the building emptied.")
    if weekend and not residential:
        return ("weekend_ac", "Weekend/holiday load in an unoccupied building - AC or "
                              "lighting probably left on from Friday.")
    if residential and not weekend and 9 <= h < 17:
        return ("empty_room_load", "Load during class hours when rooms are normally empty - "
                                   "geysers, ACs or fans left on.")
    return ("unusual_spike", "Load well above the normal level for this hour - check "
                             "equipment schedules.")


def detect(timestamps, y, building_id, z_threshold=config.ANOMALY_Z_THRESHOLD,
           min_kw=config.ANOMALY_MIN_EXCESS_KW, min_frac=config.ANOMALY_MIN_EXCESS_FRAC,
           min_hours=config.ANOMALY_MIN_HOURS, max_gap=config.ANOMALY_MAX_GAP_HOURS):
    """Return (hourly_rows, events) for one building's series."""
    b = BUILDING_BY_ID.get(building_id, {"id": building_id, "name": building_id,
                                         "type": "Other"})
    base = baseline(timestamps, y)
    hourly = []
    for i, (t, v) in enumerate(zip(timestamps, y)):
        med, spread = base[how_key(t)]
        z = robust_z(v, med, spread)
        excess = v - med
        flag = z > z_threshold and excess > min_kw and excess > min_frac * med
        hourly.append({"i": i, "value": v, "baseline": med, "z": z,
                       "excess": excess, "flag": flag})

    # merge flagged hours into events
    events, cur, gap = [], None, 0
    for row in hourly:
        if row["flag"]:
            if cur is None:
                cur = [row["i"], row["i"]]
            else:
                cur[1] = row["i"]
            gap = 0
        elif cur is not None:
            gap += 1
            if gap > max_gap:
                events.append(cur)
                cur, gap = None, 0
    if cur is not None:
        events.append(cur)

    out = []
    for s, e in events:
        if e - s + 1 < min_hours:
            continue
        rows = hourly[s:e + 1]
        peak = max(rows, key=lambda r: r["excess"])
        wasted = sum(max(0.0, r["excess"]) for r in rows)
        rule, cause = classify(b, timestamps[peak["i"]])
        t_peak = timestamps[peak["i"]]
        reason = ("%s drew %.1f kW at %s vs %.1f kW typical for that hour "
                  "(robust z = %.1f). %s" % (b["name"], peak["value"], fmt_time(t_peak),
                                             peak["baseline"], peak["z"], cause))
        out.append({
            "building": building_id, "building_name": b["name"],
            "start": timestamps[s].isoformat(), "end": timestamps[e].isoformat(),
            "start_index": s, "end_index": e, "hours": e - s + 1,
            "peak_kw": round(peak["value"], 2), "baseline_kw": round(peak["baseline"], 2),
            "max_z": round(max(r["z"] for r in rows), 1),
            "wasted_kwh": round(wasted, 1),
            "cost_inr": round(wasted * config.TARIFF_INR_PER_KWH, 0),
            "co2_kg": round(wasted * config.GRID_EMISSION_FACTOR_KG_PER_KWH, 1),
            "rule": rule, "reason": reason,
            "rule_fired": "z > %.1f and excess > max(%.0f kWh, %d%% of baseline) for >= %d h"
                          % (z_threshold, min_kw, int(min_frac * 100), min_hours),
        })
    return hourly, out


def detect_all(ds):
    return {bid: detect(ds.timestamps, ds.loads[bid], bid)[1] for bid in ds.loads}


# ------------------------------------------------------------------ evaluation
def _overlap(a, b):
    return a["start_index"] <= b["end_index"] and b["start_index"] <= a["end_index"]


def evaluate(detected_by_building, truth_events, n_hours):
    """Event-level and hour-level precision/recall against injected events."""
    detected = [e for evs in detected_by_building.values() for e in evs]
    tp_det = sum(1 for d in detected
                 if any(d["building"] == t["building"] and _overlap(d, t) for t in truth_events))
    hit = [t for t in truth_events
           if any(d["building"] == t["building"] and _overlap(d, t) for d in detected)]
    missed = [t for t in truth_events if t not in hit]
    false_pos = [d for d in detected
                 if not any(d["building"] == t["building"] and _overlap(d, t)
                            for t in truth_events)]

    def hours(evs):
        s = set()
        for e in evs:
            s.update((e["building"], i) for i in range(e["start_index"], e["end_index"] + 1))
        return s
    hd, ht = hours(detected), hours(truth_events)
    inter = len(hd & ht)

    def ratio(a, b):
        return round(a / b, 3) if b else 0.0
    p, r = ratio(tp_det, len(detected)), ratio(len(hit), len(truth_events))
    hp, hr = ratio(inter, len(hd)), ratio(inter, len(ht))
    true_kwh = sum(t["wasted_kwh"] for t in truth_events)
    est_kwh = sum(d["wasted_kwh"] for d in detected)
    return {
        "events_detected": len(detected), "events_true": len(truth_events),
        "event_precision": p, "event_recall": r,
        "event_f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
        "hour_precision": hp, "hour_recall": hr,
        "hour_f1": round(2 * hp * hr / (hp + hr), 3) if hp + hr else 0.0,
        "true_wasted_kwh": round(true_kwh, 1), "estimated_wasted_kwh": round(est_kwh, 1),
        "missed": [{"building": t["building"], "start": t["start"], "hours": t["hours"],
                    "extra_kw": t["extra_kw"], "kind": t["kind"]} for t in missed],
        "false_positives": [{"building": d["building"], "start": d["start"],
                             "hours": d["hours"], "wasted_kwh": d["wasted_kwh"]}
                            for d in false_pos],
        "total_hours_scanned": n_hours * len(detected_by_building),
    }
