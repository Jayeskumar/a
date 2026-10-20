"""Transparent donor ranking for an emergency request.

score = 0.30 * compatibility + 0.30 * proximity + 0.25 * response + 0.15 * fairness

  compatibility  1.0 exact match; -0.25 if Rh-negative cells go to an Rh-positive patient;
                 -0.25 if a different (compatible) ABO group is used
  proximity      exp(-travel_minutes / tau[urgency])          (haversine km -> road minutes)
  response       Beta-smoothed historical acceptance (accepted + 2) / (alerts + 4)
  fairness       min(1, days since last alert / 14)           (spreads load, avoids spamming)

Hard gates (excluded with the reason shown): red-cell incompatible, marked unavailable,
or failing an eligibility rule (interval, age, weight, deferral).
"""
import datetime as dt
import math

from . import compat
from .config import (DISTANCE_WILLINGNESS_KM, FAIRNESS_WINDOW_DAYS, MAX_UNITS_PER_REQUEST,
                     RESPONSE_PRIOR, SCREEN_PASS_PROB, SHOWUP_PROB, URGENCIES, URGENCY_TAU_MIN,
                     W_COMPAT, W_DISTANCE, W_FAIRNESS, W_RESPONSE, WAVE_BUFFER, WAVE_MAX, WAVE_MIN)
from .eligibility import donor_profile, evaluate
from .geo import haversine_km, travel_minutes


class RequestError(ValueError):
    pass


def response_estimate(received, accepted, prior=RESPONSE_PRIOR):
    a, b = prior
    received = max(0, int(received or 0))
    accepted = max(0, min(int(accepted or 0), received))
    return (accepted + a) / (received + a + b)


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    return dt.datetime.fromisoformat(str(value))


def fairness_score(last_contacted, now):
    lc = _parse_dt(last_contacted)
    if lc is None:
        return 1.0, "Never alerted before", None
    days = max(0.0, (now - lc).total_seconds() / 86400.0)
    if days < 1:
        ago = "%d h ago" % max(0, round(days * 24))
    else:
        ago = "%d days ago" % round(days)
    return min(1.0, days / FAIRNESS_WINDOW_DAYS), "Last alerted %s" % ago, days


def proximity_score(travel_min, urgency):
    return math.exp(-travel_min / URGENCY_TAU_MIN[urgency])


def normalize_request(req, hospitals):
    if not isinstance(req, dict):
        raise RequestError("request must be a JSON object")
    try:
        group = compat.normalize(req.get("group", ""))
    except compat.GroupError as e:
        raise RequestError(str(e))
    urgency = str(req.get("urgency", "urgent")).lower()
    if urgency not in URGENCIES:
        raise RequestError("urgency must be one of %s" % ", ".join(URGENCIES))
    try:
        units = int(req.get("units", 1))
    except (TypeError, ValueError):
        raise RequestError("units must be an integer")
    if not 1 <= units <= MAX_UNITS_PER_REQUEST:
        raise RequestError("units must be between 1 and %d" % MAX_UNITS_PER_REQUEST)
    hid = req.get("hospital_id")
    if hid:
        h = next((h for h in hospitals if h["id"] == hid), None)
        if h is None:
            raise RequestError("unknown hospital_id %r" % hid)
        lat, lon, place = h["lat"], h["lon"], h["name"]
    else:
        try:
            lat, lon = float(req.get("lat")), float(req.get("lon"))
        except (TypeError, ValueError):
            raise RequestError("give hospital_id or numeric lat/lon")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise RequestError("lat/lon out of range")
        place = str(req.get("place") or "Custom location")[:60]
    return {"group": group, "urgency": urgency, "units": units, "hospital_id": hid,
            "lat": lat, "lon": lon, "place": place}


