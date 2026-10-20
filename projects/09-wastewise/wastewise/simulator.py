"""Day-by-day simulation of two worlds that see exactly the same waste:

* "fixed": the municipal baseline - each truck drives its fixed beat in fixed order, emptying
  every bin it reaches regardless of fill, until its shift ends (tomorrow it resumes there).
* "smart": WasteWise - forecast-driven bin selection + Clarke-Wright/2-opt routes.

Both fleets have the same trucks, capacity and shift window, so the comparison is fair.
"""

import copy

from . import config as C
from . import planner
from .forecast import fit_seasonal_es
from .routing import manhattan
from .town import Town, date_of, deposit_fraction, is_market_day, weekday_of
from .forecast import DOW

POLICIES = ("fixed", "smart")


def _xy(town, node):
    if node == "DEPOT":
        return (town.depot["x"], town.depot["y"])
    b = town.bin_by_id[node]
    return (b.x, b.y)


def execute(town, sequences, levels, day):
    """Drive every truck through its sequence ("U" = planned unload). Ground truth is used for
    the waste each bin holds when the truck arrives. Returns per-truck logs and per-bin visits."""
    trucks, visits, unvisited = [], {}, []
    min_per_km = 60.0 / C.SPEED_KMPH
    for t, seq in enumerate(sequences):
        pos, tmin, load, km = "DEPOT", 0.0, 0.0, 0.0
        ev = [{"node": "DEPOT", "arrive": 0.0, "depart": 0.0, "load": 0.0}]
        stops, unloads, service, done = 0, 0, 0.0, 0

        def go_unload():
            nonlocal pos, tmin, load, km, unloads
            if pos != "DEPOT":
                d = manhattan(_xy(town, pos), _xy(town, "DEPOT"))
                km += d
                tmin += d * min_per_km
                pos = "DEPOT"
            if load > 0:
                arrive = tmin
                tmin += C.UNLOAD_MIN
                unloads += 1
                ev.append({"node": "DEPOT", "arrive": round(arrive, 2), "depart": round(tmin, 2),
                           "load": 0.0, "unloaded": round(load, 1)})
                load = 0.0

        stopped = False
        for k, item in enumerate(seq):
            if item == "U":
                go_unload()
                continue
            b = town.bin_by_id[item]
            delta = town.delta(b, day)

            def visit_from(p, t0):
                d = manhattan(_xy(town, p), (b.x, b.y))
                arr = t0 + d * min_per_km
                lvl = levels[b.id] + deposit_fraction(C.SHIFT_START_H + arr / 60.0) * delta
                return d, arr, lvl, min(lvl, 1.0) * b.capacity

            d, arr, lvl, vol = visit_from(pos, tmin)
            if load + vol > C.TRUCK_CAPACITY_L:
                back = manhattan(_xy(town, pos), _xy(town, "DEPOT")) * min_per_km
                if tmin + back + C.UNLOAD_MIN > C.SHIFT_MIN:
                    stopped = True
                go_unload()
                d, arr, lvl, vol = visit_from("DEPOT", tmin)
            ret = manhattan((b.x, b.y), _xy(town, "DEPOT")) * min_per_km
            if stopped or arr + C.SERVICE_MIN_PER_BIN + ret + C.UNLOAD_MIN > C.SHIFT_MIN:
                unvisited.extend(x for x in seq[k:] if x != "U")
                break
            km += d
            tmin = arr + C.SERVICE_MIN_PER_BIN
            service += C.SERVICE_MIN_PER_BIN
            load += vol
            pos = b.id
            stops += 1
            done += 1
            visits[b.id] = {"truck": town.trucks[t]["id"], "arrive": round(arr, 2),
                            "level": round(lvl, 4), "volume_l": round(vol, 1)}
            ev.append({"node": b.id, "arrive": round(arr, 2), "depart": round(tmin, 2),
                       "load": round(load, 1), "level": round(lvl, 4)})
        go_unload()
        if ev[-1]["node"] != "DEPOT":
            ev.append({"node": "DEPOT", "arrive": round(tmin, 2), "depart": round(tmin, 2),
                       "load": 0.0})
        fuel = km / C.TRUCK_KM_PER_L + service / 60.0 * C.IDLE_L_PER_H
        trucks.append({"truck": town.trucks[t]["id"], "km": round(km, 3), "minutes": round(tmin, 1),
                       "stops": stops, "unloads": unloads, "fuel_l": round(fuel, 3),
                       "events": ev, "visited": done})
    return {"trucks": trucks, "visits": visits, "unvisited": unvisited}


def end_of_day(town, levels, visits, day):
    """Apply the day's waste to every bin; detect overflows. Returns (new_levels, overflows)."""
    new, overflows = {}, []
    for b in town.bins:
        L, delta = levels[b.id], town.delta(b, day)
        spill = 0.0
        when = None
        v = visits.get(b.id)
        if v is None:
            end = L + delta
            if end > 1.0:
                spill, when = end - 1.0, "not collected"
                end = 1.0
        else:
            F = deposit_fraction(C.SHIFT_START_H + v["arrive"] / 60.0)
            pre = L + F * delta
            if pre > 1.0:
                spill, when = pre - 1.0, "before the truck came"
            end = (1.0 - F) * delta
            if end > 1.0:
                spill += end - 1.0
                when = when or "after collection"
                end = 1.0
        new[b.id] = round(end, 6)
        if spill > 1e-9:
            overflows.append({"bin": b.id, "ward": b.ward, "litres": round(spill * b.capacity, 1),
                              "when": when})
    return new, overflows


