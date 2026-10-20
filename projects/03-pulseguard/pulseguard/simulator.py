"""Deterministic ward simulator: 12 virtual patients, one reading every 15 minutes.

Each vital = baseline + severity(t) * delta + slow AR(1) physiological drift + measurement
noise, all drawn from random.Random seeded per (seed, bed). Same seed -> identical ward.

Profiles (illustrative, not real patients):
  * 3 deteriorate (sepsis-like, hospital-acquired pneumonia, upper-GI bleed),
  * 2 improve (post-op settling, asthma being weaned off oxygen),
  * 7 are stable, including a COPD patient scored on SpO2 Scale 2.

Run `python -m pulseguard.simulator` to export the default ward to data/sample_ward.json.
"""

import json
import os
import random
import sys

from . import config

# Slow physiological drift (AR(1), phi) and per-reading measurement noise, per vital (SD).
# Rough, assumed magnitudes chosen so stable patients wander realistically.
DRIFT_PHI = 0.85
DRIFT_SD = {"rr": 0.45, "spo2": 0.35, "sbp": 2.2, "hr": 1.6, "temp": 0.05}
MEAS_SD = {"rr": 0.8, "spo2": 0.6, "sbp": 4.0, "hr": 2.5, "temp": 0.06}
VITALS = ("rr", "spo2", "sbp", "hr", "temp")


def _p(pid, bed, name, age, sex, diagnosis, kind, base, delta=None, onset_h=0.0,
       duration_h=1.0, scale=1, o2_at=None, o2_boost=0.0, confusion_at=None, o2_base=False):
    return {"id": pid, "bed": bed, "name": name, "age": age, "sex": sex,
            "diagnosis": diagnosis, "kind": kind, "base": base, "delta": delta or {},
            "onset_h": onset_h, "duration_h": duration_h, "scale": scale, "o2_at": o2_at,
            "o2_boost": o2_boost, "confusion_at": confusion_at, "o2_base": o2_base}


def base(rr, spo2, sbp, hr, temp):
    return {"rr": rr, "spo2": spo2, "sbp": sbp, "hr": hr, "temp": temp}


PROFILES = [
    _p("P01", 1, "Ramesh Kumar", 67, "M", "Urinary tract infection, type 2 diabetes",
       "deteriorating", base(16, 97, 128, 82, 37.2),
       delta={"rr": 12, "spo2": -4, "sbp": -40, "hr": 46, "temp": 2.3},
       onset_h=4.0, duration_h=12.0, confusion_at=0.85),
    _p("P02", 2, "Lakshmi Devi", 58, "F", "Post-op day 2, laparotomy",
       "deteriorating", base(17, 96, 124, 84, 37.1),
       delta={"rr": 11, "spo2": -8, "sbp": -12, "hr": 30, "temp": 1.6},
       onset_h=8.0, duration_h=10.0, o2_at=0.6, o2_boost=4.0),
    _p("P03", 3, "Arjun Reddy", 45, "M", "Peptic ulcer with melaena",
       "deteriorating", base(15, 98, 126, 76, 36.8),
       delta={"rr": 8, "spo2": -2, "sbp": -38, "hr": 50, "temp": 0.0},
       onset_h=12.0, duration_h=6.0),
    _p("P04", 4, "Mohammed Ismail", 72, "M", "COPD, hypercapnic respiratory failure",
       "stable", base(19, 89, 138, 86, 36.9), scale=2),
    _p("P05", 5, "Priya Sharma", 34, "F", "Dengue fever day 4, platelet watch",
       "stable", base(18, 98, 112, 88, 37.8)),
    _p("P06", 6, "Suresh Babu", 61, "M", "Diabetic foot ulcer",
       "stable", base(16, 97, 142, 78, 37.0)),
    _p("P07", 7, "Kavitha Rajan", 49, "F", "Post-op day 1, cholecystectomy",
       "improving", base(16, 97, 122, 80, 37.0),
       delta={"rr": 5, "spo2": -2, "sbp": -6, "hr": 24, "temp": 0.9},
       onset_h=0.0, duration_h=10.0),
    _p("P08", 8, "Venkatesh Iyer", 80, "M", "Heart failure on IV diuretics",
       "stable", base(18, 95, 120, 84, 36.6)),
    _p("P09", 9, "Anjali Gupta", 27, "F", "Acute asthma, improving",
       "improving", base(16, 97, 118, 84, 36.9),
       delta={"rr": 6, "spo2": -3, "sbp": 0, "hr": 20, "temp": 0.0},
       onset_h=0.0, duration_h=12.0, o2_at=0.5, o2_boost=3.0),
    _p("P10", 10, "Rajesh Patel", 55, "M", "Cellulitis, IV antibiotics",
       "stable", base(16, 97, 134, 80, 37.4)),
    _p("P11", 11, "Fatima Begum", 66, "F", "Ischaemic stroke, rehabilitation",
       "stable", base(15, 96, 158, 72, 36.7)),
    _p("P12", 12, "Deepak Singh", 39, "M", "Tibia fracture after road accident",
       "stable", base(17, 98, 130, 84, 37.3)),
]


