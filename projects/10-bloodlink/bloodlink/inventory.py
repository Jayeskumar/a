"""Blood bank inventory network: FEFO issue, moving-average demand forecast, expiry-risk
projection, greedy inter-bank transfer suggestions and a month-long network simulation.

Time is measured in integer days relative to the snapshot day (day 0 = config.DEMO_TODAY).
A unit is usable on day d while d < unit["expires"]; on day == expires it is discarded.
"""
import math
import random

from . import compat
from .config import (BANKS, BLOOD_GROUPS, GROUP_SHARE, LOW_COVER_DAYS, MA_WINDOW_DAYS,
                     MAX_TRANSFER_KM, NETWORK_HISTORY_DAYS, NETWORK_WARMUP_DAYS, SAGM_SHARE,
                     SHELF_LIFE_DAYS, TARGET_COVER_DAYS, TRANSIT_DAYS)
from .geo import haversine_km

KEEP_COVER_DAYS = 7.0   # a sender keeps at least a week of its own forecast demand
EXCESS_STATUS_DAYS = 14.0


# ------------------------------------------------------------------------------------------
# FEFO issue
# ------------------------------------------------------------------------------------------
def fefo_issue(stock, group, units, today, allow_substitutes=True):
    """Issue `units` red-cell units for a `group` patient from `stock` (list, mutated).

    Exact group first, then compatible substitutes in preference order; within each tier
    the unit that expires first goes out first (First-Expiry-First-Out). Expired units are
    never issued. Returns (issued_units, unmet_count).
    """
    group = compat.normalize(group)
    tiers = compat.red_cell_donors_for(group) if allow_substitutes else [group]
    issued = []
    for g in tiers:
        if len(issued) >= units:
            break
        pool = sorted((u for u in stock if u["group"] == g and u["expires"] > today),
                      key=lambda u: (u["expires"], u["id"]))
        for u in pool[:units - len(issued)]:
            issued.append(u)
    ids = {u["id"] for u in issued}
    stock[:] = [u for u in stock if u["id"] not in ids]
    return issued, units - len(issued)


def remove_expired(stock, today):
    """Drop units whose expiry day has arrived; return them."""
    gone = [u for u in stock if u["expires"] <= today]
    if gone:
        stock[:] = [u for u in stock if u["expires"] > today]
    return gone


# ------------------------------------------------------------------------------------------
# Forecasting and expiry-risk projection
# ------------------------------------------------------------------------------------------
def moving_average(series, window=MA_WINDOW_DAYS):
    """Mean of the last `window` values (fewer if the series is short); 0 for empty."""
    tail = list(series)[-window:]
    return sum(tail) / len(tail) if tail else 0.0


SPARSE_MIN_EVENTS = 3      # fewer units than this in the MA window -> demand is "sparse"
SPARSE_WINDOW_DAYS = 28


def forecast_rate(series, window=MA_WINDOW_DAYS):
    """Units/day forecast: the moving average, falling back to a 28-day average when the
    short window holds too few events (rare groups) to be meaningful."""
    tail = list(series)[-window:]
    if sum(tail) >= SPARSE_MIN_EVENTS:
        return moving_average(series, window)
    return moving_average(series, SPARSE_WINDOW_DAYS)


def backtest_moving_average(series, window=MA_WINDOW_DAYS, horizon=1):
    """One-step-ahead MAE of the moving average vs the naive 'same as yesterday' forecast."""
    errs_ma, errs_naive = [], []
    for t in range(window, len(series) - horizon + 1):
        actual = sum(series[t:t + horizon])
        errs_ma.append(abs(moving_average(series[:t], window) * horizon - actual))
        errs_naive.append(abs(series[t - 1] * horizon - actual))
    if not errs_ma:
        return None
    return {"mae_ma": sum(errs_ma) / len(errs_ma), "mae_naive": sum(errs_naive) / len(errs_naive),
            "n": len(errs_ma)}


def at_risk_flags(days_left, rate):
    """Given units' days-left in FEFO order and a demand rate (units/day), flag the units
    projected to expire before demand reaches them.

    Walk the queue with a clock t: the next usable unit is consumed at t + 1/rate. If
    that is later than its days-left it will expire (and does not consume demand time).
    """
    if rate <= 1e-9:
        return [True] * len(days_left)
    t, step, flags = 0.0, 1.0 / rate, []
    for left in days_left:
        if t + step > left:
            flags.append(True)
        else:
            t += step
            flags.append(False)
    return flags


