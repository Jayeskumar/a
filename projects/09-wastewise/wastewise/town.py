"""Deterministic simulated town: wards, smart bins, depot, trucks and the bin fill-rate model.

The town is fictional (a 6 x 4 km street grid sized like a small Tamil Nadu municipality core).
Everything is derived from config.SEED, so every run and every test sees the same town.
"""

import datetime
import math
import random

from . import config as C

WASTE_TYPES = ("wet", "dry", "recyclable")

# Ward layout: id, display name, dominant zone, rectangle (x0, y0, x1, y1) in km, bins, households
WARDS = [
    ("W1", "Hill Temple", "temple", (0.0, 2.0, 2.0, 4.0), 6, 1800),
    ("W2", "Bus Stand", "commercial", (2.0, 2.0, 4.0, 4.0), 7, 1500),
    ("W3", "College Road", "institutional", (4.0, 2.0, 6.0, 4.0), 6, 1300),
    ("W4", "Weavers' Colony", "residential", (0.0, 0.0, 2.0, 2.0), 7, 2400),
    ("W5", "Santhai Market", "market", (2.0, 0.0, 4.0, 2.0), 8, 1700),
    ("W6", "Lake View", "residential", (4.0, 0.0, 6.0, 2.0), 6, 2100),
]

# Fixed beats of the municipal baseline: each truck owns two wards, in this order.
FIXED_BEATS = [("W1", "W4"), ("W2", "W5"), ("W3", "W6")]

# Day-of-week multipliers (Mon..Sun) per zone; normalised to mean 1 below.
_PROFILES = {
    "residential": [1.10, 0.95, 0.95, 0.95, 0.95, 1.05, 1.25],   # Sunday at home
    "commercial": [1.05, 1.05, 1.05, 1.05, 1.10, 1.20, 0.70],    # shops quiet on Sunday
    "market": [0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85],        # + market-day spike below
    "institutional": [1.15, 1.15, 1.15, 1.15, 1.10, 0.60, 0.35],  # college/school days
    "temple": [0.85, 0.90, 0.85, 0.90, 1.45, 1.05, 1.40],         # Friday & Sunday darshan
}
_MARKET_DAY_BOOST = {"market": 2.1, "commercial": 1.3, "residential": 1.05}
_MARKET_NEXT_DAY = {"market": 1.25}

_TYPE_WEIGHTS = {
    "market": (0.55, 0.20, 0.25),
    "commercial": (0.30, 0.35, 0.35),
    "residential": (0.45, 0.30, 0.25),
    "institutional": (0.30, 0.35, 0.35),
    "temple": (0.55, 0.25, 0.20),
}
_BASE_RATE = {  # fraction of capacity per day, weekly average (uniform range)
    "market": (0.36, 0.50),
    "commercial": (0.32, 0.48),
    "temple": (0.28, 0.44),
    "institutional": (0.27, 0.42),
    "residential": (0.20, 0.40),
}


def _profile(zone):
    p = list(_PROFILES[zone])
    if zone in _MARKET_DAY_BOOST:
        p[C.MARKET_WEEKDAY] *= _MARKET_DAY_BOOST[zone]
    if zone in _MARKET_NEXT_DAY:
        p[(C.MARKET_WEEKDAY + 1) % 7] *= _MARKET_NEXT_DAY[zone]
    m = sum(p) / 7.0
    return [round(v / m, 4) for v in p]


PROFILES = {z: _profile(z) for z in _PROFILES}


def _rng(*parts):
    """Independent deterministic stream for a tuple of ints (no str hashing: PYTHONHASHSEED-safe)."""
    s = C.SEED
    for p in parts:
        s = (s * 1000003 + int(p) + 7919) % (2 ** 61 - 1)
    return random.Random(s)


def date_of(day):
    return datetime.date.fromisoformat(C.START_DATE) + datetime.timedelta(days=day)


def weekday_of(day):
    return date_of(day).weekday()


def is_market_day(day):
    return weekday_of(day) == C.MARKET_WEEKDAY


class Bin:
    __slots__ = ("idx", "id", "ward", "zone", "x", "y", "capacity", "type", "base_rate", "profile")

    def __init__(self, idx, bid, ward, zone, x, y, capacity, wtype, base_rate):
        self.idx, self.id, self.ward, self.zone = idx, bid, ward, zone
        self.x, self.y, self.capacity, self.type = x, y, capacity, wtype
        self.base_rate = base_rate
        self.profile = PROFILES[zone]

    def to_json(self):
        return {"id": self.id, "ward": self.ward, "zone": self.zone, "x": self.x, "y": self.y,
                "capacity": self.capacity, "type": self.type,
                "base_rate": round(self.base_rate, 3)}


