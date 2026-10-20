"""SLA analytics: Kaplan-Meier "% still open after N days" curves and a breach-risk model."""

import math

from . import config as C
from .metrics import percentile


def kaplan_meier(durations, events):
    """Kaplan-Meier estimate of S(t) = P(still open after t days).

    durations: days until resolution (event=1) or until now if still open (event=0, censored).
    Returns step points [(t, S(t))] starting at (0, 1).
    """
    data = sorted(zip(durations, events))
    n_at_risk = len(data)
    s = 1.0
    curve = [(0.0, 1.0)]
    i = 0
    while i < len(data):
        t = data[i][0]
        d = c = 0
        while i < len(data) and data[i][0] == t:
            if data[i][1]:
                d += 1
            else:
                c += 1
            i += 1
        if d and n_at_risk:
            s *= 1.0 - d / float(n_at_risk)
            curve.append((t, s))
        n_at_risk -= d + c
    return curve


def survival_at(curve, t):
    s = 1.0
    for ti, si in curve:
        if ti <= t:
            s = si
        else:
            break
    return s


def km_median(curve):
    for t, s in curve:
        if s <= 0.5:
            return t
    return None


def survival_grid(durations, events, max_days=C.SURVIVAL_MAX_DAYS, step=0.5):
    curve = kaplan_meier(durations, events)
    n = int(max_days / step)
    return [{"day": round(k * step, 2), "open_pct": round(100 * survival_at(curve, k * step), 2)} for k in range(n + 1)], curve


def resolution_stats(days):
    if not days:
        return {"n": 0}
    return {"n": len(days), "mean": round(sum(days) / len(days), 2), "p10": round(percentile(days, 0.10), 2),
            "p25": round(percentile(days, 0.25), 2), "median": round(percentile(days, 0.5), 2),
            "p75": round(percentile(days, 0.75), 2), "p90": round(percentile(days, 0.90), 2),
            "max": round(max(days), 2)}


# ----------------------------------------------------------------------------- breach model features
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def breach_feature_names(wards):
    names = ["dept=" + d for d in C.DEPT_CODES] + ["ward=" + w for w in wards] + ["dow=" + d for d in DOW]
    names += ["priority=P%d" % p for p in (1, 2, 3, 4)] + ["backlog", "backlog above normal"]
    return names


def breach_vector(index, dept, ward, dow, priority, backlog, dept_mean_backlog):
    feats = [(index["dept=" + dept], 1.0), (index["ward=" + ward], 1.0), (index["dow=" + DOW[dow]], 1.0),
             (index["priority=P%d" % priority], 1.0),
             (index["backlog"], math.log1p(backlog) / 4.0),
             (index["backlog above normal"], (backlog - dept_mean_backlog) / max(5.0, dept_mean_backlog))]
    feats.sort()
    return tuple(f[0] for f in feats), tuple(f[1] for f in feats)