def score_donor(donor, req, now):
    """Score one eligible + compatible donor; returns a dict with per-component points."""
    km = haversine_km(donor["lat"], donor["lon"], req["lat"], req["lon"])
    minutes = travel_minutes(km)
    c = compat.compat_score(donor["group"], req["group"])
    p = proximity_score(minutes, req["urgency"])
    r = response_estimate(donor.get("alerts_received"), donor.get("alerts_accepted"))
    f, f_detail, f_days = fairness_score(donor.get("last_contacted"), now)
    rec, acc = int(donor.get("alerts_received") or 0), int(donor.get("alerts_accepted") or 0)
    comps = [
        {"key": "compat", "label": "Compatibility", "weight": W_COMPAT, "value": round(c, 3),
         "points": round(W_COMPAT * c, 4), "detail": compat.compat_reason(donor["group"], req["group"])},
        {"key": "distance", "label": "Proximity", "weight": W_DISTANCE, "value": round(p, 3),
         "points": round(W_DISTANCE * p, 4),
         "detail": "%.1f km away, ~%d min (tau %d min for %s)" % (
             km, round(minutes), URGENCY_TAU_MIN[req["urgency"]], req["urgency"])},
        {"key": "response", "label": "Response history", "weight": W_RESPONSE, "value": round(r, 3),
         "points": round(W_RESPONSE * r, 4),
         "detail": ("Accepted %d of %d past alerts" % (acc, rec)) if rec else "No alert history yet (prior 50%)"},
        {"key": "fairness", "label": "Fairness", "weight": W_FAIRNESS, "value": round(f, 3),
         "points": round(W_FAIRNESS * f, 4), "detail": f_detail},
    ]
    score = sum(x["points"] for x in comps)
    # chance this donor ends up giving a unit, as the planner estimates it (used for wave size)
    p_unit = r / (1 + km / DISTANCE_WILLINGNESS_KM) * SHOWUP_PROB * SCREEN_PASS_PROB
    return {"km": round(km, 2), "travel_min": round(minutes, 1), "score": round(score, 4),
            "components": comps, "p_unit_est": round(p_unit, 3),
            "exact": donor["group"] == req["group"], "fairness_days": f_days}


def rank(donors, req, now, today):
    """Rank every donor in the registry for request `req` (already normalized)."""
    ranked, excluded = [], []
    counts = {"registry": len(donors), "compatible": 0, "incompatible": 0, "unavailable": 0,
              "ineligible": 0, "ranked": 0, "ineligible_by_rule": {}}
    for d in donors:
        base = {"id": d["id"], "name": d["name"], "group": d["group"], "town": d["town"],
                "lat": d["lat"], "lon": d["lon"], "sex": d["sex"]}
        if not compat.red_cell_compatible(d["group"], req["group"]):
            counts["incompatible"] += 1
            excluded.append(dict(base, code="incompatible", category="Incompatible",
                                 reason=compat.compat_reason(d["group"], req["group"])))
            continue
        counts["compatible"] += 1
        if not d.get("available", True):
            counts["unavailable"] += 1
            excluded.append(dict(base, code="unavailable", category="Unavailable",
                                 reason="Marked unavailable by donor (travelling / opted out)"))
            continue
        el = evaluate(donor_profile(d), today)
        if not el["eligible"]:
            counts["ineligible"] += 1
            for code in el["codes"]:
                counts["ineligible_by_rule"][code] = counts["ineligible_by_rule"].get(code, 0) + 1
            nxt = el["next_eligible_date"]
            excluded.append(dict(base, code=el["codes"][0], category="Ineligible",
                                 reason="; ".join(el["reasons"]) + (" - eligible from %s" % nxt if nxt else ""),
                                 next_eligible_date=nxt))
            continue
        s = score_donor(d, req, now)
        ranked.append(dict(base, age=el["age"], **s))
    ranked.sort(key=lambda x: (-x["score"], x["km"], x["id"]))
    for i, x in enumerate(ranked):
        x["rank"] = i + 1
        x["explanation"] = explain(x, ranked[i + 1] if i + 1 < len(ranked) else None)
    counts["ranked"] = len(ranked)
    cat_order = {"Ineligible": 0, "Unavailable": 1, "Incompatible": 2}
    excluded.sort(key=lambda x: (cat_order[x["category"]], x["id"]))
    return {"ranked": ranked, "excluded": excluded, "counts": counts,
            "first_wave": plan_first_wave(ranked, req["units"])}


def explain(x, nxt=None):
    c = {k["key"]: k for k in x["components"]}
    parts = [c["compat"]["detail"], c["distance"]["detail"].split(" (")[0],
             c["response"]["detail"], c["fairness"]["detail"]]
    text = "Score %.1f = %s." % (x["score"] * 100, " + ".join(
        "%s %.1f" % (k["label"].lower(), k["points"] * 100) for k in x["components"]))
    text += " " + "; ".join(parts) + "."
    if nxt is not None:
        diffs = sorted(((k["points"] - n["points"], k["label"].lower())
                        for k, n in zip(x["components"], nxt["components"])), reverse=True)
        lead, label = diffs[0]
        if lead > 0:
            text += " Ahead of #%d mainly on %s (+%.1f)." % (x["rank"] + 1, label, lead * 100)
    return text


def plan_first_wave(ranked, units):
    """How many top donors to alert first: enough expected units for need + buffer."""
    if not ranked:
        return 0
    target = math.ceil(units * (1 + WAVE_BUFFER))
    total, n = 0.0, 0
    for x in ranked:
        if n >= WAVE_MAX or (total >= target and n >= WAVE_MIN):
            break
        total += x["p_unit_est"]
        n += 1
    return max(min(WAVE_MIN, len(ranked)), n)
