"""Duplicate detection: MinHash + LSH banding on concept shingles, then geo + time checks.

MinHash: for k random hash functions h_i(x) = (a_i x + b_i) mod p, the signature of a set S
is (min_{x in S} h_i(x))_i, and P[sig_i(A) == sig_i(B)] = Jaccard(A, B). LSH cuts the signature
into b bands of r rows; two sets become *candidates* if any band matches, with probability
1 - (1 - s^r)^b - a steep S-curve around s ~ (1/b)^(1/r).
"""

import hashlib
import math
import random

from . import config as C

MERSENNE = (1 << 61) - 1
_HCACHE = {}


def stable_hash(s):
    """Process-independent 61-bit hash (Python's hash() is salted per run)."""
    h = _HCACHE.get(s)
    if h is None:
        h = int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little") % MERSENNE
        if len(_HCACHE) < 200000:
            _HCACHE[s] = h
    return h


class MinHasher:
    def __init__(self, n_perm=C.MINHASH_PERM, seed=1):
        rng = random.Random(seed)
        self.n = n_perm
        self.ab = [(rng.randrange(1, MERSENNE), rng.randrange(0, MERSENNE)) for _ in range(n_perm)]

    def signature(self, shingle_set):
        if not shingle_set:
            return None
        hs = [stable_hash(s) for s in shingle_set]
        P = MERSENNE
        return tuple(min((a * h + b) % P for h in hs) for a, b in self.ab)

    @staticmethod
    def similarity(s1, s2):
        if s1 is None or s2 is None:
            return 0.0
        return sum(1 for x, y in zip(s1, s2) if x == y) / float(len(s1))


class LSHIndex:
    """Banded LSH. An optional *tag* (e.g. a geo cell) is part of every bucket key, so only items
    with the same tag can collide; ``query`` takes the tags to look in."""

    def __init__(self, bands=C.LSH_BANDS, rows=C.LSH_ROWS):
        self.b, self.r = bands, rows
        self.buckets = [dict() for _ in range(bands)]

    def _keys(self, sig):
        r = self.r
        return [sig[i * r:(i + 1) * r] for i in range(self.b)]

    def add(self, item, sig, tag=None):
        if sig is None:
            return
        for band, key in zip(self.buckets, self._keys(sig)):
            band.setdefault((key, tag), []).append(item)

    def query(self, sig, tags=(None,)):
        out = set()
        if sig is None:
            return out
        keys = self._keys(sig)
        for tag in tags:
            for band, key in zip(self.buckets, keys):
                out.update(band.get((key, tag), ()))
        return out

    def candidate_pairs(self):
        pairs = set()
        for band in self.buckets:
            for members in band.values():
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        a, b = members[i], members[j]
                        pairs.add((a, b) if a < b else (b, a))
        return pairs

    @staticmethod
    def probability(s, bands=C.LSH_BANDS, rows=C.LSH_ROWS):
        return 1.0 - (1.0 - s ** rows) ** bands


def geo_cell(lat, lon, size_m=C.DUP_GEO_CELL_M):
    return (int(math.floor(lat * 110574.0 / size_m)), int(math.floor(lon * 109020.0 / size_m)))


