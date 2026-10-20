"""Discrete-event simulation of finding donors for one request, under three strategies:

  waves       BloodLink: alert the top-ranked eligible donors in waves sized to the
              remaining need; extra acceptors go on standby; en-route donors are stood
              down the moment the need is met.
  broadcast   Baseline "forward to everyone" (WhatsApp-style): every exact-group contact
              within 60 km gets the message as it spreads; nobody knows who is eligible;
              nobody can be stood down, so every acceptor travels.
  first_come  Baseline phone list: one coordinator calls exact-group donors in register
              order, screening eligibility on the phone, until enough have agreed.

All strategies share the same donor behaviour model and *common random numbers* (each
donor's dice are seeded by request seed + donor id), so differences come from the
strategy, not from luck. Every behavioural constant is an assumption in config.py.
"""
import datetime as dt
import heapq
import math
import random

from .config import (BROADCAST_RADIUS_KM, BROADCAST_REACH_MEAN_MIN, BROADCAST_RESPONSE_FACTOR,
                     CALL_MIN, DECLINE_SHARE, DISTANCE_WILLINGNESS_KM, DONATION_MIN,
                     NOSHOW_GRACE_MIN, RECENT_CONTACT_DAYS, RECENT_CONTACT_FATIGUE,
                     RESPONSE_MEAN_MIN, SCREEN_PASS_PROB, SHOWUP_PROB, SIM_HORIZON_MIN,
                     TRAVEL_NOISE, WAVE_BUFFER, WAVE_INTERVAL_MIN,
                     WAVE_MAX, WAVE_MIN)
from .eligibility import donor_profile, evaluate
from .geo import haversine_km, travel_minutes
from .ranking import rank

STRATEGIES = {
    "waves": "BloodLink waves",
    "broadcast": "Broadcast to everyone",
    "first_come": "First-come phone list",
}


def donor_draws(seed, donor_id):
    rng = random.Random("%s:%s" % (seed, donor_id))
    return {"outcome": rng.random(), "delay": rng.expovariate(1.0 / RESPONSE_MEAN_MIN),
            "showup": rng.random(), "screen": rng.random(), "noise": rng.uniform(*TRAVEL_NOISE),
            "reach": rng.expovariate(1.0 / BROADCAST_REACH_MEAN_MIN)}


def true_accept_p(donor, km, now):
    """Simulator's hidden 'ground truth' willingness (the ranker never sees it)."""
    p = float(donor.get("sim_willingness", 0.4)) / (1 + km / DISTANCE_WILLINGNESS_KM)
    lc = donor.get("last_contacted")
    if lc:
        days = (now - dt.datetime.fromisoformat(lc)).total_seconds() / 86400.0
        if days < RECENT_CONTACT_DAYS:
            p *= RECENT_CONTACT_FATIGUE
    if not donor.get("available", True):
        p *= 0.1
    return min(1.0, max(0.0, p))


def _candidate(d, km, minutes, now, today, rank_no=None, p_est=None):
    el = evaluate(donor_profile(d), today)
    return {"id": d["id"], "name": d["name"], "group": d["group"], "km": km, "travel_min": minutes,
            "p": true_accept_p(d, km, now), "eligible": el["eligible"],
            "inelig_reason": "; ".join(el["reasons"]), "rank": rank_no, "p_est": p_est}


def build_candidates(strategy, donors, req, now, today, ranked=None):
    if strategy == "waves":
        ranked = ranked if ranked is not None else rank(donors, req, now, today)["ranked"]
        by_id = {d["id"]: d for d in donors}
        out = []
        for x in ranked:
            p_acc_est = x["p_unit_est"] / (SHOWUP_PROB * SCREEN_PASS_PROB)
            out.append(_candidate(by_id[x["id"]], x["km"], x["travel_min"], now, today, x["rank"], p_acc_est))
        return out
    out = []
    for d in donors:
        if d["group"] != req["group"]:      # families/lists ask for the exact group
            continue
        km = haversine_km(d["lat"], d["lon"], req["lat"], req["lon"])
        if km > BROADCAST_RADIUS_KM:
            continue
        out.append(_candidate(d, round(km, 2), round(travel_minutes(km), 1), now, today))
    if strategy == "first_come":
        order = {d["id"]: d.get("list_order", i) for i, d in enumerate(donors)}
        out.sort(key=lambda c: order[c["id"]])
    return out


