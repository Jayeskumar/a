"""Hotspots: DBSCAN on incident locations, weekly ward grid and a Poisson emerging-hotspot test."""

import math

from . import config as C
from .dedup import haversine_m


def dbscan(points, eps_m=C.DBSCAN_EPS_M, min_pts=C.DBSCAN_MIN_PTS):
    """DBSCAN over (lat, lon) points with haversine distance and a grid index.

    Returns labels: -1 = noise, 0..k-1 = cluster id. A point is *core* if at least min_pts
    points (itself included) lie within eps; clusters are core points chained by eps plus
    the border points they reach.
    """
    n = len(points)
    if n == 0:
        return []
    lat0 = sum(p[0] for p in points) / n
    dlat = eps_m / 110574.0
    dlon = eps_m / (111320.0 * math.cos(math.radians(lat0)))
    grid = {}
    cells = []
    for i, (la, lo) in enumerate(points):
        key = (int(math.floor(la / dlat)), int(math.floor(lo / dlon)))
        cells.append(key)
        grid.setdefault(key, []).append(i)

    def neighbours(i):
        ci, cj = cells[i]
        la, lo = points[i]
        out = []
        for a in (ci - 1, ci, ci + 1):
            for b in (cj - 1, cj, cj + 1):
                for j in grid.get((a, b), ()):
                    if haversine_m(la, lo, points[j][0], points[j][1]) <= eps_m:
                        out.append(j)
        return out

    labels = [None] * n
    cid = -1
    for i in range(n):
        if labels[i] is not None:
            continue
        nb = neighbours(i)
        if len(nb) < min_pts:
            labels[i] = -1
            continue
        cid += 1
        labels[i] = cid
        queue = [j for j in nb if j != i]
        k = 0
        while k < len(queue):
            j = queue[k]
            k += 1
            if labels[j] == -1:
                labels[j] = cid           # border point
            if labels[j] is not None:
                continue
            labels[j] = cid
            nb2 = neighbours(j)
            if len(nb2) >= min_pts:
                queue.extend(nb2)
    return labels


def summarise_clusters(points, labels):
    groups = {}
    for i, l in enumerate(labels):
        if l is not None and l >= 0:
            groups.setdefault(l, []).append(i)
    out = []
    for l in sorted(groups):
        mem = groups[l]
        la = sum(points[i][0] for i in mem) / len(mem)
        lo = sum(points[i][1] for i in mem) / len(mem)
        d = sorted(haversine_m(la, lo, points[i][0], points[i][1]) for i in mem)
        out.append({"cluster": l, "members": mem, "n": len(mem), "center": [round(la, 6), round(lo, 6)],
                    "radius_m": round(d[int(0.9 * (len(d) - 1))], 1)})
    return out


def match_planted(detected, planted, max_m=C.HOTSPOT_MATCH_M):
    """Greedy one-to-one matching of detected clusters to planted hotspots of the same department."""
    pairs = []
    for di, d in enumerate(detected):
        for pi, p in enumerate(planted):
            if d["dept"] != p["dept"]:
                continue
            m = haversine_m(d["center"][0], d["center"][1], p["center"][0], p["center"][1])
            if m <= max_m:
                pairs.append((m, di, pi))
    pairs.sort()
    used_d, used_p, matches = set(), set(), {}
    for m, di, pi in pairs:
        if di in used_d or pi in used_p:
            continue
        used_d.add(di)
        used_p.add(pi)
        matches[di] = (pi, m)
    return matches


# ----------------------------------------------------------------------------- emerging hotspots
def poisson_z(x, lam, floor=C.EMERGING_LAMBDA_FLOOR):
    lam = max(lam, floor)
    return (x - lam) / math.sqrt(lam)


def poisson_sf(x, lam, floor=C.EMERGING_LAMBDA_FLOOR):
    """P(X >= x) for X ~ Poisson(lam)."""
    lam = max(lam, floor)
    if x <= 0:
        return 1.0
    term = math.exp(-lam)
    cdf = term
    for k in range(1, int(x)):
        term *= lam / k
        cdf += term
    return max(0.0, 1.0 - cdf)


def emerging_test(series, week, baseline=C.EMERGING_BASELINE_WEEKS, z_thr=C.EMERGING_Z,
                  min_count=C.EMERGING_MIN_COUNT):
    """series: weekly counts indexed 0.. (week 1 = index 0). Tests `week` vs the previous `baseline` weeks."""
    i = week - 1
    if i < baseline or i >= len(series):
        return None
    base = series[i - baseline:i]
    lam = sum(base) / float(baseline)
    x = series[i]
    z = poisson_z(x, lam)
    return {"x": x, "lambda": round(lam, 2), "z": round(z, 2), "p": poisson_sf(x, lam),
            "flag": bool(z >= z_thr and x >= min_count)}
