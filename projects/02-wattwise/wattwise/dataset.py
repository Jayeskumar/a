"""Deterministic synthetic smart-meter dataset for a college campus.

Six buildings, hourly kWh for 8 weeks (Mon 24 Aug 2026 - Sun 18 Oct 2026),
with daily/weekly occupancy patterns, a temperature-driven cooling load,
a public holiday, a "switch-off" campaign in the last two weeks, and a list of
injected waste events that act as ground truth for the anomaly detector.

Everything is driven by ``random.Random(seed)`` so the same seed always gives
exactly the same numbers. The data is SYNTHETIC - shaped to look like a
typical Indian engineering campus, not measured from a real one.
"""

import csv
import json
import math
import os
import random
from datetime import date, datetime, timedelta

from . import config

START_DATE = date(2026, 8, 24)   # a Monday
N_DAYS = 56                      # 8 weeks
FORECAST_DAYS = 7
DEFAULT_SEED = 2026

HOLIDAYS = {
    date(2026, 10, 2): "Gandhi Jayanti",
}

DAYTYPES = ("workday", "saturday", "sunday")  # holidays behave like Sunday


def _shape(segments, default=0.0):
    """Build a 24-hour profile from (start_hour, end_hour, level) segments."""
    prof = [default] * 24
    for start, end, level in segments:
        for h in range(start, end):
            prof[h % 24] = level
    return prof


# ------------------------------------------------------------------ buildings
# kw values are average kW (= kWh per hour). Shares are the end-use split an
# energy auditor would estimate on a walk-through (assumed, used by what-if).
_HOSTEL_WORK = _shape([(0, 5, 0.35), (5, 6, 0.5), (6, 9, 0.9), (9, 16, 0.22),
                       (16, 18, 0.55), (18, 23, 1.0), (23, 24, 0.6)])
_HOSTEL_OFF = _shape([(0, 6, 0.4), (6, 9, 0.6), (9, 18, 0.62), (18, 23, 1.0),
                      (23, 24, 0.7)])
_HOSTEL_AC = _shape([(0, 6, 1.0), (6, 21, 0.3), (21, 24, 1.0)])

_LAB_WORK = _shape([(8, 9, 0.5), (9, 17, 1.0), (17, 19, 0.5), (19, 20, 0.2)])
_LAB_SAT = _shape([(9, 13, 0.4)])
_LIB_WORK = _shape([(8, 9, 0.6), (9, 20, 0.9), (20, 21, 0.3)])
_LIB_SAT = _shape([(9, 14, 0.6)])
_ADMIN_WORK = _shape([(8, 9, 0.4), (9, 17, 1.0), (17, 18, 0.5)])
_ADMIN_SAT = _shape([(9, 13, 0.5)])
_CANTEEN = _shape([(5, 6, 0.4), (6, 10, 1.0), (10, 12, 0.6), (12, 15, 1.0),
                   (15, 17, 0.5), (17, 21, 0.9), (21, 22, 0.3)])
_CANTEEN_SUN = [v * 0.7 for v in _CANTEEN]
_ZERO = [0.0] * 24