def group_status(units, rate, today):
    """Stock, forecast and status for one bank x group."""
    usable = sorted((u for u in units if u["expires"] > today), key=lambda u: (u["expires"], u["id"]))
    left = [u["expires"] - today for u in usable]
    flags = at_risk_flags(left, rate)
    at_risk = sum(flags)
    good = len(usable) - at_risk
    cover = good / rate if rate > 1e-9 else (float("inf") if good else 0.0)
    target = math.ceil(rate * TARGET_COVER_DAYS)
    if rate <= 1e-9:
        status = "idle" if usable else "none"   # no demand seen in 28 days
    elif cover < LOW_COVER_DAYS:
        status = "short"
    elif cover < TARGET_COVER_DAYS:
        status = "low"
    elif at_risk:
        status = "expiry-risk"
    elif cover > EXCESS_STATUS_DAYS:
        status = "excess"
    else:
        status = "ok"
    return {
        "units": len(usable),
        "at_risk": at_risk,
        "expiring_3d": sum(1 for x in left if x <= 3),
        "earliest_days_left": left[0] if left else None,
        "rate": round(rate, 2),
        "days_cover": None if (cover == float("inf") or rate <= 1e-9) else round(cover, 1),
        "target": target,
        "deficit": max(0, target - good),
        "status": status,
    }


# ------------------------------------------------------------------------------------------
# Transfer suggestions (greedy, most-urgent unit first, nearest feasible receiver)
# ------------------------------------------------------------------------------------------
def bank_distances(banks):
    return {(a["id"], b["id"]): haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            for a in banks for b in banks}


def suggest_transfers(stock_by_bank, rates, today, banks=BANKS, dist=None,
                      max_km=MAX_TRANSFER_KM, transit_days=TRANSIT_DAYS):
    """Suggest inter-bank moves that prevent expiry wastage and fill shortages.

    For every group:
      1. Project FEFO consumption at each bank (moving-average rate) -> units at risk of
         expiring unused, and each bank's deficit vs a TARGET_COVER_DAYS stock target.
      2. Transferable units: every at-risk unit, plus "excess" units beyond a week of the
         sender's own demand (excess only goes to banks with a deficit).
      3. Greedy: take transferable units in order of days-left (most urgent first) and
         send each to the nearest bank that (a) is within max_km, (b) has a deficit -- or,
         for an at-risk unit, at least spare demand -- and (c) would use the unit before
         it expires after transit without pushing any of its own units into expiry.
    Units already transferred once are not moved again (cold-chain hygiene).
    Returns a list of grouped suggestions with plain-language reasons.
    """
    dist = dist or bank_distances(banks)
    names = {b["id"]: b["name"].replace(" (demo)", "") for b in banks}
    moves = []
    for g in BLOOD_GROUPS:
        queues, units_q, flags, deficit, rate = {}, {}, {}, {}, {}
        for b in banks:
            bid = b["id"]
            rate[bid] = rates.get(bid, {}).get(g, 0.0)
            q = sorted((u for u in stock_by_bank.get(bid, []) if u["group"] == g and u["expires"] > today),
                       key=lambda u: (u["expires"], u["id"]))
            queues[bid] = [u["expires"] - today for u in q]
            flags[bid] = at_risk_flags(queues[bid], rate[bid])
            good = len(q) - sum(flags[bid])
            deficit[bid] = max(0, math.ceil(rate[bid] * TARGET_COVER_DAYS) - good)
            units_q[bid] = q
        cands = []
        for b in banks:
            bid = b["id"]
            q, f = units_q[bid], flags[bid]
            keep = math.ceil(rate[bid] * KEEP_COVER_DAYS)
            good_units = [u for u, r in zip(q, f) if not r]
            for u, r in zip(q, f):
                if r and not u.get("moved"):
                    cands.append((u["expires"] - today, 0, bid, u))
            excess = good_units[:max(0, len(good_units) - keep)]
            for u in excess:
                if not u.get("moved"):
                    cands.append((u["expires"] - today, 1, bid, u))
        cands.sort(key=lambda c: (c[1], c[0], c[3]["id"]))
        for left, kind, src, u in cands:
            arrive_left = left - transit_days
            if arrive_left <= 0:
                continue
            best = None
            for b in banks:
                rid = b["id"]
                if rid == src or dist[(src, rid)] > max_km or rate[rid] <= 1e-9:
                    continue
                if kind == 1 and deficit[rid] <= 0:
                    continue
                if kind == 1 and deficit[src] > 0:
                    continue
                # receiver's queue as seen on arrival day
                rq = [x - transit_days for x in queues[rid] if x - transit_days > 0]
                before = sum(at_risk_flags(rq, rate[rid]))
                rq2 = sorted(rq + [arrive_left])
                after = sum(at_risk_flags(rq2, rate[rid]))
                if after > before:
                    continue  # receiver could not use it in time / would waste its own
                key = (0 if deficit[rid] > 0 else 1, dist[(src, rid)])
                if best is None or key < best[0]:
                    best = (key, rid)
            if best is None:
                continue
            rid = best[1]
            moves.append({"unit": u, "from": src, "to": rid, "group": g, "kind": kind,
                          "days_left": left, "km": dist[(src, rid)],
                          "receiver_deficit": deficit[rid], "receiver_rate": rate[rid],
                          "sender_rate": rate[src]})
            queues[rid] = sorted(queues[rid] + [left])
            deficit[rid] = max(0, deficit[rid] - 1)
            # remove from sender queue so later checks see the right picture
            queues[src].remove(left)
    return _group_moves(moves, names)


