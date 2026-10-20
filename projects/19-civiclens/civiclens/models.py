"""From-scratch classifiers on sparse vectors: Multinomial Naive Bayes and logistic regression.

Sparse vector = (indices tuple, values tuple). Labels are ints 0..K-1.
"""

import math
import random

from .features import dot


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logsumexp(xs):
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


class MultinomialNB:
    """P(c | d) ∝ P(c) * Π_j P(f_j | c)^{x_j},  P(f | c) = (N_cf + α) / (N_c + α V)."""

    def __init__(self, n_classes, n_features, alpha=1.0):
        self.K, self.V, self.alpha = n_classes, n_features, alpha
        self.log_prior, self.log_prob = [], []

    def fit(self, X, y):
        counts = [[0.0] * self.V for _ in range(self.K)]
        class_n = [0] * self.K
        for (idx, val), c in zip(X, y):
            class_n[c] += 1
            row = counts[c]
            for j, v in zip(idx, val):
                row[j] += v
        n = float(len(y))
        self.log_prior = [math.log((class_n[c] + 1.0) / (n + self.K)) for c in range(self.K)]
        self.log_prob = []
        for c in range(self.K):
            tot = sum(counts[c]) + self.alpha * self.V
            self.log_prob.append([math.log((x + self.alpha) / tot) for x in counts[c]])
        self.class_n = class_n
        return self

    def joint_log(self, x):
        return [self.log_prior[c] + dot(self.log_prob[c], x) for c in range(self.K)]

    def predict_proba(self, x):
        jl = self.joint_log(x)
        lse = logsumexp(jl)
        return [math.exp(v - lse) for v in jl]

    def predict(self, x):
        jl = self.joint_log(x)
        return max(range(self.K), key=jl.__getitem__)

    def top_features(self, c, names, k=10, prefix="w:"):
        """Features most indicative of class c: log P(f|c) - mean over other classes."""
        others = [o for o in range(self.K) if o != c]
        scores = []
        for j, nm in enumerate(names):
            if not nm.startswith(prefix):
                continue
            rest = sum(self.log_prob[o][j] for o in others) / len(others)
            scores.append((self.log_prob[c][j] - rest, nm))
        scores.sort(reverse=True)
        return [(nm, s) for s, nm in scores[:k]]


class LogisticRegression:
    """Binary logistic regression trained by SGD on log-loss with L2 (lazy, on touched weights).

    Learning rate decays as lr / (1 + t / n): roughly halves after the first epoch.
    """

    def __init__(self, n_features, epochs=8, lr=0.5, l2=1e-5, seed=0, pos_weight=1.0):
        self.n, self.epochs, self.lr, self.l2, self.seed = n_features, epochs, lr, l2, seed
        self.pos_weight = pos_weight
        self.w, self.b, self.loss_history = [0.0] * n_features, 0.0, []

    def fit(self, X, y):
        w, b = self.w, self.b
        rng = random.Random(self.seed)
        order = list(range(len(X)))
        n = float(max(1, len(X)))
        t = 0
        lr0, l2 = self.lr, self.l2
        for _ in range(self.epochs):
            rng.shuffle(order)
            loss = 0.0
            for i in order:
                idx, val = X[i]
                z = b + (sum(map(float.__mul__, map(w.__getitem__, idx), val)) if idx else 0.0)
                p = sigmoid(z)
                yi = y[i]
                sw = self.pos_weight if yi == 1 else 1.0
                loss -= sw * (math.log(p + 1e-12) if yi == 1 else math.log(1.0 - p + 1e-12))
                eta = lr0 / (1.0 + t / n)
                t += 1
                g = (p - yi) * sw * eta
                if g == 0.0:
                    continue
                shrink = 1.0 - eta * l2
                for j, v in zip(idx, val):
                    w[j] = w[j] * shrink - g * v
                b -= g
            self.loss_history.append(loss / n)
        self.b = b
        return self

    def decision(self, x):
        return self.b + dot(self.w, x)

    def predict_proba(self, x):
        return sigmoid(self.decision(x))

    def contributions(self, x):
        idx, val = x
        return [(j, self.w[j] * v) for j, v in zip(idx, val)]


class OneVsRest:
    """K binary logistic regressions; class scores normalised to sum to 1."""

    def __init__(self, n_classes, n_features, **kw):
        self.K, self.V, self.kw = n_classes, n_features, kw
        self.models = []

    def fit(self, X, y):
        self.models = []
        for c in range(self.K):
            yc = [1 if v == c else 0 for v in y]
            kw = dict(self.kw)
            kw["seed"] = kw.get("seed", 0) + c
            self.models.append(LogisticRegression(self.V, **kw).fit(X, yc))
        return self

    def raw_proba(self, x):
        return [m.predict_proba(x) for m in self.models]

    def predict_proba(self, x):
        p = self.raw_proba(x)
        s = sum(p) or 1.0
        return [v / s for v in p]

    def predict(self, x):
        p = self.raw_proba(x)
        return max(range(self.K), key=p.__getitem__)

    def top_features(self, c, names, k=10, prefix="w:"):
        w = self.models[c].w
        cand = [(w[j], nm) for j, nm in enumerate(names) if nm.startswith(prefix)]
        cand.sort(reverse=True)
        return [(nm, s) for s, nm in cand[:k]]