BUILDINGS = [
    {
        "id": "hostel_a", "name": "Hostel Block A", "type": "Residential",
        "base_kw": 12.0, "occ_kw": 45.0, "ac_kw_per_deg": 0.6,
        "occ": {"workday": _HOSTEL_WORK, "saturday": _HOSTEL_OFF, "sunday": _HOSTEL_OFF},
        "ac": {"workday": _HOSTEL_AC, "saturday": _HOSTEL_AC, "sunday": _HOSTEL_AC},
        "shares": {"ac": 0.15, "lighting": 0.25, "fans": 0.35},
        "roof_m2": 1200, "auto_off": False, "campaign": None,
    },
    {
        "id": "hostel_b", "name": "Hostel Block B", "type": "Residential",
        "base_kw": 10.0, "occ_kw": 40.0, "ac_kw_per_deg": 0.8,
        "occ": {"workday": _HOSTEL_WORK, "saturday": _HOSTEL_OFF, "sunday": _HOSTEL_OFF},
        "ac": {"workday": _HOSTEL_AC, "saturday": _HOSTEL_AC, "sunday": _HOSTEL_AC},
        "shares": {"ac": 0.18, "lighting": 0.25, "fans": 0.32},
        "roof_m2": 1000, "auto_off": False,
        "campaign": {"start_day": 42, "factor": 0.90, "label": "Switch-off pledge drive"},
    },
    {
        "id": "cse_lab", "name": "CSE Lab Block", "type": "Academic",
        "base_kw": 3.0, "occ_kw": 55.0, "ac_kw_per_deg": 2.5,
        "occ": {"workday": _LAB_WORK, "saturday": _LAB_SAT, "sunday": _ZERO},
        "ac": {"workday": _LAB_WORK, "saturday": _LAB_SAT, "sunday": _ZERO},
        "shares": {"ac": 0.40, "lighting": 0.15, "fans": 0.05},
        "roof_m2": 1500, "auto_off": True, "campaign": None,
    },
    {
        "id": "library", "name": "Central Library", "type": "Academic",
        "base_kw": 4.0, "occ_kw": 25.0, "ac_kw_per_deg": 3.0,
        "occ": {"workday": _LIB_WORK, "saturday": _LIB_SAT, "sunday": _ZERO},
        "ac": {"workday": _LIB_WORK, "saturday": _LIB_SAT, "sunday": _ZERO},
        "shares": {"ac": 0.50, "lighting": 0.25, "fans": 0.05},
        "roof_m2": 900, "auto_off": True, "campaign": None,
    },
    {
        "id": "admin", "name": "Admin Block", "type": "Office",
        "base_kw": 5.0, "occ_kw": 20.0, "ac_kw_per_deg": 3.2,
        "occ": {"workday": _ADMIN_WORK, "saturday": _ADMIN_SAT, "sunday": _ZERO},
        "ac": {"workday": _ADMIN_WORK, "saturday": _ADMIN_SAT, "sunday": _ZERO},
        "shares": {"ac": 0.45, "lighting": 0.20, "fans": 0.05},
        "roof_m2": 700, "auto_off": True,
        "campaign": {"start_day": 42, "factor": 1.04, "label": "New server room"},
    },
    {
        "id": "canteen", "name": "Main Canteen", "type": "Services",
        "base_kw": 8.0, "occ_kw": 30.0, "ac_kw_per_deg": 0.5,
        "occ": {"workday": _CANTEEN, "saturday": _CANTEEN, "sunday": _CANTEEN_SUN},
        "ac": {"workday": _CANTEEN, "saturday": _CANTEEN, "sunday": _CANTEEN_SUN},
        "shares": {"ac": 0.10, "lighting": 0.15, "fans": 0.20},
        "roof_m2": 600, "auto_off": False,
        "campaign": {"start_day": 42, "factor": 0.94, "label": "Kitchen equipment schedule"},
    },
]
BUILDING_IDS = [b["id"] for b in BUILDINGS]
BUILDING_BY_ID = {b["id"]: b for b in BUILDINGS}

# Injected waste events: (building, day index, start hour, hours, extra kW, kind)
# day 0 = Mon 24 Aug 2026. These are the ground truth for evaluation.
WASTE_EVENTS = [
    ("cse_lab", 3, 22, 8, 14.0, "night_load"),
    ("cse_lab", 13, 0, 7, 15.0, "night_load"),
    ("cse_lab", 30, 21, 9, 12.0, "night_load"),
    ("cse_lab", 51, 19, 11, 10.0, "night_load"),
    ("cse_lab", 54, 9, 8, 20.0, "weekend_ac"),
    ("admin", 5, 9, 9, 18.0, "weekend_ac"),
    ("admin", 27, 8, 10, 16.0, "weekend_ac"),
    ("admin", 48, 10, 8, 14.0, "weekend_ac"),
    ("library", 16, 21, 9, 6.0, "lights_left_on"),
    ("library", 41, 20, 10, 5.0, "lights_left_on"),
    ("library", 34, 10, 6, 15.0, "weekend_ac"),
    ("hostel_a", 22, 10, 6, 12.0, "empty_room_load"),
    ("hostel_a", 44, 10, 5, 10.0, "empty_room_load"),
    ("hostel_b", 37, 11, 5, 9.0, "empty_room_load"),
    ("hostel_b", 25, 1, 4, 4.0, "night_load"),        # deliberately subtle
    ("canteen", 10, 22, 8, 5.0, "equipment_left_on"),
    ("canteen", 52, 22, 8, 6.0, "equipment_left_on"),
    ("canteen", 19, 15, 3, 3.0, "equipment_left_on"),  # deliberately subtle
]


def daytype_of(d):
    """'workday' | 'saturday' | 'sunday' (holidays count as sunday)."""
    if d in HOLIDAYS or d.weekday() == 6:
        return "sunday"
    if d.weekday() == 5:
        return "saturday"
    return "workday"


def cooling_degrees(temp_c):
    return max(0.0, temp_c - config.COOLING_BASE_C)


class Dataset(object):
    """Container for the hourly campus data (lists, index = hour since start)."""

    def __init__(self, timestamps, temps, loads, events, forecast_temps, seed):
        self.timestamps = timestamps            # list[datetime], hourly
        self.temps = temps                      # list[float] degC
        self.loads = loads                      # {building_id: list[float] kWh}
        self.events = events                    # ground-truth waste events (dicts)
        self.forecast_temps = forecast_temps    # next 7 days, hourly degC
        self.seed = seed
        last = timestamps[-1]
        self.forecast_timestamps = [last + timedelta(hours=i + 1)
                                    for i in range(len(forecast_temps))]

    @property
    def n_hours(self):
        return len(self.timestamps)

    def daytypes(self, timestamps=None):
        ts = self.timestamps if timestamps is None else timestamps
        return [daytype_of(t.date()) for t in ts]


