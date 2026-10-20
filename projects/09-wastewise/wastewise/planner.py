"""Daily decisions: which bins to collect (forecast rules) and how to route the trucks."""

import math
import time

from . import config as C
from . import routing
from .forecast import hours_to_full
from .town import deposit_fraction, weekday_of


def decide(town, levels, forecasters, day):
    """One decision per bin with the rule that fired and a human-readable reason."""
    dow, dow1 = weekday_of(day), weekday_of(day + 1)
    F = deposit_fraction(C.PLAN_ARRIVAL_H)                        # typical arrival (rule A)
    F_late = deposit_fraction(C.SHIFT_START_H + C.SHIFT_MIN / 60.0)  # latest arrival (rule B)
    out = []
    for b in town.bins:
        f = forecasters[b.id]
        d0, d1, sig = f.forecast(dow), f.forecast(dow1), f.sigma
        L = levels[b.id]
        at_pickup = L + F * d0
        if_skipped = L + d0 + F_late * d1
        margin = C.SAFETY_SIGMA * sig * math.sqrt(1.0 + F_late * F_late)
        hi = if_skipped + margin
        horizon = [f.forecast(weekday_of(day + k)) for k in range(14)]
        ttf = hours_to_full(L, horizon, 0.0, (C.DEPOSIT_START_H, C.DEPOSIT_END_H))
        if at_pickup >= C.COLLECT_THRESHOLD:
            rule = "A"
            reason = "Will be %d%% full when the truck passes (rule A: >= %d%%)" % (
                round(100 * min(at_pickup, 1.5)), round(100 * C.COLLECT_THRESHOLD))
        elif hi >= C.OVERFLOW_LIMIT:
            rule = "B"
            reason = ("Only %d%% at pickup, but if skipped it reaches %d%% before tomorrow's run "
                      "(incl. +%d%% safety margin) - rule B overflow guard" % (
                          round(100 * at_pickup), round(100 * min(hi, 1.5)), round(100 * margin)))
        else:
            rule = None
            reason = "Skip: %d%% at pickup, %d%% by tomorrow's run even with +%d%% margin" % (
                round(100 * at_pickup), round(100 * hi), round(100 * margin))
        out.append({
            "bin": b.id, "ward": b.ward, "type": b.type, "capacity": b.capacity,
            "level": round(L, 4), "forecast_today": round(d0, 4), "forecast_tomorrow": round(d1, 4),
            "sigma": round(sig, 4), "at_pickup": round(at_pickup, 4),
            "if_skipped": round(if_skipped, 4), "if_skipped_hi": round(hi, 4),
            "urgency": round(hi, 4), "hours_to_full": ttf,
            "collect": rule is not None, "rule": rule, "reason": reason,
        })
    return out


def _points(town, ids):
    pts = [(town.depot["x"], town.depot["y"])]
    pts += [(town.bin_by_id[i].x, town.bin_by_id[i].y) for i in ids]
    return pts


def _trip_duration(route, dist):
    return routing.route_duration(route, dist, C.SPEED_KMPH, C.SERVICE_MIN_PER_BIN, C.UNLOAD_MIN)


def solve(town, ids, demand_l):
    """CW + 2-opt + truck assignment for the given bins. Returns a dict (no dropping)."""
    ids = list(ids)
    dist = routing.distance_matrix(_points(town, ids))
    demand = [0.0] + [demand_l[i] for i in ids]
    cap = C.TRUCK_CAPACITY_L * C.PLAN_CAPACITY_SHARE
    t0 = time.perf_counter()
    routes, trace = routing.clarke_wright(
        dist, demand, cap, max_duration=C.SHIFT_MIN, kmph=C.SPEED_KMPH,
        service_min=C.SERVICE_MIN_PER_BIN, unload_min=C.UNLOAD_MIN)
    t1 = time.perf_counter()
    cw_km = sum(routing.route_length(r, dist) for r in routes)
    improved, moves = [], 0
    for r in routes:
        nr, m = routing.two_opt(r, dist)
        improved.append(nr)
        moves += m
    t2 = time.perf_counter()
    opt_km = sum(routing.route_length(r, dist) for r in improved)
    durations = [_trip_duration(r, dist) for r in improved]
    per_truck, unassigned = routing.assign_trips(durations, C.N_TRUCKS, C.SHIFT_MIN)
    # naive ordering of the *same* bins (route-chart order) for the routing-only comparison
    order = sorted(range(1, len(ids) + 1), key=lambda k: town.bin_by_id[ids[k - 1]].idx)
    fixed_trips = routing.fixed_order(order, demand, cap)
    fixed_km = sum(routing.route_length(r, dist) for r in fixed_trips)
    return {
        "ids": ids, "dist": dist, "demand": demand, "routes": improved,
        "durations": durations, "per_truck": per_truck, "unassigned": unassigned,
        "trace": trace, "two_opt_moves": moves, "cw_km": cw_km, "opt_km": opt_km,
        "fixed_same_km": fixed_km, "fixed_same_trips": len(fixed_trips),
        "cw_ms": (t1 - t0) * 1000.0, "two_opt_ms": (t2 - t1) * 1000.0,
    }


