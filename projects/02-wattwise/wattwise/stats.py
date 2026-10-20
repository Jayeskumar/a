"""Small numeric helpers written from scratch (no numpy)."""

import math


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def mad(xs, med=None):
    """Median absolute deviation (unscaled)."""
    if med is None:
        med = median(xs)
    return median([abs(x - med) for x in xs])


def percentile(xs, q):
    """Linear-interpolated percentile, q in [0, 1]."""
    s = sorted(xs)
    if not s:
        return 0.0
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def solve(a, b):
    """Solve A x = b by Gaussian elimination with partial pivoting.

    ``a`` is a list of rows (it is copied, not modified). Raises ValueError for
    a singular matrix.
    """
    n = len(a)
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        rowc = m[col]
        for r in range(col + 1, n):
            f = m[r][col] / pv
            if f != 0.0:
                rowr = m[r]
                for c in range(col, n + 1):
                    rowr[c] -= f * rowc[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x


def mape(actual, predicted, floor=0.5):
    """Mean absolute percentage error in %, ignoring actuals below ``floor``."""
    errs = [abs(a - p) / a for a, p in zip(actual, predicted) if a >= floor]
    return 100.0 * mean(errs) if errs else 0.0


def wape(actual, predicted):
    """Weighted absolute percentage error in % (sum|e| / sum|a|)."""
    den = sum(abs(a) for a in actual)
    return 100.0 * sum(abs(a - p) for a, p in zip(actual, predicted)) / den if den else 0.0
