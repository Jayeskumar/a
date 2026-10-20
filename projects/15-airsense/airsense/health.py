"""Health advisories, personalised alerts and 'best time for a run' from the forecast."""

from . import config as C
from .aqi import category, category_index


class ProfileError(ValueError):
    pass


def profile(key):
    p = C.PROFILES.get(key)
    if p is None:
        raise ProfileError("unknown profile '%s' (use one of: %s)" % (key, ", ".join(C.PROFILES)))
    return p


def advice(aqi, profile_key="general"):
    p = profile(profile_key)
    cat = category(aqi)
    return {"aqi": aqi, "category": cat["name"], "category_key": cat["key"], "color": cat["color"],
            "health": cat["health"], "advice": p["advice"][cat["key"]], "profile": p["name"]}


def alerts(hours, aqi, profile_key="general", labels=None, upper=None):
    """Group consecutive forecast hours at/above the profile's alert threshold.

    hours: forecast hour indices; aqi: forecast AQI per hour; upper: optional upper bound
    of the interval (an hour also alerts if its upper bound crosses the threshold - early
    warning for sensitive groups is then marked 'possible').
    """
    p = profile(profile_key)
    thr = p["alert_from"]
    out = []
    k = 0
    n = len(aqi)
    while k < n:
        hit = aqi[k] is not None and aqi[k] >= thr
        maybe = (not hit) and upper is not None and upper[k] is not None and upper[k] >= thr
        if not (hit or maybe):
            k += 1
            continue
        e = k
        while e + 1 < n and ((aqi[e + 1] is not None and aqi[e + 1] >= thr) or
                             (upper is not None and upper[e + 1] is not None and upper[e + 1] >= thr)):
            e += 1
        seg = [a for a in aqi[k:e + 1] if a is not None]
        peak = max(seg) if seg else thr
        firm = any(a is not None and a >= thr for a in aqi[k:e + 1])
        cat = category(max(peak, thr) if firm else thr)
        out.append({
            "start": labels[k] if labels else hours[k], "end": labels[e] if labels else hours[e],
            "start_index": k, "end_index": e, "peak_aqi": peak, "category": category(peak)["name"],
            "level": "alert" if firm else "possible",
            "message": "%s %s-%s: AQI %s %d (%s). %s" % (
                "Expected" if firm else "Possible", labels[k] if labels else hours[k],
                labels[e] if labels else hours[e], "up to" if firm else "may reach",
                peak if firm else thr, category(peak if firm else thr)["name"],
                p["advice"][cat["key"]]),
            "rule": "%s profile alerts from AQI %d (%s)" % (p["name"], thr, category(thr)["name"]),
        })
        k = e + 1
    return out


def best_run(hods, aqi, upper=None, labels=None, window=C.RUN_WINDOW_HOURS, profile_key="general"):
    """Lowest-AQI hour inside the daytime run window (ties: earliest). Uses the interval
    upper bound when given, so the pick is robust to forecast error."""
    p = profile(profile_key)
    best = worst = None
    for k, h in enumerate(hods):
        if not (window[0] <= h <= window[1]) or aqi[k] is None:
            continue
        score = upper[k] if upper is not None and upper[k] is not None else aqi[k]
        if best is None or score < best[0]:
            best = (score, k)
        if worst is None or aqi[k] > worst[0]:
            worst = (aqi[k], k)
    if best is None:
        return None
    k = best[1]
    cat = category(aqi[k])
    ok = aqi[k] <= p["run_max"]
    return {"index": k, "label": labels[k] if labels else hods[k], "hour": hods[k], "aqi": aqi[k],
            "upper": upper[k] if upper else None, "category": cat["name"], "color": cat["color"],
            "ok_for_profile": ok,
            "worst_index": worst[1], "worst_label": labels[worst[1]] if labels else hods[worst[1]],
            "worst_aqi": worst[0],
            "why": "Lowest forecast AQI%s between %02d:00 and %02d:59; avoid %s (AQI %d)." % (
                " (upper bound of 80% interval)" if upper else "", window[0], window[1],
                labels[worst[1]] if labels else hods[worst[1]], worst[0]),
            "verdict": ("Good window for a run" if ok else
                        "Even the cleanest hour (AQI %d) is above the %s comfort limit of AQI %d - "
                        "consider an indoor workout" % (aqi[k], p["name"], p["run_max"]))}


def worst_category_index(aqis):
    vals = [category_index(a) for a in aqis if a is not None]
    return max(vals) if vals else None
