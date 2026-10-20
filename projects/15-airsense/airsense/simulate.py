"""Deterministic synthetic sensor network for a Tiruchengode/Namakkal-like town.

Physics-flavoured, not a dispersion model: regional background with diurnal mixing and
rain washout, plus plumes from a highway (line source), town traffic (area source), an
industrial cluster, a construction site, crop-residue burning and a festival fireworks
night. Low-cost sensors see the truth through gain/offset/temperature error, a kappa-Koehler
humidity growth bias and noise, and some develop injected faults (drift, stuck, spikes).

Everything is seeded (config.SEED) so the same files are produced on every machine.
"""

import csv
import datetime as dt
import json
import math
import os
import random

from . import config as C
from .mathx import angle_diff, bearing_deg, dist, point_polyline

POLL = ["pm25", "pm10", "no2", "so2", "co", "o3", "nh3"]

# Emission strength per source and pollutant (arbitrary units -> ug/m3 after dispersion;
# CO in mg/m3). ASSUMPTION: chosen so typical values look like a small Indian town
# (hourly PM2.5 ~20-120 ug/m3, festival night several hundred). Not measured anywhere.
EMIT = {
    "highway": {"pm25": 95, "pm10": 170, "no2": 200, "so2": 6, "co": 2.0},
    "town": {"pm25": 55, "pm10": 110, "no2": 130, "so2": 4, "co": 1.6},
    "industry": {"pm25": 420, "pm10": 600, "no2": 180, "so2": 800, "co": 1.2},
    "construction": {"pm25": 70, "pm10": 650},
    "burning": {"pm25": 1600, "pm10": 2000, "no2": 60, "co": 14.0, "nh3": 60},
    "fireworks": {"pm25": 230, "pm10": 290, "no2": 20, "so2": 65, "co": 0.5},
}


def hour_label(h):
    t = dt.datetime.strptime(C.START_DATE, "%Y-%m-%d") + dt.timedelta(hours=h)
    return t


# ----------------------------------------------------------------- dispersion kernels
def plume(sx, sy, x, y, wind_from, spread=0.28):
    """Unit Gaussian-like plume from a point source (before wind-speed dilution)."""
    d = max(dist(sx, sy, x, y), 0.05)
    to = (wind_from + 180.0) % 360.0
    a = math.radians(angle_diff(bearing_deg(sx, sy, x, y), to))
    xa = d * math.cos(a)
    near = 0.35 * math.exp(-d / 0.18)
    if xa <= 0:
        return near
    yc = d * math.sin(a)
    sy_ = 0.05 + spread * xa
    return near + math.exp(-yc * yc / (2 * sy_ * sy_)) / (1 + xa / 1.0) ** 1.2


def line_source(x, y, wind_from):
    d, fx, fy = point_polyline(x, y, C.HIGHWAY)
    to = (wind_from + 180.0) % 360.0
    if d < 1e-6:
        f = 1.0
    else:
        f = 0.35 + 0.65 * max(0.0, math.cos(math.radians(angle_diff(bearing_deg(fx, fy, x, y), to))))
    return f * math.exp(-d / 0.3)


def area_source(x, y, cx, cy, sigma):
    d = dist(x, y, cx, cy)
    return math.exp(-d * d / (2 * sigma * sigma))


# ----------------------------------------------------------------- time profiles
def highway_traffic(hod, sunday):
    v = (0.55 + 0.45 * math.exp(-(hod - 9) ** 2 / 4.0) + 0.55 * math.exp(-(hod - 19) ** 2 / 5.0))
    night = 0.75 if (hod >= 22 or hod <= 4) else (0.35 if hod in (21, 5) else 0.0)
    return (v + night) * (0.85 if sunday else 1.0)


def town_traffic(hod, sunday):
    v = (0.25 + 0.9 * math.exp(-(hod - 9.5) ** 2 / 3.0) + 0.35 * math.exp(-(hod - 13) ** 2 / 4.0)
         + 1.0 * math.exp(-(hod - 19) ** 2 / 4.0))
    return v * (0.7 if sunday else 1.0)


def rain_at(h, spells):
    r = 0.0
    for s, e, peak in spells:
        if s <= h <= e:
            mid = 0.5 * (s + e)
            half = max(1.0, 0.5 * (e - s))
            r += peak * max(0.15, 1 - abs(h - mid) / (half + 1))
    return r


