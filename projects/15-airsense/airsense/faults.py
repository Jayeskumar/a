"""Sensor fault detection: stuck readings, isolated spikes and drift against neighbours.

stuck  - the same raw value (0.1 ug/m3 resolution) repeated >= STUCK_MIN_RUN hours.
spike  - a one-hour jump that is extreme both in time (vs. the hour before AND after,
         robust z on the sensor's own hour-to-hour changes) and in space (many times the
         median of its nearest neighbours). Real events (fireworks, rain) move whole
         neighbourhoods together, so they fail the spatial test.
drift  - hourly log-ratio of a sensor to the spatial median of its neighbours; each day
         we keep its lower quantile (plumes only raise some hours, drift moves them all).
         A healthy sensor keeps a stable ratio; drift shows as a steady trend. Robust
         z-score vs. the sensor's own healthy baseline days, scaled by the network MAD.
"""

import math

from . import config as C
from .mathx import dist, median, percentile, robust_sigma


def neighbours(sensors, k=C.NEIGHBOURS_K):
    out = {}
    for s in sensors:
        others = sorted((dist(s["x"], s["y"], o["x"], o["y"]), o["id"]) for o in sensors
                        if o["id"] != s["id"])
        out[s["id"]] = [sid for _, sid in others[:k]]
    return out


def detect_stuck(raw, min_run=C.STUCK_MIN_RUN):
    """Return list of (start, end, value) runs of identical consecutive readings."""
    runs = []
    i, n = 0, len(raw)
    while i < n:
        v = raw[i]
        if v is None:
            i += 1
            continue
        j = i
        while j + 1 < n and raw[j + 1] is not None and abs(raw[j + 1] - v) < 1e-9:
            j += 1
        if j - i + 1 >= min_run:
            runs.append((i, j, v))
        i = j + 1
    return runs


def spatial_median(values, nbrs, t, exclude=None):
    vals = []
    for sid in nbrs:
        v = values[sid][t]
        if v is not None and not (exclude and (sid, t) in exclude):
            vals.append(v)
    return median(vals) if len(vals) >= 3 else None


def detect_spikes(series, nbr_series_median, z=C.SPIKE_Z, ratio=C.SPIKE_SPATIAL_RATIO,
                  min_excess=C.SPIKE_MIN_EXCESS):
    """series: one sensor's values; nbr_series_median: neighbour median per hour."""
    diffs = [abs(series[t] - series[t - 1]) for t in range(1, len(series))
             if series[t] is not None and series[t - 1] is not None]
    scale = max(robust_sigma(diffs) or 0.0, 2.0)
    out = []
    for t in range(1, len(series) - 1):
        x, a, b = series[t], series[t - 1], series[t + 1]
        m = nbr_series_median[t]
        if x is None or a is None or b is None or m is None:
            continue
        excess = x - max(a, b)
        if excess > z * scale and x > ratio * m and x - m > min_excess:
            out.append({"hour": t, "value": x, "neighbour_median": m,
                        "z": excess / scale, "ratio": x / m if m > 0 else None})
    return out


def detect_drift(values, sensors, nbrs, n_hours, flagged=None, z_thr=C.DRIFT_Z,
                 min_days=C.DRIFT_MIN_DAYS, base_days=C.DRIFT_BASELINE_DAYS, q=C.DRIFT_QUANTILE):
    """Daily drift detector. For every hour r_t = ln(sensor / spatial median of its
    neighbours). Each day we keep a LOW quantile of r_t: local plumes only push r_t up for
    some hours, while calibration drift shifts every hour. Robust z-score of that daily
    value against the sensor's own healthy baseline days (scale = network-wide MAD).
    Returns per-sensor daily z and drift events."""
    flagged = flagged or set()
    n_days = n_hours // 24
    logr = {}
    for s in sensors:
        sid = s["id"]
        row = []
        for d in range(n_days):
            rs = []
            for t in range(d * 24, d * 24 + 24):
                v = values[sid][t]
                if v is None or (sid, t) in flagged:
                    continue
                nb = [values[o][t] for o in nbrs[sid] if values[o][t] is not None and (o, t) not in flagged]
                if len(nb) >= 3:
                    rs.append(math.log(max(v, 1.0) / max(median(nb), 1.0)))
            row.append(percentile(rs, q) if len(rs) >= 12 else None)
        logr[sid] = row
    dev = {}
    for sid, row in logr.items():
        base = median([v for v in row[:base_days] if v is not None])
        dev[sid] = [None if v is None or base is None else v - base for v in row]
    allv = [v for row in dev.values() for v in row if v is not None]
    sigma = max(robust_sigma(allv) or 0.0, 0.02)
    events = []
    zrows = {}
    for sid, row in dev.items():
        zs = [None if v is None else v / sigma for v in row]
        zrows[sid] = zs
        d = 0
        while d < n_days:
            if zs[d] is not None and abs(zs[d]) > z_thr:
                sign = 1 if zs[d] > 0 else -1
                e = d
                while e + 1 < n_days and zs[e + 1] is not None and zs[e + 1] * sign > z_thr:
                    e += 1
                if e - d + 1 >= min_days:
                    events.append({"sensor": sid, "start_day": d, "end_day": e,
                                   "start_hour": d * 24, "end_hour": e * 24 + 23,
                                   "direction": "up" if sign > 0 else "down",
                                   "max_z": max(abs(z) for z in zs[d:e + 1] if z is not None),
                                   "ratio_change": math.exp(row[e]) if row[e] is not None else None})
                d = e + 1
            else:
                d += 1
    return {"sigma": sigma, "z": zrows, "events": events}


