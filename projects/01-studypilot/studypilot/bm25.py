"""Okapi BM25 retrieval from scratch, with per-term score contributions.

score(D, Q) = Σ_{t in Q} IDF(t) * tf(t,D) * (k1 + 1) / (tf(t,D) + k1 * (1 - b + b * |D| / avgdl))
IDF(t)      = ln(1 + (N - n(t) + 0.5) / (n(t) + 0.5))      (always positive)
"""
import math
from collections import Counter

K1 = 1.5   # term-frequency saturation (common default range 1.2-2.0)
B = 0.75   # length normalisation (Robertson & Zaragoza default)


class BM25:
    def __init__(self, docs, k1=K1, b=B):
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in docs]
        self.lengths = [len(d) for d in docs]
        self.n = len(docs)
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.df = df

    def idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.n - n + 0.5) / (n + 0.5))

    def score(self, i, q_terms):
        """Return (score, contributions) for document i."""
        d = self.docs[i]
        dl = self.lengths[i]
        total, contrib = 0.0, {}
        for t in dict.fromkeys(q_terms):  # unique, order preserved
            tf = d.get(t, 0)
            if not tf:
                continue
            idf = self.idf(t)
            norm = 1 - self.b + self.b * (dl / self.avgdl if self.avgdl else 0)
            c = idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
            contrib[t] = {"tf": tf, "idf": round(idf, 4), "score": round(c, 4)}
            total += c
        return total, contrib

    def search(self, q_terms, k=5):
        results = []
        for i in range(self.n):
            s, contrib = self.score(i, q_terms)
            if s > 0:
                results.append({"index": i, "score": s, "contributions": contrib})
        results.sort(key=lambda r: (-r["score"], r["index"]))
        return results[:k]

    def query_idf_mass(self, q_terms):
        return sum(self.idf(t) for t in dict.fromkeys(q_terms))