class Town:
    """Static description of the town plus the ground-truth fill model."""

    def __init__(self, seed=None):
        if seed is not None and seed != C.SEED:
            raise ValueError("use config.SEED (the town is defined by it)")
        self.wards = [{"id": w[0], "name": w[1], "zone": w[2], "rect": list(w[3]),
                       "households": w[5]} for w in WARDS]
        self.ward_by_id = {w["id"]: w for w in self.wards}
        self.depot = {"id": "DEPOT", "name": "Transfer station", "x": C.DEPOT_XY[0],
                      "y": C.DEPOT_XY[1]}
        self.bins = self._make_bins()
        self.bin_by_id = {b.id: b for b in self.bins}
        self.trucks = [{"id": "T%d" % (i + 1), "name": "Truck %d" % (i + 1),
                        "color": C.TRUCK_COLORS[i % len(C.TRUCK_COLORS)],
                        "capacity": C.TRUCK_CAPACITY_L,
                        "beat": [b.id for b in self.bins if b.ward in FIXED_BEATS[i]]}
                       for i in range(C.N_TRUCKS)]
        self._delta_cache = {}

    # ------------------------------------------------------------------ layout
    def _make_bins(self):
        bins = []
        for wi, (wid, _name, zone, (x0, y0, x1, y1), count, _hh) in enumerate(WARDS):
            r = _rng(11, wi)
            xs = [round(x0 + C.STREET_KM * k, 3) for k in range(1, int((x1 - x0) / C.STREET_KM))]
            ys = [round(y0 + C.STREET_KM * k, 3) for k in range(1, int((y1 - y0) / C.STREET_KM))]
            cands = [(x, y) for x in xs for y in ys]
            r.shuffle(cands)
            chosen = []
            for (x, y) in cands:
                if all(abs(x - a) + abs(y - b) >= 0.6 for a, b in chosen):
                    chosen.append((x, y))
                if len(chosen) == count:
                    break
            # route-chart order: north to south, west to east (how a ward register lists them)
            chosen.sort(key=lambda p: (-p[1], p[0]))
            for k, (x, y) in enumerate(chosen):
                bz = zone if (k % 3 != 2 or zone == "residential") else "residential"
                wt = r.random()
                tw = _TYPE_WEIGHTS[bz]
                wtype = "wet" if wt < tw[0] else ("dry" if wt < tw[0] + tw[1] else "recyclable")
                if bz in ("market", "commercial"):
                    cap = r.choice([660, 1100, 1100])
                else:
                    cap = r.choice([240, 660, 660, 1100])
                lo, hi = _BASE_RATE[bz]
                rate = lo + (hi - lo) * r.random()
                if cap == 240:
                    rate *= 1.15  # small street bins fill up faster relative to size
                bins.append((wid, bz, x, y, cap, wtype, rate))
        out = []
        for i, (wid, bz, x, y, cap, wtype, rate) in enumerate(bins):
            out.append(Bin(i, "B%02d" % (i + 1), wid, bz, x, y, cap, wtype, rate))
        return out

    # ------------------------------------------------------------------ fill model
    def delta(self, b, day):
        """True fraction of capacity deposited into bin b on simulated day `day` (may be < 0)."""
        key = (b.idx, day)
        v = self._delta_cache.get(key)
        if v is None:
            r = _rng(23, b.idx, day + 100000)
            noise = math.exp(r.gauss(0.0, 0.13))
            v = b.base_rate * b.profile[weekday_of(day)] * noise
            self._delta_cache[key] = v
        return v

    def observed_delta(self, b, day):
        """What the bin's ultrasonic sensor reports for that day's increment (true + noise)."""
        r = _rng(37, b.idx, day + 100000)
        return max(0.0, self.delta(b, day) + r.gauss(0.0, C.SENSOR_NOISE))

    def initial_level(self, b):
        """Sensor snapshot at 00:00 on day 0 (identical for every policy)."""
        r = _rng(41, b.idx)
        return round(0.10 + 0.60 * r.random(), 4)

    def history(self, b, days=None):
        """Observed daily increments for the HISTORY_DAYS before day 0 -> [(day, dow, value)]."""
        n = days or C.HISTORY_DAYS
        return [(d, weekday_of(d), self.observed_delta(b, d)) for d in range(-n, 0)]

    # ------------------------------------------------------------------ export
    def to_json(self):
        return {
            "wards": self.wards,
            "depot": self.depot,
            "bins": [b.to_json() for b in self.bins],
            "trucks": self.trucks,
            "bounds": {"w": C.TOWN_W_KM, "h": C.TOWN_H_KM, "street": C.STREET_KM},
            "start_date": C.START_DATE,
            "market_weekday": C.MARKET_WEEKDAY,
            "profiles": PROFILES,
        }


def deposit_fraction(clock_h):
    """Share of a day's waste already deposited by clock time `clock_h` (uniform 05:00-23:00)."""
    span = C.DEPOSIT_END_H - C.DEPOSIT_START_H
    return min(1.0, max(0.0, (clock_h - C.DEPOSIT_START_H) / span))