def run(sensors, raw25, cal25, n_hours):
    """Full QA pass. Returns flagged hour set, events with reasons, neighbour medians."""
    nbrs = neighbours(sensors)
    events = []
    flagged = set()
    for s in sensors:
        sid = s["id"]
        for a, b, v in detect_stuck(raw25[sid]):
            events.append({"sensor": sid, "type": "stuck", "start_hour": a, "end_hour": b,
                           "reason": "Raw PM2.5 frozen at %.1f ug/m3 for %d h in a row "
                                     "(rule: >= %d identical readings)" % (v, b - a + 1, C.STUCK_MIN_RUN)})
            for t in range(a, b + 1):
                flagged.add((sid, t))
    med = {}
    for s in sensors:
        sid = s["id"]
        med[sid] = [spatial_median(cal25, nbrs[sid], t, flagged) for t in range(n_hours)]
    for s in sensors:
        sid = s["id"]
        series = [None if (sid, t) in flagged else cal25[sid][t] for t in range(n_hours)]
        for sp in detect_spikes(series, med[sid]):
            t = sp["hour"]
            events.append({"sensor": sid, "type": "spike", "start_hour": t, "end_hour": t,
                           "reason": "%.0f ug/m3 is %.1fx its 6 neighbours (median %.0f) and jumps "
                                     "robust z=%.0f vs. the hours before and after" %
                                     (sp["value"], sp["ratio"] or 0, sp["neighbour_median"], sp["z"])})
            flagged.add((sid, t))
    drift = detect_drift(cal25, sensors, nbrs, n_hours, flagged)
    for e in drift["events"]:
        pct = (e["ratio_change"] - 1) * 100 if e["ratio_change"] else 0
        events.append({"sensor": e["sensor"], "type": "drift", "start_hour": e["start_hour"],
                       "end_hour": n_hours - 1,
                       "reason": "Reading vs. its neighbours' median moved %+.0f%% from its healthy "
                                 "baseline (robust z=%.1f, %d+ days in a row). Needs re-calibration." %
                                 (pct, e["max_z"], e["end_day"] - e["start_day"] + 1)})
        for t in range(e["start_hour"], n_hours):
            flagged.add((e["sensor"], t))
    events.sort(key=lambda e: (e["start_hour"], e["sensor"]))
    return {"events": events, "flagged": flagged, "neighbours": nbrs, "drift": drift,
            "neighbour_median": med}


# ----------------------------------------------------------------- evaluation
def evaluate(detected, injected, n_hours):
    """Event- and hour-level precision/recall per fault type vs. injected ground truth."""
    def hours(ev):
        return set((ev["sensor"], t) for t in range(ev["start_hour"], ev["end_hour"] + 1))

    out = {}
    types = ["stuck", "spike", "drift"]
    for typ in types:
        inj = [e for e in injected if e["type"] == typ]
        det = [e for e in detected if e["type"] == typ]
        hit = 0
        delays = []
        for e in inj:
            matches = [d for d in det if d["sensor"] == e["sensor"] and d["start_hour"] <= e["end_hour"]
                       and d["end_hour"] >= e["start_hour"]]
            if matches:
                hit += 1
                delays.append(max(0, min(d["start_hour"] for d in matches) - e["start_hour"]))
        tp_det = sum(1 for d in det if any(d["sensor"] == e["sensor"] and d["start_hour"] <= e["end_hour"]
                                           and d["end_hour"] >= e["start_hour"] for e in inj))
        res = {"injected": len(inj), "detected": len(det), "true_positive_events": tp_det,
               "event_precision": tp_det / len(det) if det else None,
               "event_recall": hit / len(inj) if inj else None}
        if typ == "drift":
            res["detection_delay_h"] = delays
        else:
            ih = set().union(*[hours(e) for e in inj]) if inj else set()
            dh = set().union(*[hours(e) for e in det]) if det else set()
            res["hour_precision"] = len(ih & dh) / len(dh) if dh else None
            res["hour_recall"] = len(ih & dh) / len(ih) if ih else None
        out[typ] = res
    all_det = len(detected)
    all_tp = sum(out[t]["true_positive_events"] for t in types)
    all_inj = sum(out[t]["injected"] for t in types)
    all_hit = sum(round((out[t]["event_recall"] or 0) * out[t]["injected"]) for t in types)
    out["overall"] = {"event_precision": all_tp / all_det if all_det else None,
                      "event_recall": all_hit / all_inj if all_inj else None,
                      "detected": all_det, "injected": all_inj}
    return out