def _group_moves(moves, names):
    groups = {}
    for m in moves:
        k = (m["from"], m["to"], m["group"])
        g = groups.setdefault(k, {"from": m["from"], "to": m["to"], "group": m["group"],
                                  "from_name": names[m["from"]], "to_name": names[m["to"]],
                                  "km": round(m["km"], 1), "unit_ids": [], "at_risk_units": 0,
                                  "excess_units": 0, "min_days_left": m["days_left"],
                                  "receiver_deficit": m["receiver_deficit"],
                                  "receiver_rate": m["receiver_rate"], "sender_rate": m["sender_rate"]})
        g["unit_ids"].append(m["unit"]["id"])
        if m["kind"] == 0:
            g["at_risk_units"] += 1
        else:
            g["excess_units"] += 1
        g["min_days_left"] = min(g["min_days_left"], m["days_left"])
        g["receiver_deficit"] = max(g["receiver_deficit"], m["receiver_deficit"])
    out = []
    for g in groups.values():
        g["units"] = len(g["unit_ids"])
        why = []
        if g["at_risk_units"]:
            why.append("%d %s unit%s would expire unused at %s (demand ~%.1f/day; first expires in %d d)" % (
                g["at_risk_units"], g["group"], "" if g["at_risk_units"] == 1 else "s", g["from_name"],
                g["sender_rate"], g["min_days_left"]))
        if g["excess_units"]:
            why.append("%d surplus unit%s beyond a week of %s's own demand" % (
                g["excess_units"], "" if g["excess_units"] == 1 else "s", g["from_name"]))
        if g["receiver_deficit"] > 0:
            why.append("%s is %d unit%s below its %g-day target (uses ~%.1f/day)" % (
                g["to_name"], g["receiver_deficit"], "" if g["receiver_deficit"] == 1 else "s",
                TARGET_COVER_DAYS, g["receiver_rate"]))
        else:
            why.append("%s uses ~%.1f/day and will use them before expiry" % (g["to_name"], g["receiver_rate"]))
        g["reason"] = "; ".join(why) + " (%.0f km)" % g["km"]
        g["priority"] = "high" if (g["receiver_deficit"] > 0 or g["min_days_left"] <= 5) else "normal"
        out.append(g)
    out.sort(key=lambda g: (g["priority"] != "high", g["min_days_left"], -g["units"]))
    return out


# ------------------------------------------------------------------------------------------
# Network simulation
# ------------------------------------------------------------------------------------------
def _poisson(rng, lam):
    """Knuth's method (fine for the small daily rates used here)."""
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _pick_group(rng):
    r, acc = rng.random(), 0.0
    for g in BLOOD_GROUPS:
        acc += GROUP_SHARE[g]
        if r < acc:
            return g
    return BLOOD_GROUPS[-1]


