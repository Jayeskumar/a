"""National Early Warning Score 2 (NEWS2), Royal College of Physicians, 2017.

Implemented from the published NEWS2 chart (Chart 1: scoring system, Chart 4: clinical
response). Pure functions, no I/O. Every threshold below is the published one; the
tables are also served to the UI as the on-screen reference so there is one source of truth.

Input precision follows the paper chart: respiration rate, SpO2, systolic BP and pulse are
whole numbers; temperature has one decimal place. Inputs are rounded half-up to that
precision before scoring (e.g. 36.05 C -> 36.1 C).
"""

import math

from . import config

INF = float("inf")

# Each table: list of (upper bound inclusive, points, label). The first row whose upper
# bound is >= value applies. Values are rounded to chart precision first.
RESP_TABLE = [(8, 3, "≤8"), (11, 1, "9–11"), (20, 0, "12–20"), (24, 2, "21–24"), (INF, 3, "≥25")]
SPO2_SCALE1_TABLE = [(91, 3, "≤91"), (93, 2, "92–93"), (95, 1, "94–95"), (INF, 0, "≥96")]
SBP_TABLE = [(90, 3, "≤90"), (100, 2, "91–100"), (110, 1, "101–110"), (219, 0, "111–219"),
             (INF, 3, "≥220")]
PULSE_TABLE = [(40, 3, "≤40"), (50, 1, "41–50"), (90, 0, "51–90"), (110, 1, "91–110"),
               (130, 2, "111–130"), (INF, 3, "≥131")]
TEMP_TABLE = [(35.0, 3, "≤35.0"), (36.0, 1, "35.1–36.0"), (38.0, 0, "36.1–38.0"),
              (39.0, 1, "38.1–39.0"), (INF, 2, "≥39.1")]
# SpO2 Scale 2 (for patients with confirmed hypercapnic respiratory failure, target 88-92%).
# Below 88 it is a simple table; at >=93 the score depends on whether the patient is on oxygen.
SPO2_SCALE2_LOW_TABLE = [(83, 3, "≤83"), (85, 2, "84–85"), (87, 1, "86–87"), (92, 0, "88–92")]
SPO2_SCALE2_ON_O2_TABLE = [(94, 1, "93–94 on oxygen"), (96, 2, "95–96 on oxygen"),
                           (INF, 3, "≥97 on oxygen")]

ACVPU = {
    "A": "Alert",
    "C": "New confusion",
    "V": "Responds to voice",
    "P": "Responds to pain",
    "U": "Unresponsive",
}

PARAM_META = {
    "rr": ("Respiration rate", "/min"),
    "spo2": ("SpO2", "%"),
    "o2": ("Air or oxygen?", ""),
    "sbp": ("Systolic BP", "mmHg"),
    "hr": ("Pulse", "/min"),
    "acvpu": ("Consciousness", ""),
    "temp": ("Temperature", "°C"),
}

BANDS = {
    # key: (rank, label, colour key)
    "low": (0, "Low", "low"),
    "low_medium": (1, "Low–medium", "lowmed"),
    "medium": (2, "Medium", "medium"),
    "high": (3, "High", "high"),
}

# RCP NEWS2 Chart 4 - clinical response to NEWS2 trigger thresholds.
RESPONSES = {
    "zero": {
        "frequency": "Minimum 12-hourly",
        "response": "Continue routine NEWS2 monitoring.",
    },
    "low": {
        "frequency": "Minimum 4–6-hourly",
        "response": ("Inform registered nurse, who must assess the patient. Registered nurse "
                     "decides whether increased frequency of clinical monitoring or an "
                     "escalation of clinical care is required."),
    },
    "low_medium": {
        "frequency": "Minimum 1-hourly",
        "response": ("Registered nurse to inform the medical team caring for the patient, who "
                     "will review and decide whether escalation of care is necessary."),
    },
    "medium": {
        "frequency": "Minimum 1-hourly",
        "response": ("Registered nurse to immediately inform the medical team caring for the "
                     "patient. Registered nurse to request urgent assessment by a clinician or "
                     "team with core competencies in the care of acutely ill patients. Provide "
                     "clinical care in an environment with monitoring facilities."),
    },
    "high": {
        "frequency": "Continuous monitoring of vital signs",
        "response": ("Registered nurse to immediately inform the medical team caring for the "
                     "patient - at least at specialist registrar level. Emergency assessment by "
                     "a team with critical-care competencies, including practitioner(s) with "
                     "advanced airway management skills. Consider transfer of care to a level "
                     "2 or 3 facility (HDU or ICU). Clinical care in an environment with "
                     "monitoring facilities."),
    },
}