def neighbour_cells(cell):
    a, b = cell
    return [(a + i, b + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            self.p[rb] = ra      # the earliest complaint stays the root
        return ra


def pair_score(jac, dist_m, gap_days, max_dist=C.DUP_MAX_DIST_M, max_gap=C.DUP_MAX_GAP_DAYS,
               weights=C.DUP_SCORE_WEIGHTS):
    wj, wg, wt = weights
    return wj * jac + wg * max(0.0, 1.0 - dist_m / max_dist) + wt * max(0.0, 1.0 - gap_days / max_gap)


class DuplicateDetector:
    """Streaming detector. Items are dicts with keys t, lat, lon, dept, closed_t, shingles."""

    def __init__(self, threshold=C.DUP_SCORE_THRESHOLD, min_jaccard=C.DUP_MIN_JACCARD,
                 max_dist=C.DUP_MAX_DIST_M, max_gap=C.DUP_MAX_GAP_DAYS, hasher=None):
        self.threshold, self.min_jaccard = threshold, min_jaccard
        self.max_dist, self.max_gap = max_dist, max_gap
        self.hasher = hasher or MinHasher()
        self.lsh = LSHIndex()
        self.items, self.sigs = [], []
        self.uf = UnionFind(0)
        self.n_candidates = 0

    def evaluate(self, a, b, sig_a=None, sig_b=None):
        """Explain the comparison of a new item a with an earlier item b."""
        sa = sig_a if sig_a is not None else self.hasher.signature(a["shingles"])
        sb = sig_b if sig_b is not None else self.hasher.signature(b["shingles"])
        jac = MinHasher.similarity(sa, sb)
        dist = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        gap = a["t"] - b["t"]
        score = pair_score(jac, dist, gap, self.max_dist, self.max_gap)
        reasons = []
        still_open = b.get("closed_t") is None or b["closed_t"] > a["t"]
        same_dept = a["dept"] == b["dept"] or jac >= 0.6
        ok = (still_open and same_dept and dist <= self.max_dist and 0 <= gap <= self.max_gap
              and jac >= self.min_jaccard and score >= self.threshold)
        if not still_open:
            reasons.append("earlier complaint already resolved")
        if not same_dept:
            reasons.append("different department")
        if dist > self.max_dist:
            reasons.append("%.0f m apart" % dist)
        if gap > self.max_gap:
            reasons.append("%.1f days apart" % gap)
        return {"jaccard": round(jac, 3), "dist_m": round(dist, 1), "gap_days": round(gap, 3),
                "score": round(score, 3), "duplicate": ok, "rejected_because": reasons}

    def add(self, item, record=True):
        """Match item against earlier items; returns (best_match_index or None, details, candidates)."""
        sig = self.hasher.signature(item["shingles"])
        cell = geo_cell(item["lat"], item["lon"])
        cands = self.lsh.query(sig, neighbour_cells(cell))
        self.n_candidates += len(cands)
        best, best_d = None, None
        for j in cands:
            d = self.evaluate(item, self.items[j], sig, self.sigs[j])
            if d["duplicate"] and (best_d is None or d["score"] > best_d["score"]):
                best, best_d = j, d
        if record:
            k = len(self.items)
            self.items.append(item)
            self.sigs.append(sig)
            self.uf.p.append(k)
            self.lsh.add(k, sig, cell)
            if best is not None:
                self.uf.union(best, k)
        return best, best_d, cands

    def root(self, k):
        return self.uf.find(k)


def run_stream(items, **kw):
    """Run the detector over items (already sorted by time). Returns (detector, matches)."""
    det = DuplicateDetector(**kw)
    matches = []
    for it in items:
        best, d, _ = det.add(it)
        matches.append((best, d))
    return det, matches


# ----------------------------------------------------------------------------- learned pair scorer
PAIR_FEATURES = ["text similarity (MinHash)", "geo closeness", "time closeness", "text x geo", "geo x time"]


def pair_features(jac, dist_m, gap_days, max_dist=C.DUP_MAX_DIST_M, max_gap=C.DUP_MAX_GAP_DAYS):
    g = max(0.0, 1.0 - dist_m / max_dist)
    t = max(0.0, 1.0 - gap_days / max_gap)
    return (0, 1, 2, 3, 4), (jac, g, t, jac * g, g * t)


class PairScorer:
    """Logistic regression on (text, geo, time) features of a candidate pair -> P(same incident)."""

    def __init__(self, epochs=40, lr=0.3, l2=1e-4, seed=3):
        from .models import LogisticRegression
        self.model = LogisticRegression(len(PAIR_FEATURES), epochs=epochs, lr=lr, l2=l2, seed=seed)

    def fit(self, rows, labels):
        """rows: [(jaccard, dist_m, gap_days)], labels: 0/1."""
        self.model.fit([pair_features(*r) for r in rows], labels)
        return self

    def prob(self, jac, dist_m, gap_days):
        return self.model.predict_proba(pair_features(jac, dist_m, gap_days))

    def explain(self, jac, dist_m, gap_days):
        idx, val = pair_features(jac, dist_m, gap_days)
        return [{"feature": PAIR_FEATURES[i], "value": round(v, 3), "contribution": round(self.model.w[i] * v, 3)}
                for i, v in zip(idx, val)]

    def weights(self):
        return {"bias": round(self.model.b, 3),
                **{PAIR_FEATURES[i]: round(w, 3) for i, w in enumerate(self.model.w)}}
