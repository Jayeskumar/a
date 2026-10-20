"""Topic discovery for "Other" complaints: spherical k-means on TF-IDF concept vectors.

Vectors are dicts term -> weight, L2-normalised, so cosine similarity is a dot product.
k-means++ seeding, a few restarts (best inertia wins) and silhouette to compare k.
"""

import math
import random

# place names and landmark types say *where*, not *what*; leave them out of topic vectors
PLACE_CONCEPTS = {
    "temple", "school", "bus", "stand", "stop", "busstop", "busstand", "ration", "shop", "rationshop", "tank",
    "watertank", "park", "hospital", "market", "street", "junction", "community", "hall", "communityhall",
    "nagar", "cross", "road", "murugan", "vinayagar", "mariamman", "perumal", "gandhi", "nehru", "anna",
    "kamarajar", "periyar", "bharathi", "valluvar", "kannagi", "kaveri", "ambedkar", "rajaji", "indira",
    "thiruvika", "lake", "industrial", "pudhupalayam", "college", "railway", "mettu", "voc", "estate",
    "colony", "view", "new", "old", "boys", "girls", "block", "also", "problem",
    # generic words that say nothing about the topic
    "no", "not", "notworking", "public",
}


def tfidf_dicts(token_lists, min_df=2):
    df = {}
    for toks in token_lists:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n = len(token_lists)
    idf = {t: math.log((1.0 + n) / (1.0 + c)) + 1.0 for t, c in df.items() if c >= min_df}
    out = []
    for toks in token_lists:
        tf = {}
        for t in toks:
            if t in idf:
                tf[t] = tf.get(t, 0) + 1
        v = {t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items()}
        out.append(normalize(v))
    return out, idf


def normalize(v):
    nrm = math.sqrt(sum(x * x for x in v.values()))
    return {k: x / nrm for k, x in v.items()} if nrm else {}


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


def _mean(vecs):
    acc = {}
    for v in vecs:
        for k, x in v.items():
            acc[k] = acc.get(k, 0.0) + x
    return normalize(acc)


def kmeans(vecs, k, seed=0, restarts=4, max_iter=40):
    """Returns (labels, centroids, inertia) where inertia = sum(1 - cos(x, centroid))."""
    best = None
    n = len(vecs)
    if n == 0:
        return [], [], 0.0
    k = max(1, min(k, n))
    for r in range(restarts):
        rng = random.Random(seed * 1000 + r)
        cents = [vecs[rng.randrange(n)]]
        while len(cents) < k:                                  # k-means++ on cosine distance
            d2 = [min(1.0 - cos(v, c) for c in cents) ** 2 for v in vecs]
            tot = sum(d2)
            if tot <= 0:
                cents.append(vecs[rng.randrange(n)])
                continue
            u, acc = rng.random() * tot, 0.0
            for i, d in enumerate(d2):
                acc += d
                if acc >= u:
                    cents.append(vecs[i])
                    break
        labels = [-1] * n
        for _ in range(max_iter):
            new = [max(range(k), key=lambda c: cos(v, cents[c])) for v in vecs]
            if new == labels:
                break
            labels = new
            for c in range(k):
                mem = [vecs[i] for i in range(n) if labels[i] == c]
                if mem:
                    cents[c] = _mean(mem)
        inertia = sum(1.0 - cos(vecs[i], cents[labels[i]]) for i in range(n))
        if best is None or inertia < best[2] - 1e-9:
            best = (labels, cents, inertia)
    return best


def silhouette(vecs, labels):
    """Mean silhouette with cosine distance (1 - cos)."""
    n = len(vecs)
    ks = sorted(set(labels))
    if n < 3 or len(ks) < 2:
        return 0.0
    members = {c: [i for i in range(n) if labels[i] == c] for c in ks}
    total = 0.0
    for i in range(n):
        own = labels[i]
        dists = {}
        for c in ks:
            mem = [j for j in members[c] if j != i]
            if not mem:
                continue
            dists[c] = sum(1.0 - cos(vecs[i], vecs[j]) for j in mem) / len(mem)
        if own not in dists or len(members[own]) <= 1:
            continue
        a = dists[own]
        b = min(v for c, v in dists.items() if c != own) if len(dists) > 1 else 0.0
        total += (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return total / n


def top_terms(centroid, k=6):
    return [t for t, _ in sorted(centroid.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def purity(labels, truth):
    groups = {}
    for l, t in zip(labels, truth):
        groups.setdefault(l, {}).setdefault(t, 0)
        groups[l][t] += 1
    return sum(max(g.values()) for g in groups.values()) / float(len(labels)) if labels else 0.0