def round_half_up(value, decimals=0):
    """Round like a nurse reading a chart (half away from zero for positives)."""
    factor = 10 ** decimals
    return math.floor(value * factor + 0.5) / factor


def _lookup(table, value):
    for upper, points, label in table:
        if value <= upper:
            return points, label
    raise ValueError("value outside table")  # unreachable: last row is +inf


def score_respiration(rr):
    return _lookup(RESP_TABLE, round_half_up(rr))[0]


def score_spo2_scale1(spo2):
    return _lookup(SPO2_SCALE1_TABLE, round_half_up(spo2))[0]


def _spo2_scale2(spo2, on_oxygen):
    s = round_half_up(spo2)
    if s <= 92:
        return _lookup(SPO2_SCALE2_LOW_TABLE, s)
    if not on_oxygen:
        return 0, "≥93 on air"
    return _lookup(SPO2_SCALE2_ON_O2_TABLE, s)


def score_spo2_scale2(spo2, on_oxygen):
    return _spo2_scale2(spo2, on_oxygen)[0]


def score_air_oxygen(on_oxygen):
    return 2 if on_oxygen else 0


def score_systolic(sbp):
    return _lookup(SBP_TABLE, round_half_up(sbp))[0]


def score_pulse(hr):
    return _lookup(PULSE_TABLE, round_half_up(hr))[0]


def score_consciousness(acvpu):
    code = str(acvpu).upper()
    if code not in ACVPU:
        raise ValueError("consciousness must be one of A, C, V, P, U")
    return 0 if code == "A" else 3


def score_temperature(temp):
    return _lookup(TEMP_TABLE, round_half_up(temp, 1))[0]


def band_for(total, any_three):
    """Clinical risk band. Aggregate thresholds take precedence over the single-3 rule."""
    if total >= config.NEWS2_HIGH_THRESHOLD:
        return "high"
    if total >= config.NEWS2_MEDIUM_THRESHOLD:
        return "medium"
    if any_three:
        return "low_medium"
    return "low"


def response_for(total, band):
    if band == "low" and total == 0:
        return RESPONSES["zero"]
    return RESPONSES[band]


def calculate(obs):
    """Score a validated observation dict.

    obs keys: rr, spo2, sbp, hr, temp (numbers), o2 (bool: supplemental oxygen),
    acvpu ('A'|'C'|'V'|'P'|'U'), scale (1|2; 2 = SpO2 Scale 2 for hypercapnic failure).
    Returns the aggregate, band, escalation response and a per-parameter breakdown.
    """
    scale = int(obs.get("scale", 1))
    on_o2 = bool(obs.get("o2", False))
    acvpu = str(obs.get("acvpu", "A")).upper()
    rr = round_half_up(obs["rr"])
    spo2 = round_half_up(obs["spo2"])
    sbp = round_half_up(obs["sbp"])
    hr = round_half_up(obs["hr"])
    temp = round_half_up(obs["temp"], 1)

    rows = []

    def add(key, value, points, band_label):
        label, unit = PARAM_META[key]
        rows.append({"key": key, "label": label, "value": value, "unit": unit,
                     "points": points, "range": band_label})

    p, lab = _lookup(RESP_TABLE, rr)
    add("rr", int(rr), p, lab)
    if scale == 2:
        p, lab = _spo2_scale2(spo2, on_o2)
        add("spo2", int(spo2), p, "Scale 2: " + lab)
    else:
        p, lab = _lookup(SPO2_SCALE1_TABLE, spo2)
        add("spo2", int(spo2), p, "Scale 1: " + lab)
    add("o2", "Oxygen" if on_o2 else "Air", score_air_oxygen(on_o2),
        "Supplemental oxygen" if on_o2 else "Room air")
    p, lab = _lookup(SBP_TABLE, sbp)
    add("sbp", int(sbp), p, lab)
    p, lab = _lookup(PULSE_TABLE, hr)
    add("hr", int(hr), p, lab)
    add("acvpu", acvpu, score_consciousness(acvpu), ACVPU[acvpu])
    p, lab = _lookup(TEMP_TABLE, temp)
    add("temp", temp, p, lab)

    total = sum(r["points"] for r in rows)
    red = [r["key"] for r in rows if r["points"] == 3]
    band = band_for(total, bool(red))
    rank, band_label, colour = BANDS[band]
    resp = response_for(total, band)
    return {
        "total": total,
        "band": band,
        "band_rank": rank,
        "band_label": band_label,
        "red_params": red,
        "scale": scale,
        "frequency": resp["frequency"],
        "response": resp["response"],
        "parameters": rows,
    }


