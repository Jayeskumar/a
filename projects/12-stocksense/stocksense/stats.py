"""Small numeric toolkit written from scratch (no numpy).

- normal pdf / cdf (cdf via math.erfc from the standard library)
- inverse normal (Acklam's rational approximation + one Halley refinement step)
- standard normal loss function G(z) for expected shortage
- mean / std / linear-system solver (Gaussian elimination with partial pivoting)
"""
import math

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def std(xs, ddof=0):
    xs = list(xs)
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def norm_pdf(z):
    return math.exp(-0.5 * z * z) / SQRT2PI


def norm_cdf(z):
    # erfc keeps full precision in the lower tail (no 1 + (-1 + tiny) cancellation)
    return 0.5 * math.erfc(-z / SQRT2)


# Coefficients of Peter J. Acklam's algorithm (relative error < 1.15e-9 before refinement).
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)
_P_LOW = 0.02425


def inv_norm(p):
    """z such that P(Z <= z) = p for a standard normal Z. Valid for 0 < p < 1."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    elif p <= 1.0 - _P_LOW:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
            (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    # One step of Halley's method against the exact cdf polishes it to ~1e-15.
    e = norm_cdf(x) - p
    u = e * SQRT2PI * math.exp(0.5 * x * x)
    return x - u / (1.0 + 0.5 * x * u)


def norm_loss(z):
    """Standard normal loss G(z) = E[(Z - z)+] = pdf(z) - z * (1 - cdf(z))."""
    return norm_pdf(z) - z * (1.0 - norm_cdf(z))


def expected_shortage(stock, mu, sigma):
    """E[(D - stock)+] for D ~ Normal(mu, sigma)."""
    if sigma <= 1e-9:
        return max(0.0, mu - stock)
    return sigma * norm_loss((stock - mu) / sigma)


def prob_exceed(stock, mu, sigma):
    """P(D > stock) for D ~ Normal(mu, sigma)."""
    if sigma <= 1e-9:
        return 1.0 if mu > stock else 0.0
    return 1.0 - norm_cdf((stock - mu) / sigma)


def solve(a, b):
    """Solve a x = b (a: list of rows) by Gaussian elimination with partial pivoting."""
    n = len(a)
    m = [list(map(float, row)) + [float(b[i])] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        m[col], m[piv] = m[piv], m[col]
        pivot_row = m[col]
        inv = 1.0 / pivot_row[col]
        for r in range(col + 1, n):
            f = m[r][col] * inv
            if f:
                row = m[r]
                for c in range(col, n + 1):
                    row[c] -= f * pivot_row[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x