def run(strategy, cands, units, seed, horizon=SIM_HORIZON_MIN, broadcast_factor=None):
    """Simulate one strategy; returns metrics, a cumulative-units curve and an event log."""
    if strategy not in STRATEGIES:
        raise ValueError("unknown strategy")
    bf = BROADCAST_RESPONSE_FACTOR if broadcast_factor is None else broadcast_factor
    coordinated = strategy != "broadcast"
    target = math.ceil(units * (1 + WAVE_BUFFER)) if strategy == "waves" else units
    heap, seq = [], [0]
    log, curve = [], [[0.0, 0]]
    st = {"collected": 0, "in_donation": set(), "en_route": {}, "standby": [], "fulfilled_at": None,
          "alerts": 0, "accepted": 0, "declined": 0, "no_reply": 0, "surplus": 0, "wasted": 0,
          "deferred": 0, "noshow": 0, "waves": 0, "next": 0, "pending": {}, "caller_busy": False,
          "notified": [], "accepted_ids": [], "donated_ids": [], "wasted_calls": 0}
    draws = {c["id"]: donor_draws(seed, c["id"]) for c in cands}

    def push(t, kind, c=None):
        seq[0] += 1
        heapq.heappush(heap, (t, seq[0], kind, c))

    def note(t, kind, text, c=None, **extra):
        e = {"t": round(t, 1), "kind": kind, "text": text}
        if c is not None:
            e.update(donor=c["id"], name=c["name"], group=c["group"], rank=c.get("rank"))
        e.update(extra)
        log.append(e)

    def active():
        return st["collected"] + len(st["in_donation"]) + len(st["en_route"])

    def p_eff(c):
        return c["p"] * (bf if strategy == "broadcast" else 1.0)

    def depart(c, t):
        dr = draws[c["id"]]
        st["en_route"][c["id"]] = c
        eta = c["travel_min"] * dr["noise"]
        if dr["showup"] < SHOWUP_PROB:
            push(t + eta, "arrive", c)
        else:
            push(t + c["travel_min"] + NOSHOW_GRACE_MIN, "noshow", c)
        return eta

    def refill(t):
        if not coordinated or st["fulfilled_at"] is not None:
            return
        if st["standby"] and active() < target:
            c = st["standby"].pop(0)
            eta = depart(c, t)
            note(t, "standby", "%s called in from standby, ETA ~%d min" % (c["name"], eta), c)
        if strategy == "first_come" and not st["caller_busy"] and active() < target:
            st["caller_busy"] = True
            push(t, "call")

    # ---- policy kick-off -------------------------------------------------------------
    if not cands:
        note(0, "info", "No candidate donors for this request")
    elif strategy == "waves":
        push(0.0, "wave")
    elif strategy == "broadcast":
        st["alerts"] = len(cands)
        st["notified"] = [c["id"] for c in cands]
        note(0, "wave", "Request forwarded to %d %s contacts within %d km (eligibility unknown)" % (
            len(cands), cands[0]["group"], BROADCAST_RADIUS_KM), count=len(cands))
        for c in cands:
            push(draws[c["id"]]["reach"] + draws[c["id"]]["delay"], "response", c)
    else:
        st["caller_busy"] = True
        push(0.0, "call")

    while heap:
        t, _, kind, c = heapq.heappop(heap)
        if t > horizon:
            break
        done = st["fulfilled_at"] is not None
        if done and coordinated:
            break
        if kind == "wave":
            if done:
                continue
            exp_pending = sum(x["p_est"] for x, t0 in st["pending"].values() if t - t0 <= 2.5 * RESPONSE_MEAN_MIN)
            need = target - active() - len(st["standby"]) - exp_pending
            if need > 0 and st["next"] < len(cands):
                nxt = cands[st["next"]:st["next"] + WAVE_MAX]
                avg = max(0.05, sum(x["p_est"] * SHOWUP_PROB * SCREEN_PASS_PROB for x in nxt) / len(nxt))
                size = max(WAVE_MIN, min(WAVE_MAX, math.ceil(need / avg)))
                batch = cands[st["next"]:st["next"] + size]
                st["next"] += len(batch)
                st["waves"] += 1
                for x in batch:
                    st["alerts"] += 1
                    st["notified"].append(x["id"])
                    st["pending"][x["id"]] = (x, t)
                    push(t + draws[x["id"]]["delay"], "response", x)
                note(t, "wave", "Wave %d: alerted %d donor%s (rank %d-%d)" % (
                    st["waves"], len(batch), "" if len(batch) == 1 else "s", batch[0]["rank"], batch[-1]["rank"]),
                     ids=[x["id"] for x in batch])
            more = st["next"] < len(cands) or st["en_route"] or st["in_donation"] or st["pending"]
            if more and t + WAVE_INTERVAL_MIN <= horizon:
                push(t + WAVE_INTERVAL_MIN, "wave")
        elif kind == "call":
            if done or active() >= target:
                st["caller_busy"] = False
                continue
            if st["next"] >= len(cands):
                st["caller_busy"] = False
                if not st["en_route"] and not st["in_donation"]:
                    note(t, "info", "Reached the end of the phone list")
                continue
            c = cands[st["next"]]
            st["next"] += 1
            st["alerts"] += 1
            st["notified"].append(c["id"])
            u = draws[c["id"]]["outcome"]
            tc = t + CALL_MIN
            if u < p_eff(c):
                if not c["eligible"]:
                    st["wasted_calls"] += 1
                    note(tc, "decline", "%s willing but not eligible (%s)" % (c["name"], c["inelig_reason"]), c)
                else:
                    st["accepted"] += 1
                    st["accepted_ids"].append(c["id"])
                    eta = depart(c, tc)
                    note(tc, "accept", "%s agreed on the phone, ETA ~%d min (%.1f km)" % (c["name"], eta, c["km"]), c)
            elif u < p_eff(c) + (1 - p_eff(c)) * DECLINE_SHARE:
                st["declined"] += 1
                note(tc, "decline", "%s declined" % c["name"], c)
            else:
                st["no_reply"] += 1
                note(tc, "silent", "%s did not answer" % c["name"], c)
            push(tc, "call")
        elif kind == "response":
            st["pending"].pop(c["id"], None)
            u = draws[c["id"]]["outcome"]
            p = p_eff(c)
            if u < p:
                st["accepted"] += 1
                st["accepted_ids"].append(c["id"])
                if coordinated and active() >= target:
                    st["standby"].append(c)
                    note(t, "standby", "%s accepted - kept on standby (need covered)" % c["name"], c)
                else:
                    eta = depart(c, t)
                    note(t, "accept", "%s accepted, ETA ~%d min (%.1f km)" % (c["name"], eta, c["km"]), c)
            elif u < p + (1 - p) * DECLINE_SHARE:
                st["declined"] += 1
                if strategy == "waves":
                    note(t, "decline", "%s declined" % c["name"], c)
            else:
                st["no_reply"] += 1
        elif kind == "noshow":
            if c["id"] not in st["en_route"]:
                continue
            del st["en_route"][c["id"]]
            st["noshow"] += 1
            note(t, "noshow", "%s did not arrive (no-show)" % c["name"], c)
            refill(t)
        elif kind == "arrive":
            if c["id"] not in st["en_route"]:
                continue   # stood down earlier
            del st["en_route"][c["id"]]
            if st["collected"] + len(st["in_donation"]) >= units:
                st["surplus"] += 1
                note(t, "surplus", "%s arrived but the need was already met - sent home" % c["name"], c)
                continue
            if not c["eligible"]:
                st["wasted"] += 1
                note(t, "defer", "%s deferred at screening: %s (wasted trip)" % (c["name"], c["inelig_reason"]), c)
                refill(t)
                continue
            if draws[c["id"]]["screen"] >= SCREEN_PASS_PROB:
                st["deferred"] += 1
                note(t, "defer", "%s deferred at on-site check (Hb/BP)" % c["name"], c)
                refill(t)
                continue
            st["in_donation"].add(c["id"])
            note(t, "arrive", "%s arrived, screening passed - donating" % c["name"], c)
            push(t + DONATION_MIN, "collect", c)
            if coordinated and st["collected"] + len(st["in_donation"]) >= units and st["en_route"]:
                for x in st["en_route"].values():   # every unit is now being drawn: stand the rest down
                    st["surplus"] += 1
                    note(t, "surplus", "%s stood down en route (thank-you sent)" % x["name"], x)
                st["en_route"].clear()
        elif kind == "collect":
            st["in_donation"].discard(c["id"])
            st["collected"] += 1
            st["donated_ids"].append(c["id"])
            curve.append([round(t, 1), st["collected"]])
            note(t, "collect", "Unit %d/%d collected from %s" % (st["collected"], units, c["name"]), c)
            if st["collected"] >= units and st["fulfilled_at"] is None:
                st["fulfilled_at"] = t
                note(t, "fulfilled", "Request fulfilled in %d min" % round(t))
                if coordinated:
                    for x in st["en_route"].values():
                        st["surplus"] += 1
                        note(t, "surplus", "%s stood down en route (thank-you sent)" % x["name"], x)
                    st["en_route"].clear()
                    if st["standby"]:
                        note(t, "info", "%d standby donor%s released" % (
                            len(st["standby"]), "" if len(st["standby"]) == 1 else "s"))
    if st["fulfilled_at"] is None and cands:
        note(min(horizon, log[-1]["t"] if log else 0), "info",
             "Not fulfilled: %d of %d units within %d min" % (st["collected"], units, horizon))
    curve.append([round(st["fulfilled_at"] if st["fulfilled_at"] is not None else horizon, 1), st["collected"]])
    log.sort(key=lambda e: e["t"])
    return {
        "strategy": strategy, "label": STRATEGIES[strategy], "units": units,
        "fulfilled": st["fulfilled_at"] is not None,
        "time_to_fulfil": round(st["fulfilled_at"], 1) if st["fulfilled_at"] is not None else None,
        "collected": st["collected"], "alerts": st["alerts"], "accepted": st["accepted"],
        "declined": st["declined"], "no_reply": st["no_reply"], "surplus_trips": st["surplus"],
        "wasted_trips": st["wasted"], "wasted_calls": st["wasted_calls"], "deferred_on_site": st["deferred"],
        "no_shows": st["noshow"], "waves": st["waves"], "candidates": len(cands),
        "curve": curve, "events": log[:400], "notified_ids": st["notified"],
        "accepted_ids": st["accepted_ids"], "donated_ids": st["donated_ids"],
    }