def generate_events(seed, days, banks=BANKS, start_day=0):
    """Pre-draw daily demand and collections so every policy faces the same month."""
    rng = random.Random(seed)
    out = []
    for i in range(days):
        day = start_day + i
        per_bank = {}
        for b in banks:
            demand = {g: _poisson(rng, b["demand_per_day"] * GROUP_SHARE[g]) for g in BLOOD_GROUPS}
            collected = {g: _poisson(rng, b["demand_per_day"] * b["collect_ratio"] * GROUP_SHARE[g])
                         for g in BLOOD_GROUPS}
            every = b["camp_every_days"]
            phase = (sum(ord(c) for c in b["id"]) + seed) % every if every else 0
            if every and (day + phase) % every == 0:
                lo, hi = b["camp_size"]
                for _ in range(rng.randint(lo, hi)):
                    g = _pick_group(rng)
                    collected[g] += 1
            additive = [rng.random() < SAGM_SHARE for _ in range(sum(collected.values()))]
            per_bank[b["id"]] = {"demand": demand, "collected": collected, "sagm": additive}
        out.append({"day": day, "banks": per_bank})
    return out


class Network:
    """Mutable state of the 5-bank network."""

    def __init__(self, banks=BANKS):
        self.banks = banks
        self.stock = {b["id"]: [] for b in banks}
        self.history = {b["id"]: {g: [] for g in BLOOD_GROUPS} for b in banks}
        self.in_transit = []   # (arrival_day, bank_id, unit)
        self.dist = bank_distances(banks)
        self.counter = 0

    # -- helpers ---------------------------------------------------------------------
    def _new_unit(self, bank_id, group, day, sagm):
        self.counter += 1
        additive = "SAGM" if sagm else "CPDA-1"
        return {"id": "%s-%05d" % (bank_id, self.counter), "group": group, "collected": day,
                "expires": day + SHELF_LIFE_DAYS[additive], "additive": additive, "bank": bank_id}

    def rates(self, window=MA_WINDOW_DAYS):
        return {bid: {g: forecast_rate(h, window) for g, h in groups.items()}
                for bid, groups in self.history.items()}

    def to_json(self):
        return {"stock": self.stock, "history": self.history, "counter": self.counter,
                "in_transit": self.in_transit}

    @classmethod
    def from_json(cls, data, banks=BANKS):
        n = cls(banks)
        n.stock = {k: [dict(u) for u in v] for k, v in data["stock"].items()}
        n.history = {k: {g: list(s) for g, s in v.items()} for k, v in data["history"].items()}
        n.counter = data.get("counter", 0)
        n.in_transit = [tuple(x) for x in data.get("in_transit", [])]
        return n

    def clone(self):
        return Network.from_json(self.to_json(), self.banks)

    # -- one simulated day ---------------------------------------------------------------
    def step(self, ev, transfers=False):
        day = ev["day"]
        m = {"expired": 0, "unmet": 0, "issued": 0, "substituted": 0, "demand": 0,
             "moved": 0, "trip_km": 0.0, "shipments": 0, "expired_by_bank": {}}
        for bid, st in self.stock.items():
            gone = remove_expired(st, day)
            m["expired"] += len(gone)
            m["expired_by_bank"][bid] = len(gone)
        arriving = [x for x in self.in_transit if x[0] <= day]
        self.in_transit = [x for x in self.in_transit if x[0] > day]
        for _, bid, u in arriving:
            if u["expires"] > day:
                self.stock[bid].append(u)
            else:
                m["expired"] += 1
        for bid, e in ev["banks"].items():
            flags = iter(e["sagm"])
            for g in BLOOD_GROUPS:
                for _ in range(e["collected"][g]):
                    self.stock[bid].append(self._new_unit(bid, g, day, next(flags, False)))
        for bid, e in ev["banks"].items():
            st = self.stock[bid]
            pending = {}
            for g in BLOOD_GROUPS:           # pass 1: exact group only
                need = e["demand"][g]
                m["demand"] += need
                self.history[bid][g].append(need)
                got, short = fefo_issue(st, g, need, day, allow_substitutes=False)
                m["issued"] += len(got)
                if short:
                    pending[g] = short
            for g in BLOOD_GROUPS:           # pass 2: compatible substitutes
                if g in pending:
                    got, short = fefo_issue(st, g, pending[g], day, allow_substitutes=True)
                    m["issued"] += len(got)
                    m["substituted"] += len(got)
                    m["unmet"] += short
        for bid in self.history:
            for g in BLOOD_GROUPS:
                h = self.history[bid][g]
                if len(h) > 60:
                    del h[:-60]
        if transfers:
            sugg = suggest_transfers(self.stock, self.rates(), day, self.banks, self.dist)
            self.apply(sugg, day, m)
        return m

    def apply(self, suggestions, day, m=None):
        moved, routes = 0, set()
        for s in suggestions:
            src = self.stock[s["from"]]
            ids = set(s["unit_ids"])
            units = [u for u in src if u["id"] in ids]
            src[:] = [u for u in src if u["id"] not in ids]
            for u in units:
                u = dict(u, moved=True, bank=s["to"])
                self.in_transit.append((day + TRANSIT_DAYS, s["to"], u))
            moved += len(units)
            if m is not None and units:
                m["moved"] += len(units)
                if (s["from"], s["to"]) not in routes:   # one cold-box trip per route per day
                    routes.add((s["from"], s["to"]))
                    m["shipments"] += 1
                    m["trip_km"] += s["km"]
        return moved


