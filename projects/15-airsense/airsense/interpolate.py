"""Spatial interpolation: inverse-distance weighting and ordinary kriging.

IDW:      z(x) = sum_i w_i z_i / sum_i w_i,   w_i = 1 / d_i^p
Kriging:  exponential variogram  g(h) = c0 + c1 * (1 - exp(-h / a))  fitted to the pooled,
          per-hour standardised empirical semivariogram; ordinary-kriging system
          [G 1; 1' 0] [w; mu] = [g0; 1]  gives weights and the kriging variance
          s^2 = w' g0 + mu  (our uncertainty).
Leave-one-out errors for kriging use Dubrule's (1983) shortcut: e_i = c_i / (A^-1)_ii
with c = A^-1 [z; 0], so one matrix inverse gives all n cross-validation residuals.
"""

import math

from . import config as C
from .mathx import dist, inverse, matvec, mean, std


# ----------------------------------------------------------------- IDW
def idw(points, x, y, power=C.IDW_POWER):
    """points: list of (x, y, value). Returns the IDW estimate at (x, y)."""
    num = den = 0.0
    for px, py, v in points:
        d = dist(px, py, x, y)
        if d < 1e-9:
            return v
        w = 1.0 / d ** power
        num += w * v
        den += w
    return num / den if den else None


def idw_weights(points, x, y, power=C.IDW_POWER):
    ws = []
    for px, py, v in points:
        d = dist(px, py, x, y)
        ws.append(1e12 if d < 1e-9 else 1.0 / d ** power)
    s = sum(ws)
    return [w / s for w in ws]


def idw_loo(points, power=C.IDW_POWER):
    """Leave-one-out predictions for every point."""
    out = []
    for i in range(len(points)):
        rest = points[:i] + points[i + 1:]
        out.append(idw(rest, points[i][0], points[i][1], power))
    return out


# ----------------------------------------------------------------- variogram
def empirical_variogram(snapshots, bin_km=0.6, max_km=7.2):
    """Pooled semivariogram of per-snapshot standardised values.

    snapshots: list of point lists [(x, y, v), ...]. Returns bins with h, gamma, n.
    """
    nb = int(round(max_km / bin_km))
    sums = [0.0] * nb
    cnt = [0] * nb
    hs = [0.0] * nb
    for pts in snapshots:
        if len(pts) < 5:
            continue
        vals = [p[2] for p in pts]
        mu, sd = mean(vals), std(vals)
        if not sd:
            continue
        z = [(v - mu) / sd for v in vals]
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                h = dist(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
                k = int(h / bin_km)
                if k < nb:
                    sums[k] += 0.5 * (z[i] - z[j]) ** 2
                    cnt[k] += 1
                    hs[k] += h
    return [{"h": hs[k] / cnt[k], "gamma": sums[k] / cnt[k], "n": cnt[k]}
            for k in range(nb) if cnt[k] >= 10]


def exp_model(h, nugget, psill, rng):
    if h <= 0:
        return 0.0
    return nugget + psill * (1.0 - math.exp(-h / rng))


def fit_variogram(bins):
    """Weighted least squares (Cressie-style n/gamma^2 weights) over a grid of ranges;
    nugget and partial sill are solved in closed form for each range."""
    best = None
    for k in range(3, 81):
        a = k * 0.1
        rows = [(1.0, 1.0 - math.exp(-b["h"] / a), b["gamma"], b["n"] / max(b["gamma"], 0.05) ** 2)
                for b in bins]
        s11 = sum(w * x0 * x0 for x0, x1, g, w in rows)
        s12 = sum(w * x0 * x1 for x0, x1, g, w in rows)
        s22 = sum(w * x1 * x1 for x0, x1, g, w in rows)
        t1 = sum(w * x0 * g for x0, x1, g, w in rows)
        t2 = sum(w * x1 * g for x0, x1, g, w in rows)
        det = s11 * s22 - s12 * s12
        if abs(det) < 1e-12:
            continue
        c0 = (t1 * s22 - t2 * s12) / det
        c1 = (s11 * t2 - s12 * t1) / det
        if c0 < 0:
            c0 = 0.0
            c1 = t2 / s22 if s22 else 0.0
        if c1 <= 0:
            continue
        sse = sum(w * (c0 + c1 * x1 - g) ** 2 for x0, x1, g, w in rows)
        if best is None or sse < best[0]:
            best = (sse, c0, c1, a)
    if best is None:
        return {"model": "exponential", "nugget": 0.1, "psill": 0.9, "range": 2.0}
    _, c0, c1, a = best
    return {"model": "exponential", "nugget": c0, "psill": c1, "range": a,
            "practical_range_km": 3 * a}


# ----------------------------------------------------------------- ordinary kriging
class Kriging:
    """Ordinary kriging for one snapshot. `scale` multiplies the normalised variogram
    (we use the snapshot's sample variance) so the variance comes out in data units."""

    def __init__(self, points, vario, scale=1.0):
        if len(points) < 3:
            raise ValueError("kriging needs at least 3 points")
        self.points = points
        self.v = vario
        self.scale = scale
        n = len(points)
        a = [[0.0] * (n + 1) for _ in range(n + 1)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    a[i][j] = self.gamma(dist(points[i][0], points[i][1], points[j][0], points[j][1]))
            a[i][n] = a[n][i] = 1.0
        self.ainv = inverse(a)
        self.n = n

    def gamma(self, h):
        return self.scale * exp_model(h, self.v["nugget"], self.v["psill"], self.v["range"])

    def predict(self, x, y):
        n = self.n
        b = [self.gamma(dist(p[0], p[1], x, y)) for p in self.points] + [1.0]
        w = matvec(self.ainv, b)
        est = sum(w[i] * self.points[i][2] for i in range(n))
        var = sum(w[i] * b[i] for i in range(n)) + w[n]
        return est, math.sqrt(max(var, 0.0)), w[:n]

    def loo_residuals(self):
        """Dubrule shortcut: z_i - zhat_(-i) for every point."""
        n = self.n
        z = [p[2] for p in self.points] + [0.0]
        c = matvec(self.ainv, z)
        return [c[i] / self.ainv[i][i] for i in range(n)]


def kriging_loo_bruteforce(points, vario, scale=1.0):
    out = []
    for i in range(len(points)):
        rest = points[:i] + points[i + 1:]
        k = Kriging(rest, vario, scale)
        out.append(k.predict(points[i][0], points[i][1])[0])
    return out


def snapshot_scale(points):
    vals = [p[2] for p in points]
    s = std(vals)
    return max(s * s, 1.0)


def grid(points, method, nx, ny, w_km=C.MAP_W_KM, h_km=C.MAP_H_KM, vario=None):
    """Interpolate on an nx x ny grid of cell centres. Returns rows (south->north)."""
    vals, sds = [], []
    krig = Kriging(points, vario, snapshot_scale(points)) if method == "kriging" else None
    for j in range(ny):
        y = (j + 0.5) * h_km / ny
        rv, rs = [], []
        for i in range(nx):
            x = (i + 0.5) * w_km / nx
            if krig:
                e, s, _ = krig.predict(x, y)
                rv.append(round(max(0.0, e), 1))
                rs.append(round(s, 1))
            else:
                rv.append(round(idw(points, x, y), 1))
        vals.append(rv)
        sds.append(rs)
    return {"values": vals, "sd": sds if krig else None, "nx": nx, "ny": ny}
