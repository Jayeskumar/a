"""Multinomial Naive Bayes with Laplace smoothing, written from scratch.

Classes are integers 0 (ham / safe) and 1 (scam).  Documents are mappings
``feature -> count`` (counts may be fractional, e.g. weighted char n-grams).

    P(c | d)  oc  P(c) * prod_t P(t | c) ** n_t
    P(t | c)  =  (N_tc + alpha) / (N_c + alpha * |V|)

Explanations use the per-token log-likelihood ratio
    LLR(t) = log P(t | scam) - log P(t | ham)
multiplied by the token's count in the message.
"""
import math
from collections import Counter


class MultinomialNB:
    def __init__(self, alpha=1.0):
        self.alpha = float(alpha)
        self.class_docs = [0, 0]
        self.class_tokens = [0.0, 0.0]
        self.counts = [Counter(), Counter()]
        self.vocab = set()

    # ------------------------------------------------------------ training
    def fit(self, docs, labels):
        if len(docs) != len(labels):
            raise ValueError("docs and labels must have the same length")
        if not docs:
            raise ValueError("cannot fit on an empty corpus")
        for doc, y in zip(docs, labels):
            y = int(y)
            if y not in (0, 1):
                raise ValueError("labels must be 0 or 1")
            self.class_docs[y] += 1
            for f, n in doc.items():
                self.counts[y][f] += n
                self.class_tokens[y] += n
                self.vocab.add(f)
        return self

    # ---------------------------------------------------------- likelihoods
    def log_prior(self, c):
        total = self.class_docs[0] + self.class_docs[1]
        return math.log(self.class_docs[c] / total)

    def log_likelihood(self, feature, c):
        v = len(self.vocab)
        return math.log((self.counts[c].get(feature, 0.0) + self.alpha) /
                        (self.class_tokens[c] + self.alpha * v))

    def llr(self, feature):
        return self.log_likelihood(feature, 1) - self.log_likelihood(feature, 0)

    def joint_log(self, doc):
        """Unnormalised log P(c, d) for both classes. Unknown features are ignored."""
        out = []
        for c in (0, 1):
            s = self.log_prior(c)
            for f, n in doc.items():
                if f in self.vocab:
                    s += n * self.log_likelihood(f, c)
            out.append(s)
        return out

    def log_odds(self, doc):
        j0, j1 = self.joint_log(doc)
        return j1 - j0

    def predict_proba(self, doc):
        """Exact NB posterior P(scam | doc)."""
        return _sigmoid(self.log_odds(doc))

    def predict(self, doc):
        return 1 if self.log_odds(doc) > 0 else 0

    # --------------------------------------------------------- explanation
    def contributions(self, doc):
        """List of (feature, count, llr, count*llr) for known features."""
        rows = []
        for f, n in doc.items():
            if f in self.vocab:
                r = self.llr(f)
                rows.append((f, n, r, n * r))
        return rows

    def top_features(self, k=20, min_count=3):
        """Globally most indicative features for each class (by LLR)."""
        rows = []
        for f in self.vocab:
            if self.counts[0].get(f, 0) + self.counts[1].get(f, 0) >= min_count:
                rows.append((f, self.llr(f)))
        rows.sort(key=lambda r: r[1])
        return {"scam": rows[::-1][:k], "ham": rows[:k]}


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)