# ----------------------------------------------------------------- main generator
class Generator:
    def __init__(self, seed=C.SEED):
        self.rng = random.Random(seed)
        self.h0 = -C.COLOC_DAYS * 24
        self.h1 = C.FIELD_DAYS * 24
        self.hours = list(range(self.h0, self.h1))
        # weather runs 24 h past the data: that last day is the "weather forecast" input
        self.wx_hours = list(range(self.h0, self.h1 + 24))

    def weather(self):
        rng = self.rng
        W = {}
        syn_t = syn_rh = syn_ws = 0.0
        dir_noise = 0.0
        wash = 0.0
        syn_pm = 0.0
        for h in self.wx_hours:
            hod = h % 24
            day = h / 24.0
            if hod == 0:
                syn_t = 0.7 * syn_t + rng.gauss(0, 0.6)
                syn_rh = 0.7 * syn_rh + rng.gauss(0, 3.0)
                syn_ws = 0.6 * syn_ws + rng.gauss(0, 0.25)
                syn_pm = 0.65 * syn_pm + rng.gauss(0, 0.17)
            rain = rain_at(h, C.RAIN_SPELLS + C.COLOC_RAIN)
            if rain > 0:
                rain *= 0.7 + 0.6 * rng.random()
            raining = rain > 0.2
            temp = 27.5 + 4.5 * math.cos(2 * math.pi * (hod - 14) / 24.0) + syn_t - (3.5 if raining else 0)
            rh = 72 - 14 * math.cos(2 * math.pi * (hod - 14) / 24.0) + syn_rh + rng.gauss(0, 1.2)
            if raining:
                rh = 95 + 3.5 * rng.random()
            elif wash > 0.3:
                rh += 8 * wash
            rh = max(38.0, min(99.0, rh))
            # wind: westerlies -> north-east monsoon easterlies (turning through north)
            if day < C.WIND_SHIFT_DAY - 1.5:
                prev = 250.0
            elif day > C.WIND_SHIFT_DAY + 1.5:
                prev = 65.0 + 360.0
            else:
                prev = 250.0 + (day - (C.WIND_SHIFT_DAY - 1.5)) / 3.0 * 175.0
            dir_noise = 0.9 * dir_noise + rng.gauss(0, 13.0)
            wdir = (prev + dir_noise + 18 * math.sin(2 * math.pi * (hod - 15) / 24.0)) % 360.0
            ws = 2.5 + 1.3 * math.sin(2 * math.pi * (hod - 9) / 24.0) + syn_ws + rng.gauss(0, 0.3)
            if raining:
                ws += 1.5
            fest = C.FESTIVAL_DAY * 24 + 16 <= h <= C.FESTIVAL_DAY * 24 + 32
            if fest:
                ws *= 0.45
            ws = max(0.3, min(7.5, ws))
            wash = min(1.0, wash * math.exp(-1 / 16.0) + 0.11 * rain)
            mix = 1.0 + 0.4 * math.cos(2 * math.pi * (hod - 3) / 24.0)
            W[h] = {"temp": temp, "rh": rh, "wdir": wdir, "ws": ws, "rain": rain,
                    "wash": wash, "mix": mix, "syn": math.exp(syn_pm)}
        return W

    def true_conc(self, x, y, h, w, cache_dt):
        """True concentrations of all 7 pollutants at (x, y) at hour h."""
        hod = h % 24
        day = h // 24
        t = cache_dt[h]
        sunday = t.weekday() == 6
        u = w["ws"]
        mix = w["mix"]
        wash = w["wash"]
        dil = mix / (u + 0.5)
        D = {}
        D["highway"] = highway_traffic(hod, sunday) * line_source(x, y, w["wdir"]) * dil
        D["town"] = town_traffic(hod, sunday) * area_source(x, y, C.TOWN_CENTRE[0], C.TOWN_CENTRE[1], 0.9) * dil
        ind_prof = (1.0 if 6 <= hod <= 22 else 0.7) * (0.75 if sunday else 1.0)
        D["industry"] = ind_prof * plume(C.INDUSTRY[0], C.INDUSTRY[1], x, y, w["wdir"]) * dil
        cons = 0.0
        if (day >= C.CONSTRUCTION_FROM_DAY and not sunday and 8 <= hod <= 17 and wash < 0.35):
            cons = (0.6 + 0.2 * u) * (0.6 * math.exp(-dist(x, y, *C.CONSTRUCTION) / 0.2)
                                      + plume(C.CONSTRUCTION[0], C.CONSTRUCTION[1], x, y, w["wdir"], 0.25))
            cons *= mix / (u + 0.4)
        D["construction"] = cons
        burn = 0.0
        if day in C.BURN_DAYS and 17 <= hod <= 23:
            inten = math.exp(-(hod - 20) ** 2 / 4.0)
            for bx, by in ((C.FIELDS[0] - 0.2, C.FIELDS[1] - 0.3), (C.FIELDS[0] + 0.2, C.FIELDS[1] + 0.4),
                           (C.FIELDS[0] - 0.3, C.FIELDS[1] + 0.6)):
                burn += inten / 3.0 * plume(bx, by, x, y, w["wdir"], 0.24)
            burn *= dil
        D["burning"] = burn
        fw = 0.0
        hf = h - C.FESTIVAL_DAY * 24
        if 18 <= hf <= 26:
            fw = math.exp(-(hf - 22) ** 2 / 5.0)
        elif 26 < hf <= 34:
            fw = math.exp(-(26 - 22) ** 2 / 5.0) * math.exp(-(hf - 26) / 3.0) + 0.0
        if fw:
            dens = 0.35 + 0.65 * area_source(x, y, C.TOWN_CENTRE[0], C.TOWN_CENTRE[1], 2.2)
            fw *= dens * 1.6 * mix / (u + 0.4)
        D["fireworks"] = fw

        bg = 28.0 * mix * w["syn"] * (1 - 0.68 * wash)
        out = {
            "pm25": bg,
            "pm10": bg * 1.7 + 14 * (1 - wash) * (0.7 + 0.3 * mix),
            "no2": 9.0 * mix + 2.0,
            "so2": 5.0 + 1.5 * mix,
            "co": 0.32 * mix,
            "o3": 0.0,
            "nh3": 16.0 + 10 * area_source(x, y, C.FIELDS[0], C.FIELDS[1], 2.5),
        }
        for src, dval in D.items():
            if dval:
                for p, e in EMIT[src].items():
                    out[p] += e * dval
        sun = max(0.0, math.sin(math.pi * (hod - 7) / 12.0)) ** 1.3 if 7 <= hod <= 19 else 0.0
        cloud = 0.5 if w["rain"] > 0.2 else 1.0
        out["o3"] = max(4.0, 14 + 78 * sun * cloud * (1 - 0.35 * wash) - 0.25 * (out["no2"] - 20))
        return out, D

    def generate(self):
        rng = self.rng
        W = self.weather()
        dts = {h: hour_label(h) for h in self.wx_hours}
        locs = {s["id"]: (s["x"], s["y"]) for s in C.REFERENCE_STATIONS}
        sensors = [{"id": sid, "name": name, "x": x, "y": y, "coloc": col}
                   for sid, name, x, y, col in C.SENSORS]
        # per-sensor hardware personality
        for s in sensors:
            s["gain"] = round(rng.uniform(0.8, 1.45), 3)
            s["offset"] = round(rng.uniform(-2.5, 5.0), 2)
            s["kappa"] = round(rng.uniform(0.12, 0.30), 3)
            s["temp_coef"] = round(rng.uniform(-0.35, 0.35), 3)
            s["gain10"] = round(s["gain"] * rng.uniform(0.85, 1.1), 3)
            s["rh_bias"] = round(rng.uniform(-3, 3), 2)
        # reference stations: all hours
        ref_rows = []
        ref_true = {}
        for st in C.REFERENCE_STATIONS:
            for h in self.hours:
                c, _ = self.true_conc(st["x"], st["y"], h, W[h], dts)
                ref_true[(st["id"], h)] = c
                vals = {}
                for p in POLL:
                    v = c[p] * (1 + rng.gauss(0, 0.03)) + rng.gauss(0, 0.02 if p == "co" else 0.5)
                    vals[p] = round(max(0.0, v), 2 if p == "co" else 1)
                if h >= 0 and rng.random() < 0.002:
                    vals = {p: None for p in POLL}
                ref_rows.append([h, st["id"]] + [vals[p] for p in POLL])

        def sensor_reading(s, true25, true10, w):
            rh_s = max(20.0, min(99.0, w["rh"] + s["rh_bias"] + rng.gauss(0, 1.0)))
            t_s = w["temp"] + 1.2 + rng.gauss(0, 0.35)
            aw = min(w["rh"], 95.0) / 100.0
            grow = 1 + (s["kappa"] / 1.65) * aw / (1 - aw)
            grow10 = 1 + (0.8 * s["kappa"] / 1.65) * aw / (1 - aw)
            raw25 = (s["gain"] * true25 * grow + s["offset"] + s["temp_coef"] * (w["temp"] - 27)
                     + rng.gauss(0, 0.8 + 0.05 * true25))
            seen10 = true25 + 0.5 * (true10 - true25)   # optical sensors undercount coarse dust
            raw10 = (s["gain10"] * seen10 * grow10 + 1.3 * s["offset"]
                     + rng.gauss(0, 1.2 + 0.06 * seen10))
            raw25 = max(0.0, raw25)
            raw10 = max(raw25, raw10)
            return raw25, raw10, t_s, rh_s

        # co-location week
        coloc_rows = []
        for s in sensors:
            for h in range(self.h0, 0):
                c = ref_true[(s["coloc"], h)]
                r25, r10, t_s, rh_s = sensor_reading(s, c["pm25"], c["pm10"], W[h])
                coloc_rows.append([h, s["id"], s["coloc"], round(r25, 1), round(r10, 1),
                                   round(t_s, 1), round(rh_s, 1)])
        # field deployment
        field = {}
        truth_rows = []
        for s in sensors:
            for h in range(0, self.h1):
                c, _ = self.true_conc(s["x"], s["y"], h, W[h], dts)
                r25, r10, t_s, rh_s = sensor_reading(s, c["pm25"], c["pm10"], W[h])
                field[(s["id"], h)] = [r25, r10, t_s, rh_s]
                truth_rows.append([h, s["id"], round(c["pm25"], 2), round(c["pm10"], 2)])

        # ------------------------------------------------ inject faults (ground truth)
        faults = []
        for f in C.FAULTS:
            f = dict(f)
            if f["type"] == "drift":
                start = f["start_day"] * 24
                for h in range(start, self.h1):
                    days = (h - start) / 24.0
                    v = field[(f["sensor"], h)]
                    if f["kind"] == "gain":
                        m = max(0.2, 1 + f["rate"] * days)
                        v[0] *= m
                        v[1] *= m
                    else:
                        v[0] += f["rate"] * days
                        v[1] += 1.3 * f["rate"] * days
                f["start_hour"] = start
                f["end_hour"] = self.h1 - 1
            elif f["type"] == "stuck":
                start = f["start_hour"]
                frozen = list(field[(f["sensor"], start - 1)])
                frozen[0] = round(frozen[0], 1)
                frozen[1] = round(frozen[1], 1)
                for h in range(start, start + f["hours"]):
                    field[(f["sensor"], h)] = list(frozen)
                f["end_hour"] = start + f["hours"] - 1
            faults.append(f)
        busy = set()
        for f in faults:
            if f["type"] == "stuck":
                for h in range(f["start_hour"] - 2, f["end_hour"] + 3):
                    busy.add((f["sensor"], h))
        fest = set(range(C.FESTIVAL_DAY * 24 + 16, C.FESTIVAL_DAY * 24 + 36))
        spikes = []
        while len(spikes) < C.N_SPIKES:
            s = sensors[rng.randrange(len(sensors))]["id"]
            h = rng.randrange(30, self.h1 - 2)
            if (s, h) in busy or h in fest or any(abs(h - x["start_hour"]) < 3 and s == x["sensor"]
                                                   for x in spikes):
                continue
            v = field[(s, h)]
            mult = rng.uniform(3.0, 6.0)
            v[0] = v[0] * mult + rng.uniform(40, 120)
            v[1] = max(v[1] * mult * 0.9 + rng.uniform(40, 120), v[0])
            spikes.append({"sensor": s, "type": "spike", "start_hour": h, "end_hour": h})
            busy.add((s, h))
        faults.extend(sorted(spikes, key=lambda f: (f["sensor"], f["start_hour"])))

        missing = set()
        for sid, start, n in C.OUTAGES:
            for h in range(start, start + n):
                missing.add((sid, h))
        for s in sensors:
            for h in range(self.h1):
                if (s["id"], h) not in busy and rng.random() < C.MISSING_RATE:
                    missing.add((s["id"], h))
        field_rows = []
        for s in sensors:
            for h in range(self.h1):
                if (s["id"], h) in missing:
                    field_rows.append([h, s["id"], None, None, None, None])
                    continue
                r25, r10, t_s, rh_s = field[(s["id"], h)]
                field_rows.append([h, s["id"], round(r25, 1), round(r10, 1), round(t_s, 1), round(rh_s, 1)])

        weather_rows = [[h, round(W[h]["temp"], 1), round(W[h]["rh"], 1), round(W[h]["wdir"]),
                         round(W[h]["ws"], 2), round(W[h]["rain"], 1),
                         "forecast" if h >= self.h1 else "observed"] for h in self.wx_hours]
        events = scenario_events()
        meta = {
            "seed": C.SEED, "start": C.START_DATE, "field_hours": self.h1,
            "coloc_hours": -self.h0, "sensors": sensors,
            "references": C.REFERENCE_STATIONS, "faults": faults, "events": events,
            "missing": len(missing),
            "note": "Synthetic data. Sensor hardware parameters and faults are ground truth "
                    "used only for evaluation; models never read them.",
        }
        return {"field": field_rows, "coloc": coloc_rows, "reference": ref_rows,
                "weather": weather_rows, "truth": truth_rows, "meta": meta}