# ------------------------------------------------------------------ generator
def _temperature_series(rng, n_days):
    """Synthetic Tamil Nadu late-monsoon weather: hourly temperature in degC."""
    temps = []
    ar = 0.0
    for d in range(n_days):
        ar = 0.7 * ar + rng.gauss(0.0, 0.9)
        rainy = rng.random() < 0.15
        mean = 30.5 - 2.5 * d / 63.0 + ar - (2.0 if rainy else 0.0)
        amp = 2.0 if rainy else 3.5
        for h in range(24):
            temps.append(round(mean + amp * math.cos(2 * math.pi * (h - 14) / 24.0), 2))
    return temps


def generate(seed=DEFAULT_SEED):
    rng = random.Random(seed)
    n_hours = N_DAYS * 24
    all_temps = _temperature_series(rng, N_DAYS + FORECAST_DAYS)
    temps = all_temps[:n_hours]
    forecast_temps = all_temps[n_hours:]
    start = datetime(START_DATE.year, START_DATE.month, START_DATE.day)
    timestamps = [start + timedelta(hours=i) for i in range(n_hours)]

    loads = {}
    for b in BUILDINGS:
        series = []
        for d in range(N_DAYS):
            day = START_DATE + timedelta(days=d)
            dt = daytype_of(day)
            day_level = 1.0 + rng.gauss(0.0, 0.03)
            camp = b["campaign"]
            factor = camp["factor"] if camp and d >= camp["start_day"] else 1.0
            for h in range(24):
                i = d * 24 + h
                variable = (b["occ_kw"] * b["occ"][dt][h]
                            + b["ac_kw_per_deg"] * b["ac"][dt][h] * cooling_degrees(temps[i]))
                kw = b["base_kw"] * (1.0 + rng.gauss(0.0, 0.04)) \
                    + variable * factor * day_level * (1.0 + rng.gauss(0.0, 0.05))
                series.append(max(0.0, kw))
        loads[b["id"]] = series

    events = []
    for bid, day, hour, hours, extra, kind in WASTE_EVENTS:
        s = day * 24 + hour
        e = min(s + hours, n_hours)
        for i in range(s, e):
            loads[bid][i] += extra
        events.append({
            "building": bid, "start": timestamps[s].isoformat(),
            "end": timestamps[e - 1].isoformat(), "start_index": s, "end_index": e - 1,
            "hours": e - s, "extra_kw": extra, "kind": kind,
            "wasted_kwh": round(extra * (e - s), 2),
        })

    for bid in loads:
        loads[bid] = [round(v, 2) for v in loads[bid]]
    return Dataset(timestamps, temps, loads, events, forecast_temps, seed)


# ------------------------------------------------------------------ persistence
CSV_NAME = "meter_data.csv"
META_NAME = "meta.json"


def save(ds, data_dir):
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, CSV_NAME), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "temp_c"] + BUILDING_IDS)
        for i, t in enumerate(ds.timestamps):
            w.writerow([t.isoformat(), ds.temps[i]] + [ds.loads[b][i] for b in BUILDING_IDS])
    meta = {
        "seed": ds.seed,
        "note": "SYNTHETIC data generated by wattwise/dataset.py (deterministic).",
        "holidays": {k.isoformat(): v for k, v in HOLIDAYS.items()},
        "forecast_temps": ds.forecast_temps,
        "ground_truth_events": ds.events,
    }
    with open(os.path.join(data_dir, META_NAME), "w") as f:
        json.dump(meta, f, indent=1)


def load(data_dir):
    with open(os.path.join(data_dir, CSV_NAME), newline="") as f:
        r = csv.reader(f)
        header = next(r)
        bids = header[2:]
        timestamps, temps = [], []
        loads = {b: [] for b in bids}
        for row in r:
            timestamps.append(datetime.fromisoformat(row[0]))
            temps.append(float(row[1]))
            for b, v in zip(bids, row[2:]):
                loads[b].append(float(v))
    with open(os.path.join(data_dir, META_NAME)) as f:
        meta = json.load(f)
    return Dataset(timestamps, temps, loads, meta["ground_truth_events"],
                   meta["forecast_temps"], meta.get("seed", DEFAULT_SEED))


def load_or_generate(data_dir, seed=DEFAULT_SEED):
    """Load committed sample data, or generate (and save) it on first run."""
    try:
        ds = load(data_dir)
        if set(ds.loads) == set(BUILDING_IDS) and ds.n_hours == N_DAYS * 24:
            return ds
    except (OSError, ValueError, KeyError, StopIteration):
        pass
    ds = generate(seed)
    try:
        save(ds, data_dir)
    except OSError:
        pass  # read-only location: run from memory
    return ds
