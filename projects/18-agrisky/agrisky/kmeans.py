"""k-means clustering from scratch (k-means++ seeding, Lloyd iterations, restarts).

    repeat until no centroid moves more than tol (or labels stop changing):
        assign every point to its nearest centroid          (squared Euclidean)
        move every centroid to the mean of its points
    keep the restart with the lowest inertia (sum of squared distances)

Features are z-scored first so NDVI, NDRE, NDWI and SAVI weigh equally. For speed the
centroids are fitted on a regular grid sample of the field and then every cell is labelled.
"""
import random


def standardize(columns):
    """columns: list of equal-length feature lists -> (z-scored rows, means, stds)."""
    n = len(columns[0])
    means, stds = [], []
    for col in columns:
        m = sum(col) / n
        var = sum((v - m) ** 2 for v in col) / n
        means.append(m)
        stds.append(var ** 0.5 or 1.0)
    rows = [tuple((columns[j][i] - means[j]) / stds[j] for j in range(len(columns)))
            for i in range(n)]
    return rows, means, stds


def _sqdist(a, b):
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return s


def nearest(point, centroids):
    best, bd = 0, float("inf")
    for j, c in enumerate(centroids):
        d = _sqdist(point, c)
        if d < bd:
            best, bd = j, d
    return best, bd


def kmeans_pp_init(points, k, rng):
    """k-means++: first centre uniform, next ones with probability proportional to D^2."""
    centroids = [points[rng.randrange(len(points))]]
    d2 = [_sqdist(p, centroids[0]) for p in points]
    while len(centroids) < k:
        total = sum(d2)
        if total <= 0:
            centroids.append(points[rng.randrange(len(points))])
            continue
        r = rng.random() * total
        acc = 0.0
        pick = len(points) - 1
        for i, w in enumerate(d2):
            acc += w
            if acc >= r:
                pick = i
                break
        c = points[pick]
        centroids.append(c)
        for i, p in enumerate(points):
            d = _sqdist(p, c)
            if d < d2[i]:
                d2[i] = d
    return [tuple(c) for c in centroids]


def assign(points, centroids):
    """Nearest-centroid labels and total inertia (inlined fast path for 2-4 features)."""
    labels = [0] * len(points)
    inertia = 0.0
    dim = len(centroids[0]) if centroids else 0
    if 2 <= dim <= 4:
        cs = list(enumerate(tuple(c) + (0.0,) * (4 - dim) for c in centroids))
        pad = (0.0,) * (4 - dim)
        for i, p in enumerate(points):
            a0, a1, a2, a3 = tuple(p) + pad if dim < 4 else p
            best, bd = 0, 1e300
            for j, (c0, c1, c2, c3) in cs:
                d0 = a0 - c0
                d1 = a1 - c1
                d2 = a2 - c2
                d3 = a3 - c3
                d = d0 * d0 + d1 * d1 + d2 * d2 + d3 * d3
                if d < bd:
                    best, bd = j, d
            labels[i] = best
            inertia += bd
        return labels, inertia
    for i, p in enumerate(points):
        j, d = nearest(p, centroids)
        labels[i] = j
        inertia += d
    return labels, inertia


def lloyd(points, centroids, max_iter=60, tol=1e-5):
    """Run Lloyd iterations from given centroids. Returns dict with history."""
    k = len(centroids)
    dim = len(points[0])
    labels = None
    history = []
    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        new_labels, inertia = assign(points, centroids)
        history.append(inertia)
        sums = [[0.0] * dim for _ in range(k)]
        counts = [0] * k
        for p, j in zip(points, new_labels):
            counts[j] += 1
            s = sums[j]
            for d in range(dim):
                s[d] += p[d]
        new_c = []
        shift = 0.0
        for j in range(k):
            if counts[j]:
                c = tuple(s / counts[j] for s in sums[j])
            else:                         # empty cluster: re-seed at the worst-fitted point
                far = max(range(len(points)),
                          key=lambda i: _sqdist(points[i], centroids[new_labels[i]]))
                c = points[far]
            shift = max(shift, _sqdist(c, centroids[j]) ** 0.5)
            new_c.append(c)
        same = labels is not None and new_labels == labels
        centroids, labels = new_c, new_labels
        if shift <= tol or same:
            converged = True
            break
    labels, inertia = assign(points, centroids)
    history.append(inertia)
    return {"centroids": centroids, "labels": labels, "inertia": inertia,
            "iterations": it, "converged": converged, "history": history}


def kmeans(points, k, seed=0, n_init=3, max_iter=60, tol=1e-5):
    """Best of n_init k-means++ restarts (deterministic for a given seed)."""
    if k < 1 or k > len(points):
        raise ValueError("k must be between 1 and the number of points")
    rng = random.Random(seed)
    best = None
    for _ in range(max(1, n_init)):
        init = kmeans_pp_init(points, k, rng)
        res = lloyd(points, init, max_iter, tol)
        if best is None or res["inertia"] < best["inertia"]:
            best = res
    return best