def kpis(run, overflows):
    km = sum(t["km"] for t in run["trucks"])
    fuel = sum(t["fuel_l"] for t in run["trucks"])
    minutes = sum(t["minutes"] for t in run["trucks"] if t["stops"])
    fills = [v["level"] for v in run["visits"].values()]
    return {
        "km": round(km, 2),
        "fuel_l": round(fuel, 2),
        "co2_kg": round(fuel * C.CO2_KG_PER_L_DIESEL, 2),
        "cost_inr": round(fuel * C.DIESEL_INR_PER_L, 1),
        "truck_hours": round(minutes / 60.0, 2),
        "stops": len(fills),
        "collected_l": round(sum(v["volume_l"] for v in run["visits"].values()), 1),
        "avg_fill_at_pickup": round(sum(fills) / len(fills), 4) if fills else 0.0,
        "half_empty_pickups": sum(1 for f in fills if f < 0.5),
        "overflow_bins": len(overflows),
        "overflow_l": round(sum(o["litres"] for o in overflows), 1),
        "unvisited_planned": len(run["unvisited"]),
    }


class World:
    def __init__(self, town, name):
        self.name = name
        self.levels = {b.id: town.initial_level(b) for b in town.bins}
        self.pointers = [0] * C.N_TRUCKS
        self.daily = []

    def totals(self):
        keys = ("km", "fuel_l", "co2_kg", "cost_inr", "truck_hours", "stops", "collected_l",
                "half_empty_pickups", "overflow_bins", "overflow_l")
        t = {k: round(sum(d[k] for d in self.daily), 2) for k in keys}
        t["days"] = len(self.daily)
        pick = [d["avg_fill_at_pickup"] * d["stops"] for d in self.daily]
        t["avg_fill_at_pickup"] = round(sum(pick) / t["stops"], 4) if t["stops"] else 0.0
        return t


class Simulation:
    def __init__(self, town=None):
        self.town = town or Town()
        self.reset()

    def reset(self):
        town = self.town
        self.obs = {b.id: [(d, dow, v) for d, dow, v in town.history(b)] for b in town.bins}
        self.forecasters = {b.id: fit_seasonal_es([(dow, v) for _, dow, v in self.obs[b.id]])
                            for b in town.bins}
        self.day = 0
        self.worlds = {p: World(town, p) for p in POLICIES}
        self.events = []
        self._preview = None

    # ------------------------------------------------------------------ today
    def preview(self):
        """Plan + simulated outcome of the current day for both worlds (not committed)."""
        if self._preview is not None and self._preview["day"] == self.day:
            return self._preview
        town, day = self.town, self.day
        smart_w, fixed_w = self.worlds["smart"], self.worlds["fixed"]
        decisions = planner.decide(town, smart_w.levels, self.forecasters, day)
        plan = planner.smart_plan(town, decisions)
        deferred = set(plan["deferred"])
        for d in decisions:
            if d["bin"] in deferred:
                d["collect"] = False
                d["reason"] += " - deferred: fleet window full, least urgent"
        smart_run = execute(town, plan["sequences"], smart_w.levels, day)
        fixed_seq = planner.fixed_sequences(town, fixed_w.pointers)
        fixed_run = execute(town, fixed_seq, fixed_w.levels, day)
        s_levels, s_over = end_of_day(town, smart_w.levels, smart_run["visits"], day)
        f_levels, f_over = end_of_day(town, fixed_w.levels, fixed_run["visits"], day)
        self._preview = {
            "day": day, "decisions": decisions, "plan": plan,
            "runs": {"smart": smart_run, "fixed": fixed_run},
            "next_levels": {"smart": s_levels, "fixed": f_levels},
            "overflows": {"smart": s_over, "fixed": f_over},
            "kpis": {"smart": kpis(smart_run, s_over), "fixed": kpis(fixed_run, f_over)},
        }
        return self._preview

    def step(self):
        p = self.preview()
        town, day = self.town, self.day
        for pol in POLICIES:
            w = self.worlds[pol]
            w.levels = p["next_levels"][pol]
            k = dict(p["kpis"][pol])
            k["day"] = day
            k["market_day"] = is_market_day(day)
            w.daily.append(k)
        fixed_run = p["runs"]["fixed"]
        fw = self.worlds["fixed"]
        for t, tr in enumerate(fixed_run["trucks"]):
            fw.pointers[t] = (fw.pointers[t] + tr["visited"]) % len(town.trucks[t]["beat"])
        dow = weekday_of(day)
        for b in town.bins:
            v = town.observed_delta(b, day)
            self.obs[b.id].append((day, dow, v))
            self.forecasters[b.id].update(dow, v)
        summary = self.day_label(day)
        summary.update({"kpis": p["kpis"], "overflows": p["overflows"]})
        self.events.append(summary)
        self.day += 1
        self._preview = None
        return summary

    def run(self, days):
        return [self.step() for _ in range(days)]

    @staticmethod
    def day_label(day):
        d = date_of(day)
        return {"day": day, "date": d.isoformat(), "weekday": DOW[d.weekday()],
                "market_day": is_market_day(day), "label": "%s %s" % (DOW[d.weekday()],
                                                                     d.strftime("%d %b"))}

    def clone(self):
        return copy.deepcopy(self)


def simulate_month(days=None, town=None):
    """Fresh simulation from day 0 for `days` days; returns (sim, daily summaries)."""
    sim = Simulation(town)
    out = sim.run(days or C.MONTH_DAYS)
    return sim, out