def compare(donors, req, now, today, seed=1, ranked=None, broadcast_factor=None):
    out = {}
    for s in STRATEGIES:
        cands = build_candidates(s, donors, req, now, today, ranked)
        out[s] = run(s, cands, req["units"], seed, broadcast_factor=broadcast_factor)
    return out


def _pct(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 1)


def evaluate_strategies(donors, hospitals, now, today, n=200, seed=11, broadcast_factor=None):
    """Monte Carlo over random requests; returns per-strategy summary statistics."""
    rng = random.Random(seed)
    from .config import GROUP_SHARE, BLOOD_GROUPS
    rows = {s: [] for s in STRATEGIES}
    for i in range(n):
        r = rng.random()
        acc, group = 0.0, BLOOD_GROUPS[-1]
        for g in BLOOD_GROUPS:
            acc += GROUP_SHARE[g]
            if r < acc:
                group = g
                break
        h = rng.choice(hospitals)
        req = {"group": group, "units": rng.choice([1, 2, 2, 3, 4]), "urgency": rng.choice(["critical", "urgent"]),
               "lat": h["lat"], "lon": h["lon"], "hospital_id": h["id"], "place": h["name"]}
        res = compare(donors, req, now, today, seed=seed * 1000 + i, broadcast_factor=broadcast_factor)
        for s, m in res.items():
            rows[s].append(m)
    summary = {}
    for s, ms in rows.items():
        times = [m["time_to_fulfil"] for m in ms if m["fulfilled"]]
        summary[s] = {
            "label": STRATEGIES[s], "requests": len(ms),
            "fulfilled_pct": round(100.0 * len(times) / len(ms), 1),
            "within_60_pct": round(100.0 * sum(1 for t in times if t <= 60) / len(ms), 1),
            "within_120_pct": round(100.0 * sum(1 for t in times if t <= 120) / len(ms), 1),
            "median_min": _pct(times, 0.5), "p90_min": _pct(times, 0.9),
            "mean_alerts": round(sum(m["alerts"] for m in ms) / len(ms), 1),
            "mean_surplus_trips": round(sum(m["surplus_trips"] for m in ms) / len(ms), 2),
            "mean_wasted_trips": round(sum(m["wasted_trips"] for m in ms) / len(ms), 2),
            "mean_wasted_calls": round(sum(m["wasted_calls"] for m in ms) / len(ms), 2),
        }
    # paired comparison: on requests both fulfilled, how often is BloodLink faster?
    pairs = [(a["time_to_fulfil"], b["time_to_fulfil"]) for a, b in zip(rows["waves"], rows["broadcast"])
             if a["fulfilled"] and b["fulfilled"]]
    pairs2 = [(a["time_to_fulfil"], b["time_to_fulfil"]) for a, b in zip(rows["waves"], rows["first_come"])
              if a["fulfilled"] and b["fulfilled"]]
    summary["paired"] = {
        "vs_broadcast_faster_pct": round(100.0 * sum(1 for a, b in pairs if a < b) / len(pairs), 1) if pairs else None,
        "vs_first_come_faster_pct": round(100.0 * sum(1 for a, b in pairs2 if a < b) / len(pairs2), 1) if pairs2 else None,
    }
    summary["n"] = n
    summary["seed"] = seed
    summary["broadcast_factor"] = BROADCAST_RESPONSE_FACTOR if broadcast_factor is None else broadcast_factor
    return summary
