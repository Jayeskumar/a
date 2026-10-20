"""Drone spray-mission planner: boustrophedon (lawn-mower) coverage of target cells only.

1. Group target cells into *blocks*: targets closer than one swath share a block, so swaths of
   different blocks can never overlap (no cell is sprayed twice).
2. Inside a block, cut it into bands one swath wide. Each band is one straight pass; passes
   alternate direction (boustrophedon). The drone sprays only the columns of the band that
   contain targets and flies over short gaps with the nozzles off.
3. Turn minimisation: for every block try east-west and north-south passes and both start
   corners, estimate flight time (spray + shifts + TURN_S per turn + ferry from the current
   position) and keep the cheapest. Fewer, longer passes = fewer turns.
4. Capacity: walk the path one 1 m swath-column at a time. Before each column check that the
   tank holds the liquid it needs and that the battery can still finish it *and* fly home with
   the reserve. Otherwise return to home (RTH), refill / swap battery, and fly back to resume.
"""
import math

from . import config, segment


class PlanError(ValueError):
    pass


def _dilate_square(mask, w, h, r):
    """Separable square dilation (Chebyshev radius r) in O(cells)."""
    rows = [False] * (w * h)
    for y in range(h):
        base = y * w
        pref = [0]
        for x in range(w):
            pref.append(pref[-1] + (1 if mask[base + x] else 0))
        for x in range(w):
            a, b = max(0, x - r), min(w, x + r + 1)
            rows[base + x] = pref[b] - pref[a] > 0
    out = [False] * (w * h)
    for x in range(w):
        pref = [0]
        for y in range(h):
            pref.append(pref[-1] + (1 if rows[y * w + x] else 0))
        for y in range(h):
            a, b = max(0, y - r), min(h, y + r + 1)
            out[y * w + x] = pref[b] - pref[a] > 0
    return out


def blocks_of(target, w, h, swath):
    dil = _dilate_square(target, w, h, swath)
    out = []
    for cells in segment.mask_components(dil, w, h, connectivity=8):
        t = [i for i in cells if target[i]]
        if t:
            out.append(t)
    return out