def smart_plan(town, decisions):
    """Pick the bins the rules selected and build routes; if the fleet window is too short,
    defer the least urgent bin (lowest predicted level-if-skipped) one at a time."""
    by_id = {d["bin"]: d for d in decisions}
    chosen = [d["bin"] for d in decisions if d["collect"]]
    demand_l = {i: min(1.0, max(0.05, by_id[i]["at_pickup"])) * town.bin_by_id[i].capacity
                for i in chosen}
    deferred = []
    t0 = time.perf_counter()
    sol = solve(town, chosen, demand_l)
    while sol["unassigned"] and chosen:
        drop = min(chosen, key=lambda i: (by_id[i]["urgency"], i))
        chosen.remove(drop)
        deferred.append(drop)
        sol = solve(town, chosen, demand_l)
    total_ms = (time.perf_counter() - t0) * 1000.0
    ids = sol["ids"]
    trucks = []
    for t, trip_idx in enumerate(sol["per_truck"]):
        trips = []
        for k in trip_idx:
            r = sol["routes"][k]
            trips.append({"stops": [ids[c - 1] for c in r],
                          "km": round(routing.route_length(r, sol["dist"]), 3),
                          "minutes": round(sol["durations"][k], 1),
                          "planned_load_l": round(sum(sol["demand"][c] for c in r), 1)})
        trucks.append({"truck": town.trucks[t]["id"], "trips": trips})
    sequences = []
    for tr in trucks:
        seq = []
        for trip in tr["trips"]:
            seq.extend(trip["stops"])
            seq.append("U")
        sequences.append(seq)
    top = sorted(sol["trace"]["merges"], key=lambda m: -m["saving"])[:8]
    algo = {
        "bins": len(ids),
        "trips": len(sol["routes"]),
        "fixed_order_km": round(sol["fixed_same_km"], 2),
        "fixed_order_trips": sol["fixed_same_trips"],
        "clarke_wright_km": round(sol["cw_km"], 2),
        "two_opt_km": round(sol["opt_km"], 2),
        "two_opt_moves": sol["two_opt_moves"],
        "savings_considered": sol["trace"]["savings_considered"],
        "merges": len(sol["trace"]["merges"]),
        "rejected_capacity": sol["trace"]["rejected_capacity"],
        "rejected_duration": sol["trace"]["rejected_duration"],
        "top_savings": [{"a": ids[m["i"] - 1], "b": ids[m["j"] - 1],
                         "saving_km": round(m["saving"], 2)} for m in top],
        "cw_ms": round(sol["cw_ms"], 3),
        "two_opt_ms": round(sol["two_opt_ms"], 3),
        "total_ms": round(total_ms, 3),
        "deferred": deferred,
    }
    return {"trucks": trucks, "sequences": sequences, "algorithm": algo, "deferred": deferred}


def fixed_sequences(town, pointers):
    """Fixed-beat baseline: every truck resumes its ordered beat where it stopped yesterday."""
    seqs = []
    for t, truck in enumerate(town.trucks):
        beat = truck["beat"]
        p = pointers[t] % len(beat)
        seqs.append(beat[p:] + beat[:p])
    return seqs


def naive_all_bins(town):
    """Reference cost of literally visiting all bins in fixed order (no time limit)."""
    ids = [b.id for t in town.trucks for b in [town.bin_by_id[i] for i in t["beat"]]]
    km, minutes = 0.0, 0.0
    for t in town.trucks:
        beat = t["beat"]
        dist = routing.distance_matrix(_points(town, beat))
        demand = [0.0] + [0.6 * town.bin_by_id[i].capacity for i in beat]
        trips = routing.fixed_order(list(range(1, len(beat) + 1)), demand, C.TRUCK_CAPACITY_L)
        for r in trips:
            km += routing.route_length(r, dist)
            minutes += _trip_duration(r, dist)
    return {"bins": len(ids), "km": round(km, 2), "truck_hours": round(minutes / 60.0, 2)}
