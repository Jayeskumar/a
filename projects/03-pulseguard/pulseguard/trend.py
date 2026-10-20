"""Trend-based early warning on top of NEWS2, implemented from scratch.

1. Ordinary least squares over the last N readings, for each vital sign and for the
   aggregate NEWS2 score:   slope b = sum((t-t_mean)(y-y_mean)) / sum((t-t_mean)^2),
   intercept a = y_mean - b*t_mean,  R^2 = 1 - SS_res/SS_tot.
2. A vital's trend is "significant" when R^2 >= TREND_MIN_R2 and the change projected over
   the horizon is clinically meaningful (TREND_MIN_DELTA).
3. Significant trends are projected TREND_HORIZON_H hours ahead; the projected vitals are
   scored with NEWS2. Non-significant vitals keep their latest observed value.
4. Early warning when the patient is still below the medium band and either
   (a) the projected NEWS2 reaches the medium threshold, is >= TREND_MIN_PROJECTED_RISE above
       the current score and at least TREND_MIN_WORSENING_VITALS vitals are worsening, or
   (b) the aggregate score is rising steeply (slope >= SCORE_SLOPE_ALERT pts/h, good fit).
"""

from . import config, news2

VITALS = ("rr", "spo2", "sbp", "hr", "temp")
VITAL_LABELS = {"rr": "Resp. rate", "spo2": "SpO2", "sbp": "Systolic BP", "hr": "Pulse",
                "temp": "Temperature"}
VITAL_UNITS = {"rr": "/min", "spo2": "%", "sbp": "mmHg", "hr": "/min", "temp": "°C"}
SCORE_FUNCS = {
    "rr": news2.score_respiration,
    "sbp": news2.score_systolic,
    "hr": news2.score_pulse,
    "temp": news2.score_temperature,
}


def ols(xs, ys):
    """Least-squares line through (xs, ys). Returns (slope, intercept, r2).

    r2 is 0.0 when y is constant (a flat line explains nothing new) and slope is 0.0 when
    all x are equal.
    """
    n = len(xs)
    if n != len(ys) or n < 2:
        raise ValueError("need at least two paired points")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return 0.0, my, 0.0
    slope = sxy / sxx
    intercept = my - slope * mx
    if syy == 0:
        return slope, intercept, 0.0
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = max(0.0, 1.0 - ss_res / syy)
    return slope, intercept, r2


def _vital_points(key, value, obs):
    if key == "spo2":
        if int(obs.get("scale", 1)) == 2:
            return news2.score_spo2_scale2(value, obs.get("o2", False))
        return news2.score_spo2_scale1(value)
    return SCORE_FUNCS[key](value)