def validate(raw):
    """Validate an untrusted observation dict. Returns (obs, errors)."""
    errors = {}
    obs = {}
    if not isinstance(raw, dict):
        return None, {"_": "body must be a JSON object"}
    for key in ("rr", "spo2", "sbp", "hr", "temp"):
        val = raw.get(key)
        label, unit = PARAM_META[key]
        if val is None or val == "":
            errors[key] = label + " is required"
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            errors[key] = label + " must be a number"
            continue
        if isinstance(val, bool) or math.isnan(num) or math.isinf(num):
            errors[key] = label + " must be a number"
            continue
        lo, hi = config.VALID_RANGES[key]
        if not lo <= num <= hi:
            errors[key] = "%s must be between %s and %s %s" % (label, lo, hi, unit)
            continue
        obs[key] = round_half_up(num, 1) if key == "temp" else int(round_half_up(num))
    o2 = raw.get("o2", False)
    if isinstance(o2, str):
        o2 = o2.strip().lower() in ("1", "true", "yes", "on", "oxygen")
    obs["o2"] = bool(o2)
    acvpu = str(raw.get("acvpu", "A")).strip().upper()
    if acvpu not in ACVPU:
        errors["acvpu"] = "Consciousness must be one of A, C, V, P, U"
    obs["acvpu"] = acvpu
    try:
        scale = int(raw.get("scale", 1))
    except (TypeError, ValueError):
        scale = 0
    if scale not in (1, 2):
        errors["scale"] = "SpO2 scale must be 1 or 2"
    obs["scale"] = scale
    if errors:
        return None, errors
    return obs, {}


def reference():
    """Threshold tables for display (generated from the same tables used for scoring)."""
    def rows(table):
        return [{"range": lab, "points": p, "upper": None if up == INF else up}
                for up, p, lab in table]
    return {
        "source": "Royal College of Physicians. National Early Warning Score (NEWS) 2. "
                  "London: RCP, 2017.",
        "parameters": [
            {"key": "rr", "label": "Respiration rate (per min)", "rows": rows(RESP_TABLE)},
            {"key": "spo2_1", "label": "SpO2 Scale 1 (%)", "rows": rows(SPO2_SCALE1_TABLE)},
            {"key": "spo2_2", "label": "SpO2 Scale 2 (%) – hypercapnic respiratory failure",
             "rows": rows(SPO2_SCALE2_LOW_TABLE) + [{"range": "≥93 on air", "points": 0,
                                                     "upper": None}]
             + rows(SPO2_SCALE2_ON_O2_TABLE)},
            {"key": "o2", "label": "Air or oxygen?",
             "rows": [{"range": "Air", "points": 0}, {"range": "Oxygen", "points": 2}]},
            {"key": "sbp", "label": "Systolic BP (mmHg)", "rows": rows(SBP_TABLE)},
            {"key": "hr", "label": "Pulse (per min)", "rows": rows(PULSE_TABLE)},
            {"key": "acvpu", "label": "Consciousness",
             "rows": [{"range": "Alert", "points": 0},
                      {"range": "New confusion, Voice, Pain, Unresponsive (CVPU)",
                       "points": 3}]},
            {"key": "temp", "label": "Temperature (°C)", "rows": rows(TEMP_TABLE)},
        ],
        "bands": [
            {"band": "low", "label": "Low", "rule": "Aggregate 0–4",
             "frequency": "0: minimum 12-hourly; 1–4: minimum 4–6-hourly",
             "response": RESPONSES["low"]["response"]},
            {"band": "low_medium", "label": "Low–medium",
             "rule": "Red score: 3 in any single parameter",
             "frequency": RESPONSES["low_medium"]["frequency"],
             "response": RESPONSES["low_medium"]["response"]},
            {"band": "medium", "label": "Medium", "rule": "Aggregate 5–6",
             "frequency": RESPONSES["medium"]["frequency"],
             "response": RESPONSES["medium"]["response"]},
            {"band": "high", "label": "High", "rule": "Aggregate 7 or more",
             "frequency": RESPONSES["high"]["frequency"],
             "response": RESPONSES["high"]["response"]},
        ],
        "notes": [
            "Use SpO2 Scale 2 only for patients with confirmed hypercapnic respiratory "
            "failure (target 88–92%), as prescribed by a clinician; otherwise use Scale 1.",
            "'C' means new-onset confusion (or disorientation/agitation) - scores 3.",
            "Scores 5–6 are the key threshold for urgent ward-based response.",
        ],
    }
