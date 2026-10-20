"""Small from-scratch numerics: statistics, linear algebra, geometry, a seeded RNG helper."""

import math


# ------------------------------------------------------------------ statistics
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def median(xs):
    s = sorted(x for x in xs if x is not None)
    n = len(s)
    if not n:
        return None
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def percentile(xs, q):
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(x for x in xs if x is not None)
    if not s:
        return None
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def mad(xs, centre=None):
    """Median absolute deviation (unscaled)."""
    vals = [x for x in xs if x is not None]
    if not vals:
        return None
    c = median(vals) if centre is None else centre
    return median([abs(x - c) for x in vals])


def robust_sigma(xs):
    m = mad(xs)
    return None if m is None else 1.4826 * m


def std(xs):
    vals = [x for x in xs if x is not None]
    if len(vals) < 2:
        return 0.0
    mu = sum(vals) / len(vals)
    return math.sqrt(sum((x - mu) ** 2 for x in vals) / (len(vals) - 1))


def errors(pred, truth):
    """MAE, RMSE, bias and R^2 over pairs where both values exist."""
    pairs = [(p, t) for p, t in zip(pred, truth) if p is not None and t is not None]
    if not pairs:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "r2": None}
    n = len(pairs)
    mae = sum(abs(p - t) for p, t in pairs) / n
    rmse = math.sqrt(sum((p - t) ** 2 for p, t in pairs) / n)
    bias = sum(p - t for p, t in pairs) / n
    mt = sum(t for _, t in pairs) / n
    sst = sum((t - mt) ** 2 for _, t in pairs)
    sse = sum((p - t) ** 2 for p, t in pairs)
    r2 = 1 - sse / sst if sst > 0 else None
    return {"n": n, "mae": mae, "rmse": rmse, "bias": bias, "r2": r2}


# ------------------------------------------------------------------ linear algebra
def solve(a, b):
    """Solve A x = b by Gaussian elimination with partial pivoting (A is n x n)."""
    n = len(a)
    m = [list(map(float, row)) + [float(bv)] for row, bv in zip(a, b)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        if piv != col:
            m[col], m[piv] = m[piv], m[col]
        pr = m[col]
        inv = 1.0 / pr[col]
        for r in range(col + 1, n):
            row = m[r]
            f = row[col] * inv
            if f:
                for c in range(col, n + 1):
                    row[c] -= f * pr[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x


def inverse(a):
    """Gauss-Jordan inverse with partial pivoting."""
    n = len(a)
    m = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(n)]
         for i, row in enumerate(a)]
    w = 2 * n
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        m[col], m[piv] = m[piv], m[col]
        pr = m[col]
        inv = 1.0 / pr[col]
        for c in range(w):
            pr[c] *= inv
        for r in range(n):
            if r != col:
                row = m[r]
                f = row[col]
                if f:
                    for c in range(w):
                        row[c] -= f * pr[c]
    return [row[n:] for row in m]


def matvec(a, v):
    return [sum(x * y for x, y in zip(row, v)) for row in a]


def least_squares(rows, y, ridge=0.0, weights=None):
    """Ridge least squares with intercept. rows: list of feature lists.

    Features are standardised internally (intercept not penalised); returns
    {"intercept": b0, "coef": [b1..bk]} in the original feature units.
    """
    n = len(rows)
    if n == 0:
        raise ValueError("no training rows")
    k = len(rows[0])
    w = weights or [1.0] * n
    sw = sum(w)
    mu = [sum(w[i] * rows[i][j] for i in range(n)) / sw for j in range(k)]
    sd = []
    for j in range(k):
        v = sum(w[i] * (rows[i][j] - mu[j]) ** 2 for i in range(n)) / sw
        sd.append(math.sqrt(v) if v > 1e-12 else 1.0)
    ym = sum(w[i] * y[i] for i in range(n)) / sw
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for i in range(n):
        z = [(rows[i][j] - mu[j]) / sd[j] for j in range(k)]
        wi = w[i]
        yi = (y[i] - ym) * wi
        for a in range(k):
            za = z[a] * wi
            xty[a] += z[a] * yi
            ra = xtx[a]
            for b in range(a, k):
                ra[b] += za * z[b]
    for a in range(k):
        for b in range(a):
            xtx[a][b] = xtx[b][a]
        xtx[a][a] += ridge * sw
    beta_z = solve(xtx, xty)
    coef = [beta_z[j] / sd[j] for j in range(k)]
    intercept = ym - sum(coef[j] * mu[j] for j in range(k))
    return {"intercept": intercept, "coef": coef}


def predict(model, feats):
    return model["intercept"] + sum(c * f for c, f in zip(model["coef"], feats))


# ------------------------------------------------------------------ geometry (km)
def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def bearing_deg(ax, ay, bx, by):
    """Compass bearing from A to B in degrees (0 = north, 90 = east)."""
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360.0


def angle_diff(a, b):
    """Smallest absolute difference between two angles in degrees."""
    d = (a - b) % 360.0
    return d if d <= 180 else 360.0 - d


def point_segment(px, py, ax, ay, bx, by):
    """Distance from P to segment AB and the foot point."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    fx, fy = ax + t * dx, ay + t * dy
    return math.hypot(px - fx, py - fy), fx, fy


def point_polyline(px, py, pts):
    best = (float("inf"), 0.0, 0.0)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        d = point_segment(px, py, ax, ay, bx, by)
        if d[0] < best[0]:
            best = d
    return best


COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(deg):
    return COMPASS16[int(((deg % 360) + 11.25) // 22.5) % 16]