def analyse(readings, window=None, horizon_h=None):
    """Analyse the most recent readings of one patient.

    readings: list of dicts with 't' (hours), the five vitals, 'o2', 'acvpu', 'scale' and
    'score' (aggregate NEWS2 of that reading). Oldest first.
    """
    window = window or config.TREND_WINDOW
    horizon = config.TREND_HORIZON_H if horizon_h is None else horizon_h
    recent = readings[-window:]
    result = {"enough_data": len(recent) >= config.TREND_MIN_READINGS, "window": len(recent),
              "horizon_h": horizon, "vitals": [], "score_slope": 0.0, "score_r2": 0.0,
              "projected_score": None, "current_score": None, "early_warning": False,
              "reason": "", "worsening": []}
    if not recent:
        return result
    last = recent[-1]
    result["current_score"] = last["score"]
    if not result["enough_data"]:
        result["reason"] = "Collecting readings (%d/%d)" % (len(recent),
                                                            config.TREND_MIN_READINGS)
        return result

    ts = [r["t"] for r in recent]
    projected = dict(last)
    worsening = []
    for key in VITALS:
        ys = [float(r[key]) for r in recent]
        slope, intercept, r2 = ols(ts, ys)
        delta = slope * horizon
        significant = r2 >= config.TREND_MIN_R2 and abs(delta) >= config.TREND_MIN_DELTA[key]
        fitted_now = intercept + slope * ts[-1]
        proj_val = fitted_now + delta if significant else float(last[key])
        if key == "spo2":
            proj_val = min(100.0, proj_val)
        proj_val = max(proj_val, 0.0)
        now_pts = _vital_points(key, last[key], last)
        proj_pts = _vital_points(key, proj_val, last)
        is_worse = significant and (proj_pts > now_pts or _away_from_normal(
            key, fitted_now, proj_val, last))
        if is_worse:
            worsening.append(key)
        projected[key] = proj_val
        result["vitals"].append({
            "key": key, "label": VITAL_LABELS[key], "unit": VITAL_UNITS[key],
            "slope_per_h": round(slope, 3), "r2": round(r2, 3), "significant": significant,
            "current": last[key], "projected": round(proj_val, 1),
            "points_now": now_pts, "points_projected": proj_pts, "worsening": is_worse,
        })

    s_slope, _, s_r2 = ols(ts, [float(r["score"]) for r in recent])
    result["score_slope"] = round(s_slope, 3)
    result["score_r2"] = round(s_r2, 3)
    proj_obs = {k: projected[k] for k in VITALS}
    proj_obs.update(o2=last.get("o2", False), acvpu=last.get("acvpu", "A"),
                    scale=last.get("scale", 1))
    proj_score = news2.calculate(proj_obs)["total"]
    result["projected_score"] = proj_score
    result["worsening"] = worsening

    current = last["score"]
    below_medium = current < config.NEWS2_MEDIUM_THRESHOLD
    rule_a = (proj_score >= config.NEWS2_MEDIUM_THRESHOLD
              and proj_score - current >= config.TREND_MIN_PROJECTED_RISE
              and len(worsening) >= config.TREND_MIN_WORSENING_VITALS)
    rule_b = (s_slope >= config.SCORE_SLOPE_ALERT and s_r2 >= config.SCORE_SLOPE_MIN_R2
              and current >= config.SCORE_SLOPE_MIN_CURRENT)
    if below_medium and (rule_a or rule_b):
        result["early_warning"] = True
        parts = []
        if rule_a:
            parts.append("projected NEWS2 %d in %g h (now %d)" % (proj_score, horizon, current))
        if rule_b:
            parts.append("score rising %+.1f/h" % s_slope)
        names = ", ".join("%s %s" % (VITAL_LABELS[k], "↑" if _rising(result, k) else "↓")
                          for k in worsening)
        result["reason"] = "; ".join(parts) + ((" — " + names) if names else "")
    elif s_slope >= 0.5 and s_r2 >= 0.4:
        result["reason"] = "Score drifting up %+.1f/h" % s_slope
    elif s_slope <= -0.5 and s_r2 >= 0.4:
        result["reason"] = "Score improving %+.1f/h" % s_slope
    else:
        result["reason"] = "Stable"
    return result


# Centre of the 0-point range for each vital; moving away from it is "worsening".
NORMAL_CENTRE = {"rr": 16.0, "spo2": 100.0, "sbp": 165.0, "hr": 70.0, "temp": 37.0}


def _away_from_normal(key, now, proj, obs):
    centre = NORMAL_CENTRE[key]
    if key == "spo2" and int(obs.get("scale", 1)) == 2:
        centre = 90.0          # Scale 2 target range 88-92 %
    if (now - centre) * (proj - centre) < 0:
        return False          # heading back through the normal range: improving
    return abs(proj - centre) > abs(now - centre)


def _rising(result, key):
    for v in result["vitals"]:
        if v["key"] == key:
            return v["slope_per_h"] > 0
    return False


def direction(result):
    """'rising' | 'falling' | 'stable' for the aggregate score trend."""
    if result["early_warning"] or (result["score_slope"] >= 0.5 and result["score_r2"] >= 0.4):
        return "rising"
    if result["score_slope"] <= -0.5 and result["score_r2"] >= 0.4:
        return "falling"
    return "stable"
