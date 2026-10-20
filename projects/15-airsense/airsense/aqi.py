"""India National AQI (CPCB) sub-indices, overall AQI and averaging rules.

I_p = (I_hi - I_lo) / (B_hi - B_lo) * (C_p - B_lo) + I_lo    (CPCB NAQI, 2014)
AQI = max over pollutants of I_p, valid only with >= 3 pollutants incl. PM2.5 or PM10.
"""

import math

from . import config as C


class AQIError(ValueError):
    pass


def _knots(pollutant):
    rows = C.BREAKPOINTS.get(pollutant)
    if rows is None:
        raise AQIError("unknown pollutant '%s'" % pollutant)
    pts = []
    for c_lo, c_hi, i_lo, i_hi in rows:
        pts.append((float(c_lo), float(i_lo)))
        pts.append((float(c_hi), float(i_hi)))
    return pts


_KNOTS = {p: _knots(p) for p in C.BREAKPOINTS}


def round_half_up(x):
    return int(math.floor(x + 0.5))


def sub_index(pollutant, conc):
    """Continuous CPCB sub-index (float, 0..500) for one concentration.

    Inside a published row the official linear formula is used; inside the small gap
    between two rows (e.g. 30 < PM2.5 < 31) we interpolate between the neighbouring
    breakpoints so the curve is continuous and monotone. Above the last row: 500.
    """
    if conc is None:
        return None
    try:
        c = float(conc)
    except (TypeError, ValueError):
        raise AQIError("concentration for %s must be a number" % pollutant)
    if math.isnan(c) or math.isinf(c):
        raise AQIError("concentration for %s must be finite" % pollutant)
    if c < 0:
        raise AQIError("concentration for %s cannot be negative" % pollutant)
    pts = _KNOTS.get(pollutant)
    if pts is None:
        raise AQIError("unknown pollutant '%s'" % pollutant)
    if c >= pts[-1][0]:
        return float(C.AQI_MAX)
    for k in range(len(pts) - 1):
        (b0, i0), (b1, i1) = pts[k], pts[k + 1]
        if b0 <= c <= b1:
            if b1 == b0:
                return i0
            return i0 + (i1 - i0) * (c - b0) / (b1 - b0)
    return float(C.AQI_MAX)  # pragma: no cover


def breakpoint_row(pollutant, conc):
    """The official table row a concentration falls in (for the 'why' explanation)."""
    rows = C.BREAKPOINTS[pollutant]
    k = category_index(sub_index(pollutant, conc))
    c_lo, c_hi, i_lo, i_hi = rows[k]
    return {"c_lo": c_lo, "c_hi": c_hi, "i_lo": i_lo, "i_hi": i_hi,
            "category": C.CATEGORIES[k]["name"]}


def category_index(aqi):
    a = round_half_up(aqi) if aqi is not None else None
    if a is None:
        return None
    for k, cat in enumerate(C.CATEGORIES):
        if a <= cat["hi"]:
            return k
    return len(C.CATEGORIES) - 1


def category(aqi):
    k = category_index(aqi)
    return None if k is None else C.CATEGORIES[k]


def overall(subindices):
    """Combine sub-indices {pollutant: value or None} into the overall AQI.

    Returns aqi (int, the max), category, prominent pollutant(s) and whether the
    CPCB data-sufficiency rule is met (>= 3 pollutants, at least one of PM2.5/PM10).
    """
    avail = {p: v for p, v in subindices.items() if v is not None}
    if not avail:
        return {"aqi": None, "valid": False, "category": None, "prominent": [],
                "reason": "no pollutant data", "n_pollutants": 0}
    best = max(avail.values())
    aqi = round_half_up(best)
    prominent = [p for p, v in avail.items() if round_half_up(v) == aqi]
    has_pm = any(p in avail for p in C.REQUIRED_ANY_OF)
    valid = len(avail) >= C.MIN_POLLUTANTS and has_pm
    if valid:
        reason = "%d pollutants available incl. %s" % (
            len(avail), "/".join(C.POLLUTANTS[p][0] for p in C.REQUIRED_ANY_OF if p in avail))
    elif not has_pm:
        reason = "CPCB rule: needs PM2.5 or PM10"
    else:
        reason = "CPCB rule: needs at least %d pollutants (have %d)" % (C.MIN_POLLUTANTS, len(avail))
    cat = category(aqi)
    return {"aqi": aqi, "valid": valid, "category": cat["name"], "category_key": cat["key"],
            "prominent": prominent, "reason": reason, "n_pollutants": len(avail)}


def compute(concs):
    """Full AQI from averaged concentrations {pollutant: value}. Unknown keys are rejected."""
    if not isinstance(concs, dict):
        raise AQIError("concentrations must be an object")
    subs = {}
    for p, v in concs.items():
        if p not in C.BREAKPOINTS:
            raise AQIError("unknown pollutant '%s'" % p)
        if v is None or v == "":
            continue
        subs[p] = sub_index(p, v)
    res = overall(subs)
    res["sub_indices"] = {p: (round(v, 1) if v is not None else None) for p, v in subs.items()}
    res["rows"] = {p: breakpoint_row(p, concs[p]) for p in subs}
    if res["aqi"] is not None:
        res["health"] = category(res["aqi"])["health"]
    return res


# ---------------------------------------------------------------- averaging rules
def rolling_mean(values, window, min_count):
    """Trailing mean over `window` hours; None where fewer than min_count valid values."""
    out = []
    s = 0.0
    n = 0
    for i, v in enumerate(values):
        if v is not None:
            s += v
            n += 1
        if i >= window:
            old = values[i - window]
            if old is not None:
                s -= old
                n -= 1
        out.append(s / n if n >= min_count else None)
    return out


def average_24h(values):
    return rolling_mean(values, 24, C.MIN_HOURS_24H)


def average_8h(values):
    return rolling_mean(values, 8, C.MIN_HOURS_8H)


def daily_max_8h(values):
    """Max of the running 8-hour means over the last 24 hours (CO and O3 rule)."""
    r8 = average_8h(values)
    out = []
    for i in range(len(r8)):
        win = [v for v in r8[max(0, i - 23): i + 1] if v is not None]
        out.append(max(win) if win else None)
    return out


def averaged(pollutant, values):
    """Apply the CPCB averaging period for a pollutant to an hourly series."""
    hours = C.POLLUTANTS[pollutant][2]
    return average_24h(values) if hours == 24 else daily_max_8h(values)


def hourly_indicative(pm25, pm10):
    """Indicative AQI from 1-hour PM values (NOT official: CPCB uses 24-h averages)."""
    subs = []
    if pm25 is not None:
        subs.append(sub_index("pm25", pm25))
    if pm10 is not None:
        subs.append(sub_index("pm10", pm10))
    return round_half_up(max(subs)) if subs else None