def _ramp(x):
    """Progress 0..1 -> severity 0..1. Blend of linear and smoothstep: subtle start."""
    x = min(1.0, max(0.0, x))
    return 0.5 * x + 0.5 * x * x * (3 - 2 * x)


def severity(profile, t):
    kind = profile["kind"]
    if kind == "stable":
        return 0.0
    x = (t - profile["onset_h"]) / profile["duration_h"]
    s = _ramp(x)
    return 1.0 - s if kind == "improving" else s


def jitter_profile(profile, rng):
    """Seed-dependent variation of onset and speed (used by the multi-seed evaluation)."""
    p = dict(profile)
    if p["kind"] == "deteriorating":
        p["onset_h"] = max(1.0, p["onset_h"] + rng.uniform(-2.0, 2.0))
        p["duration_h"] = p["duration_h"] * rng.uniform(0.75, 1.3)
        p["delta"] = {k: v * rng.uniform(0.85, 1.15) for k, v in p["delta"].items()}
    elif p["kind"] == "improving":
        p["duration_h"] = p["duration_h"] * rng.uniform(0.8, 1.25)
    return p


def generate_patient(profile, seed=config.DEFAULT_SEED, steps=config.SCENARIO_STEPS,
                     jitter=False):
    """Return (profile_used, readings) for steps 0..steps inclusive."""
    rng = random.Random(seed * 1000 + profile["bed"])
    prof = jitter_profile(profile, rng) if jitter else dict(profile)
    drift = {k: rng.gauss(0, DRIFT_SD[k] / (1 - DRIFT_PHI ** 2) ** 0.5) for k in VITALS}
    readings = []
    for step in range(steps + 1):
        t = step / config.STEPS_PER_HOUR
        sev = severity(prof, t)
        on_o2 = prof["o2_base"] or (prof["o2_at"] is not None and sev >= prof["o2_at"])
        r = {"step": step, "t": t, "source": "monitor"}
        for k in VITALS:
            drift[k] = DRIFT_PHI * drift[k] + rng.gauss(0, DRIFT_SD[k])
            val = prof["base"][k] + sev * prof["delta"].get(k, 0.0) + drift[k] \
                + rng.gauss(0, MEAS_SD[k])
            if k == "spo2" and on_o2:
                val += prof["o2_boost"]
            r[k] = val
        r["rr"] = max(4, int(round(r["rr"])))
        r["spo2"] = min(100, int(round(r["spo2"])))
        r["sbp"] = int(round(r["sbp"]))
        r["hr"] = int(round(r["hr"]))
        r["temp"] = round(r["temp"], 1)
        r["o2"] = bool(on_o2)
        r["acvpu"] = "C" if (prof["confusion_at"] is not None
                             and sev >= prof["confusion_at"]) else "A"
        r["scale"] = prof["scale"]
        readings.append(r)
    return prof, readings


def generate_ward(seed=config.DEFAULT_SEED, steps=config.SCENARIO_STEPS, jitter=False):
    out = []
    for prof in PROFILES:
        used, readings = generate_patient(prof, seed, steps, jitter)
        out.append({"profile": used, "readings": readings})
    return out


def clock_label(t_hours):
    """Simulated hours since scenario start -> 'HH:MM' (scenario starts 06:00)."""
    total = int(round(config.SCENARIO_START_CLOCK_MIN + t_hours * 60))
    day = total // (24 * 60)
    hh = (total // 60) % 24
    mm = total % 60
    return ("%02d:%02d" % (hh, mm)) + (" (+%dd)" % day if day else "")


def export(path):
    ward = generate_ward()
    data = {"seed": config.DEFAULT_SEED, "reading_interval_min": config.READING_INTERVAL_MIN,
            "patients": [{"profile": {k: v for k, v in w["profile"].items()},
                          "readings": w["readings"]} for w in ward]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    return path


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "data",
                                                                  "sample_ward.json")
    print("wrote", export(target))