def scenario_events():
    ev = []
    for d in C.BURN_DAYS:
        ev.append({"id": "burn%d" % d, "name": "Crop-residue burning", "start_hour": d * 24 + 17,
                   "end_hour": d * 24 + 23, "kind": "burning"})
    ev.append({"id": "festival", "name": "Festival fireworks night",
               "start_hour": C.FESTIVAL_DAY * 24 + 18, "end_hour": C.FESTIVAL_DAY * 24 + 27,
               "kind": "fireworks"})
    for i, (s, e, _) in enumerate(C.RAIN_SPELLS):
        if e - s >= 6:
            ev.append({"id": "rain%d" % i, "name": "Monsoon rain washout", "start_hour": s,
                       "end_hour": e, "kind": "rain"})
    ev.append({"id": "construction", "name": "Flyover construction starts",
               "start_hour": C.CONSTRUCTION_FROM_DAY * 24 + 8,
               "end_hour": C.CONSTRUCTION_FROM_DAY * 24 + 17, "kind": "construction"})
    return sorted(ev, key=lambda e: e["start_hour"])


FILES = {
    "field": ("field.csv", ["hour", "sensor", "raw_pm25", "raw_pm10", "temp_c", "rh_pct"]),
    "coloc": ("colocation.csv", ["hour", "sensor", "station", "raw_pm25", "raw_pm10", "temp_c", "rh_pct"]),
    "reference": ("reference.csv", ["hour", "station"] + POLL),
    "weather": ("weather.csv", ["hour", "temp_c", "rh_pct", "wind_from_deg", "wind_ms", "rain_mm", "kind"]),
    "truth": ("ground_truth.csv", ["hour", "sensor", "true_pm25", "true_pm10"]),
}


def write(data_dir, seed=C.SEED):
    os.makedirs(data_dir, exist_ok=True)
    data = Generator(seed).generate()
    for key, (fname, header) in FILES.items():
        with open(os.path.join(data_dir, fname), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for row in data[key]:
                w.writerow(["" if v is None else v for v in row])
    with open(os.path.join(data_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(data["meta"], f, indent=1)
    return data


def _num(v):
    return None if v == "" else float(v)


def read(data_dir):
    out = {}
    for key, (fname, header) in FILES.items():
        rows = []
        with open(os.path.join(data_dir, fname), newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            next(r)
            for row in r:
                rows.append(row)
        out[key] = rows
    with open(os.path.join(data_dir, "meta.json"), encoding="utf-8") as f:
        out["meta"] = json.load(f)
    return out


def files_present(data_dir):
    return all(os.path.isfile(os.path.join(data_dir, f)) for f, _ in FILES.values()) and \
        os.path.isfile(os.path.join(data_dir, "meta.json"))


if __name__ == "__main__":  # pragma: no cover
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    write(os.path.join(here, "data"))
    print("wrote data/ (seed %d)" % C.SEED)
