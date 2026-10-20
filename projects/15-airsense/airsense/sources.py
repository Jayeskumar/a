"""Source hints from wind direction: pollution roses and an upwind concentration map.

Excess    e_i,t = PM_i,t - background_t        (background = 20th pct of the network)
Anomaly   a_i,t = e_i,t - median_t(e_i)         (removes each sensor's constant offset)
Rose      mean excess per 16 wind sectors (wind FROM) -> peak sector = likely source side.
CWT map   concentration-weighted trajectory, simplified for a town: every sensor-hour
          sends a straight upwind ray (up to RAY_KM); each grid cell averages the
          anomalies of the rays crossing it, down-weighted where few rays pass
          (the usual PSCF/CWT weighting). Hot cells sit over the sources.
"""

import math

from . import config as C
from .mathx import angle_diff, bearing_deg, compass, dist, median, percentile, point_polyline

SECTORS = 16
RAY_KM = 3.0
STEP_KM = 0.15
CELL_KM = 0.3


def network_background(values, sensor_ids, n_hours, flagged):
    bg = []
    for t in range(n_hours):
        vals = [values[s][t] for s in sensor_ids
                if values[s][t] is not None and (s, t) not in flagged]
        bg.append(percentile(vals, 20) if len(vals) >= 5 else None)
    return bg


def rose(values, background, wind_dir, wind_speed, flagged, sid):
    sums = [0.0] * SECTORS
    cnt = [0] * SECTORS
    for t, v in enumerate(values):
        b = background[t]
        if v is None or b is None or (sid, t) in flagged or wind_speed[t] < 0.5:
            continue
        k = int(((wind_dir[t] % 360) + 11.25) // 22.5) % SECTORS
        sums[k] += max(0.0, v - b)
        cnt[k] += 1
    means = [sums[k] / cnt[k] if cnt[k] else None for k in range(SECTORS)]
    total = sum(cnt)
    overall = sum(sums) / total if total else 0.0
    valid = [(m, k) for k, m in enumerate(means) if m is not None and cnt[k] >= 8]
    peak = max(valid) if valid else (None, None)
    return {"sectors": [{"dir": k * 22.5, "label": compass(k * 22.5),
                         "mean_excess": None if means[k] is None else round(means[k], 1),
                         "hours": cnt[k]} for k in range(SECTORS)],
            "overall_excess": round(overall, 1),
            "peak_dir": None if peak[1] is None else peak[1] * 22.5,
            "peak_label": None if peak[1] is None else compass(peak[1] * 22.5),
            "peak_excess": None if peak[0] is None else round(peak[0], 1),
            "peak_ratio": None if not peak[0] or not overall else round(peak[0] / overall, 2)}


def landmark_upwind(sx, sy, direction, max_km=4.0, tol_deg=35.0):
    """Known landmarks lying upwind of a sensor in the given wind-from direction."""
    hits = []
    for lm in C.LANDMARKS:
        if lm["kind"] == "green":
            continue
        if lm["id"] == "highway":
            d, fx, fy = point_polyline(sx, sy, C.HIGHWAY)
            lx, ly = fx, fy
        else:
            lx, ly = lm["x"], lm["y"]
            d = dist(sx, sy, lx, ly)
        if d > max_km:
            continue
        if d < 0.35:
            hits.append((d, lm["name"]))
            continue
        if angle_diff(bearing_deg(sx, sy, lx, ly), direction) <= tol_deg:
            hits.append((d, lm["name"]))
    hits.sort()
    return [{"name": n, "km": round(d, 1)} for d, n in hits]


def cwt_grid(values, sensors, background, wind_dir, wind_speed, flagged, n_hours):
    nx = int(round(C.MAP_W_KM / CELL_KM))
    ny = int(round(C.MAP_H_KM / CELL_KM))
    num = [[0.0] * nx for _ in range(ny)]
    den = [[0] * nx for _ in range(ny)]
    nsteps = int(RAY_KM / STEP_KM)
    for s in sensors:
        sid = s["id"]
        ex = [None if values[sid][t] is None or background[t] is None or (sid, t) in flagged
              else values[sid][t] - background[t] for t in range(n_hours)]
        med = median(ex) or 0.0
        for t in range(n_hours):
            e = ex[t]
            if e is None or wind_speed[t] < 0.5:
                continue
            a = e - med
            ang = math.radians(wind_dir[t])
            dx, dy = math.sin(ang), math.cos(ang)
            seen = set()
            for k in range(1, nsteps + 1):
                x = s["x"] + dx * k * STEP_KM
                y = s["y"] + dy * k * STEP_KM
                i, j = int(x / CELL_KM), int(y / CELL_KM)
                if not (0 <= i < nx and 0 <= j < ny):
                    break
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                num[j][i] += a
                den[j][i] += 1
    counts = [c for row in den for c in row if c > 0]
    avg = sum(counts) / len(counts) if counts else 1.0
    grid = []
    for j in range(ny):
        row = []
        for i in range(nx):
            n = den[j][i]
            if n == 0:
                row.append(None)
                continue
            w = 1.0 if n >= avg else (0.7 if n >= 0.5 * avg else (0.4 if n >= 0.25 * avg else 0.15))
            row.append(round(num[j][i] / n * w, 2))
        grid.append(row)
    return {"values": grid, "nx": nx, "ny": ny, "cell_km": CELL_KM}


def smooth(grid):
    ny, nx = len(grid), len(grid[0])
    out = [[None] * nx for _ in range(ny)]
    for j in range(ny):
        for i in range(nx):
            vals = [grid[b][a] for b in range(max(0, j - 1), min(ny, j + 2))
                    for a in range(max(0, i - 1), min(nx, i + 2)) if grid[b][a] is not None]
            out[j][i] = sum(vals) / len(vals) if len(vals) >= 3 else None
    return out


def hotspots(grid_info, n=4, min_sep_km=2.0):
    g = smooth(grid_info["values"])
    cell = grid_info["cell_km"]
    cands = []
    for j, row in enumerate(g):
        for i, v in enumerate(row):
            if v is not None and v > 0:
                cands.append((v, (i + 0.5) * cell, (j + 0.5) * cell))
    cands.sort(reverse=True)
    picked = []
    for v, x, y in cands:
        if all(dist(x, y, px, py) >= min_sep_km for _, px, py in picked):
            picked.append((v, x, y))
        if len(picked) >= n:
            break
    out = []
    for v, x, y in picked:
        best = None
        for lm in C.LANDMARKS:
            if lm["id"] == "highway":
                d = point_polyline(x, y, C.HIGHWAY)[0]
            else:
                d = dist(x, y, lm["x"], lm["y"])
            if best is None or d < best[0]:
                best = (d, lm)
        match = best[1] if best and best[0] <= 1.5 and best[1]["kind"] != "green" else None
        out.append({"x": round(x, 2), "y": round(y, 2), "score": round(v, 1),
                    "likely": match["name"] if match else "Unmapped source - inspect on the ground",
                    "landmark_km": round(best[0], 2) if match else None,
                    "landmark_id": match["id"] if match else None})
    return out