def _passes(cells, w, h, swath, orient):
    """Bands of one block. Works in a frame where passes run along u (x for 'h', y for 'v')."""
    if orient == "h":
        coords = [(i % w, i // w) for i in cells]
        lim_v = h
    else:
        coords = [(i // w, i % w) for i in cells]      # (u=y, v=x)
        lim_v = w
    by_v = {}
    for u, v in coords:
        by_v.setdefault(v, set()).add(u)
    v_min, v_max = min(by_v), max(by_v)
    passes = []
    for v0 in range(v_min, v_max + 1, swath):
        v1 = min(v0 + swath, lim_v)
        us = set()
        for v in range(v0, v1):
            us |= by_v.get(v, set())
        if not us:
            continue
        us = sorted(us)
        runs = [[us[0], us[0]]]
        for u in us[1:]:
            if u == runs[-1][1] + 1:
                runs[-1][1] = u
            else:
                runs.append([u, u])
        passes.append({"v0": v0, "v1": v1, "line": (v0 + v1) / 2.0, "runs": runs})
    return passes


def _to_xy(orient, u, v):
    return (u, v) if orient == "h" else (v, u)


def _variant_steps(passes, orient, reverse_bands, first_dir):
    """Ordered list of 1 m spray steps for one variant of a block."""
    order = list(reversed(passes)) if reverse_bands else passes
    steps = []
    d = first_dir
    for pi, p in enumerate(order):
        runs = p["runs"] if d > 0 else [[b, a] for a, b in reversed(p["runs"])]
        for ri, (a, b) in enumerate(runs):
            rng = range(a, b + 1) if d > 0 else range(a, b - 1, -1)
            for u in rng:
                u_start, u_end = (u, u + 1) if d > 0 else (u + 1, u)
                steps.append({"pass": pi, "run": ri, "u": u, "v0": p["v0"], "v1": p["v1"],
                              "start": _to_xy(orient, u_start, p["line"]),
                              "end": _to_xy(orient, u_end, p["line"]), "orient": orient})
        d = -d
    return steps


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _estimate(steps, start_pos, prm):
    """Flight-time estimate ignoring capacity: ferry + spray + gaps + shifts + turns."""
    t = _dist(start_pos, steps[0]["start"]) / prm["transit"]
    turns = 0
    prev = None
    for s in steps:
        if prev is not None:
            gap = _dist(prev["end"], s["start"])
            if s["pass"] != prev["pass"]:
                turns += 1
                t += prm["turn"] + gap / prm["transit"]
            elif gap > 1e-9:
                t += gap / (prm["spray"] if gap <= prm["bridge"] else prm["transit"])
        t += config.CELL_M / prm["spray"]
        prev = s
    return t, turns


def _best_variant(cells, w, h, pos, prm, orient_mode):
    options = []
    orients = ("h", "v") if orient_mode == "auto" else (orient_mode,)
    per_orient = {}
    for o in orients:
        ps = _passes(cells, w, h, prm["swath"], o)
        best_o = None
        for rev in (False, True):
            for fd in (1, -1):
                st = _variant_steps(ps, o, rev, fd)
                t, turns = _estimate(st, pos, prm)
                cand = (t, turns, o, st)
                if best_o is None or t < best_o[0]:
                    best_o = cand
        per_orient[o] = {"passes": len(ps), "turns": best_o[1], "est_time_s": round(best_o[0], 1)}
        options.append(best_o)
    best = min(options, key=lambda c: c[0])
    return best, per_orient


def plan(target, payload_per_m2, w, h, swath=config.DRONE_SWATH_M, tank=config.DRONE_TANK_L,
         endurance_s=config.DRONE_ENDURANCE_S, spray_speed=config.DRONE_SPRAY_SPEED_MS,
         transit_speed=config.DRONE_TRANSIT_SPEED_MS, turn_s=config.DRONE_TURN_S,
         reserve=config.DRONE_RESERVE_FRAC, takeoff_land_s=config.DRONE_TAKEOFF_LAND_S,
         turnaround_s=config.DRONE_TURNAROUND_S, home=config.HOME_XY,
         gap_bridge=config.DRONE_GAP_BRIDGE_CELLS, orient="auto"):
    """Plan sorties covering every target cell. payload_per_m2: per-cell litres (or kg) / m^2."""
    swath = int(swath)
    if swath < 1:
        raise PlanError("swath must be at least 1 m")
    if orient not in ("auto", "h", "v"):
        raise PlanError("orient must be auto, h or v")
    prm = {"swath": swath, "spray": float(spray_speed), "transit": float(transit_speed),
           "turn": float(turn_s), "bridge": float(gap_bridge)}
    budget = endurance_s * (1.0 - reserve)
    half_tl = takeoff_land_s / 2.0
    home = (float(home[0]), float(home[1]))
    n_target = sum(1 for t in target if t)
    blocks = blocks_of(target, w, h, swath)
    # order blocks greedily by nearest entry from the current position
    pos = home
    remaining = list(range(len(blocks)))
    ordered_steps = []
    block_info = []
    while remaining:
        best = None
        for bi in remaining:
            cand, per_o = _best_variant(blocks[bi], w, h, pos, prm, orient)
            if best is None or cand[0] < best[1][0]:
                best = (bi, cand, per_o)
        bi, (t_est, turns, o, steps), per_o = best
        remaining.remove(bi)
        tag = len(block_info)
        for s in steps:
            s["block"] = tag
        ordered_steps.extend(steps)
        block_info.append({"block": tag, "cells": len(blocks[bi]), "orientation": o,
                           "turns": turns, "est_time_s": round(t_est, 1), "options": per_o})
        pos = steps[-1]["end"]

    coverage = [0] * (w * h)
    sorties = []
    cur = None

    def new_sortie():
        return {"id": len(sorties) + 1, "legs": [], "time_s": half_tl, "payload": 0.0,
                "dist": {"ferry": 0.0, "spray": 0.0, "gap": 0.0, "shift": 0.0, "rth": 0.0},
                "turns": 0, "target_cells": 0, "overspray_cells": 0, "columns": 0}

    def add_leg(s, kind, a, b):
        d = _dist(a, b)
        if d < 1e-9:
            return
        legs = s["legs"]
        if legs and legs[-1]["kind"] == kind and kind in ("spray", "gap") and \
                _dist(legs[-1]["pts"][-1], a) < 1e-9:
            last = legs[-1]["pts"]
            # extend a straight leg (same direction) instead of adding a point
            if len(last) >= 2 and abs((last[-1][0] - last[-2][0]) * (b[1] - a[1]) -
                                      (last[-1][1] - last[-2][1]) * (b[0] - a[0])) < 1e-9:
                last[-1] = [round(b[0], 2), round(b[1], 2)]
            else:
                last.append([round(b[0], 2), round(b[1], 2)])
        else:
            legs.append({"kind": kind, "pts": [[round(a[0], 2), round(a[1], 2)],
                                               [round(b[0], 2), round(b[1], 2)]]})
        s["dist"][kind] += d

    def close(s, at):
        t_back = _dist(at, home) / prm["transit"]
        add_leg(s, "rth", at, home)
        s["time_s"] += t_back + half_tl
        sorties.append(s)

    payload_left = tank
    pos = home
    prev = None
    for st in ordered_steps:
        # cells under the swath for this column
        cells = []
        for v in range(st["v0"], st["v1"]):
            x, y = _to_xy(st["orient"], st["u"], v)
            if 0 <= x < w and 0 <= y < h:
                cells.append(y * w + x)
        rates = [payload_per_m2[i] for i in cells if target[i]]
        need = (max(rates) if rates else 0.0) * len(cells) * config.CELL_AREA_M2
        step_t = config.CELL_M / prm["spray"]
        if cur is None:
            cur = new_sortie()
            payload_left = tank
            pos = home
            prev = None
        if prev is None:
            kind, move_t = "ferry", _dist(pos, st["start"]) / prm["transit"]
        elif st["pass"] != prev["pass"] or st["block"] != prev["block"]:
            gap = _dist(pos, st["start"])
            kind, move_t = "shift", prm["turn"] + gap / prm["transit"]
        else:
            gap = _dist(pos, st["start"])
            kind = "gap"
            move_t = gap / (prm["spray"] if gap <= prm["bridge"] else prm["transit"])
        ret_t = _dist(st["end"], home) / prm["transit"] + half_tl
        if prev is not None and (cur["time_s"] + move_t + step_t + ret_t > budget or
                                 payload_left + 1e-9 < need):
            close(cur, pos)
            cur = new_sortie()
            payload_left = tank
            pos = home
            prev = None
            kind, move_t = "ferry", _dist(pos, st["start"]) / prm["transit"]
        if cur["time_s"] + move_t + step_t + ret_t > budget + 1e-9:
            raise PlanError("battery endurance too short to reach (%.0f, %.0f) and return"
                            % st["start"])
        if need > tank + 1e-9:
            raise PlanError("tank smaller than one swath-column of liquid (%.3f)" % need)
        add_leg(cur, kind, pos, st["start"])
        if kind == "shift":
            cur["turns"] += 1
        add_leg(cur, "spray", st["start"], st["end"])
        cur["time_s"] += move_t + step_t
        cur["payload"] += need
        cur["columns"] += 1
        payload_left -= need
        for i in cells:
            coverage[i] += 1
            if target[i]:
                cur["target_cells"] += 1
            else:
                cur["overspray_cells"] += 1
        pos = st["end"]
        prev = st
    if cur is not None:
        close(cur, pos)

    covered_once = sum(1 for i in range(w * h) if target[i] and coverage[i] == 1)
    multi = sum(1 for i in range(w * h) if target[i] and coverage[i] > 1)
    missed = sum(1 for i in range(w * h) if target[i] and coverage[i] == 0)
    overspray = sum(1 for i in range(w * h) if not target[i] and coverage[i] > 0)
    tot_dist = sum(sum(s["dist"].values()) for s in sorties)
    spray_dist = sum(s["dist"]["spray"] for s in sorties)
    infield = sum(s["dist"]["spray"] + s["dist"]["gap"] + s["dist"]["shift"] for s in sorties)
    flight_t = sum(s["time_s"] for s in sorties)
    out_sorties = []
    for s in sorties:
        dist = sum(s["dist"].values())
        out_sorties.append({
            "id": s["id"], "legs": s["legs"], "distance_m": round(dist, 1),
            "spray_m": round(s["dist"]["spray"], 1),
            "dist_by_kind": {k: round(v, 1) for k, v in s["dist"].items()},
            "time_s": round(s["time_s"], 1), "payload": round(s["payload"], 3),
            "tank_pct": round(100.0 * s["payload"] / tank, 1) if tank else 0.0,
            "battery_pct": round(100.0 * s["time_s"] / endurance_s, 1),
            "turns": s["turns"], "target_cells": s["target_cells"],
            "overspray_cells": s["overspray_cells"]})
    n_s = len(out_sorties)
    return {
        "sorties": out_sorties,
        "blocks": block_info,
        "params": {"swath_m": swath, "tank": tank, "endurance_s": endurance_s,
                   "spray_speed": spray_speed, "transit_speed": transit_speed, "turn_s": turn_s,
                   "reserve": reserve, "turnaround_s": turnaround_s, "home": list(home),
                   "orient": orient},
        "totals": {
            "sorties": n_s, "distance_m": round(tot_dist, 1), "spray_m": round(spray_dist, 1),
            "flight_time_s": round(flight_t, 1),
            "mission_time_s": round(flight_t + max(0, n_s - 1) * turnaround_s, 1),
            "payload": round(sum(s["payload"] for s in sorties), 3),
            "turns": sum(s["turns"] for s in sorties),
            "path_efficiency": round(spray_dist / tot_dist, 4) if tot_dist else 0.0,
            "infield_efficiency": round(spray_dist / infield, 4) if infield else 0.0,
            "target_cells": n_target, "covered_once": covered_once, "covered_multi": multi,
            "missed": missed, "overspray_cells": overspray,
            "overspray_pct": round(100.0 * overspray / n_target, 1) if n_target else 0.0,
            "coverage_pct": round(100.0 * (covered_once + multi) / n_target, 2)
            if n_target else 100.0},
        "coverage": coverage,
    }