def build_snapshot(seed, warmup_days=NETWORK_WARMUP_DAYS):
    """Simulate `warmup_days` without transfers so stock ages look realistic; the state
    at the end is the dashboard's day 0."""
    net = Network()
    rng = random.Random(seed + 7)
    start = -warmup_days
    for b in BANKS:  # small opening stock, ~3 days of demand with mixed ages
        for _ in range(int(b["demand_per_day"] * 3)):
            g = _pick_group(rng)
            age = rng.randint(0, 20)
            net.stock[b["id"]].append(net._new_unit(b["id"], g, start - age, rng.random() < SAGM_SHARE))
    for ev in generate_events(seed, warmup_days, start_day=start):
        net.step(ev, transfers=False)
    for bid in net.history:
        for g in BLOOD_GROUPS:
            net.history[bid][g] = net.history[bid][g][-NETWORK_HISTORY_DAYS:]
        remove_expired(net.stock[bid], 0)   # units whose last usable day was yesterday
    return net


def simulate_month(base, seed, days=30, transfers=False):
    """Run `days` from a copy of `base` network; returns totals and a daily series."""
    net = base.clone()
    totals = {"expired": 0, "unmet": 0, "issued": 0, "substituted": 0, "demand": 0,
              "moved": 0, "trip_km": 0.0, "shipments": 0}
    daily = []
    for ev in generate_events(seed, days, start_day=0):
        m = net.step(ev, transfers=transfers)
        for k in totals:
            totals[k] += m[k]
        daily.append({"day": ev["day"], "expired": m["expired"], "unmet": m["unmet"], "moved": m["moved"]})
    totals["trip_km"] = round(totals["trip_km"], 1)
    return {"totals": totals, "daily": daily}


def compare_month(base, seeds, days=30):
    """With vs without transfers over several random months (same events per seed)."""
    rows = []
    for s in seeds:
        a = simulate_month(base, s, days, transfers=False)
        b = simulate_month(base, s, days, transfers=True)
        rows.append({"seed": s, "without": a["totals"], "with": b["totals"],
                     "daily_without": a["daily"], "daily_with": b["daily"]})

    def agg(key, k):
        vals = [r[key][k] for r in rows]
        return {"mean": round(sum(vals) / len(vals), 1), "min": min(vals), "max": max(vals)}
    keys = ["expired", "unmet", "issued", "demand", "moved", "shipments", "trip_km", "substituted"]
    summary = {"without": {k: agg("without", k) for k in keys}, "with": {k: agg("with", k) for k in keys},
               "seeds": len(rows), "days": days}
    w0, w1 = summary["without"]["expired"]["mean"], summary["with"]["expired"]["mean"]
    u0, u1 = summary["without"]["unmet"]["mean"], summary["with"]["unmet"]["mean"]
    summary["expired_reduction_pct"] = round(100.0 * (w0 - w1) / w0, 1) if w0 else 0.0
    summary["unmet_reduction_pct"] = round(100.0 * (u0 - u1) / u0, 1) if u0 else 0.0
    return {"summary": summary, "example": rows[0]}
