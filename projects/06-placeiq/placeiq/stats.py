"""Descriptive statistics for the auto-EDA tab."""

import math


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def std(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def quantile(xs, q):
    """Linear-interpolated quantile (same convention as numpy's default)."""
    if not xs:
        return 0.0
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def summary(xs):
    return {
        "count": len(xs), "mean": mean(xs), "std": std(xs),
        "min": min(xs) if xs else 0, "q1": quantile(xs, 0.25), "median": quantile(xs, 0.5),
        "q3": quantile(xs, 0.75), "max": max(xs) if xs else 0,
    }


def histogram(xs, bins=12, integer=False):
    """Equal-width bins. Integer columns with a small range get one bin per value."""
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return [{"lo": lo, "hi": hi, "count": len(xs)}]
    if integer and hi - lo + 1 <= bins:
        out = []
        for v in range(int(lo), int(hi) + 1):
            out.append({"lo": v, "hi": v, "count": sum(1 for x in xs if x == v)})
        return out
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in xs:
        k = int((x - lo) / width)
        counts[min(k, bins - 1)] += 1
    return [{"lo": lo + i * width, "hi": lo + (i + 1) * width, "count": c} for i, c in enumerate(counts)]


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def correlation_matrix(columns):
    """columns: dict name -> list. Returns (names, matrix)."""
    names = list(columns)
    m = [[1.0 if i == j else None for j in range(len(names))] for i in range(len(names))]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = pearson(columns[names[i]], columns[names[j]])
            m[i][j] = m[j][i] = r
    return names, m
