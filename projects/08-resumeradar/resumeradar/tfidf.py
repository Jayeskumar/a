"""TF-IDF vectors and cosine similarity, from scratch.

    tf(t, d)  = 1 + ln(count(t, d))                      (sublinear term frequency)
    idf(t)    = ln((1 + N) / (1 + df(t))) + 1            (smoothed inverse document frequency)
    w(t, d)   = tf * idf, then the vector is L2-normalised
    cos(a, b) = sum_t a[t] * b[t]                        (both unit length)

Documents are "skill-aware": every detected skill adds a canonical token such as
"skill:javascript", so "JS" in a resume and "JavaScript" in a JD share a dimension.
"""
import math
from collections import Counter

from .text import content_terms


def doc_terms(text, skills=None):
    terms = content_terms(text)
    if skills:
        for sid, info in skills.items():
            terms.extend(["skill:" + sid] * int(info.get("count", 1)))
    return terms


class TfidfModel(object):
    def __init__(self):
        self.df = Counter()
        self.n = 0

    def add(self, terms):
        self.n += 1
        self.df.update(set(terms))
        return self

    def fit(self, docs):
        for d in docs:
            self.add(d)
        return self

    def copy(self):
        m = TfidfModel()
        m.df = Counter(self.df)
        m.n = self.n
        return m

    def idf(self, term):
        return math.log((1.0 + self.n) / (1.0 + self.df.get(term, 0))) + 1.0

    def vector(self, terms):
        tf = Counter(terms)
        vec = {t: (1.0 + math.log(c)) * self.idf(t) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm == 0:
            return {}
        return {t: v / norm for t, v in vec.items()}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def top_contributions(a, b, k=8):
    """Terms contributing most to cos(a, b), as [(term, contribution)]."""
    if len(a) > len(b):
        a, b = b, a
    contrib = [(t, v * b[t]) for t, v in a.items() if t in b]
    contrib.sort(key=lambda x: (-x[1], x[0]))
    return contrib[:k]
