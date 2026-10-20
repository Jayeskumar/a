"""Gaussian Naive Bayes, from scratch.

    log P(c | x) = log P(c) + sum_f log N(x_f; mu_cf, var_cf) - log Z

Variances get a small smoothing term (like scikit-learn's var_smoothing) so a feature that
is constant inside one class cannot produce a zero variance.
"""
import math

LOG_2PI = math.log(2 * math.pi)


class GaussianNB:
    def __init__(self, var_smoothing=1e-9):
        self.var_smoothing = var_smoothing
        self.classes = []
        self.priors = {}
        self.means = {}
        self.vars = {}

    def fit(self, X, y):
        if not X or len(X) != len(y):
            raise ValueError("X and y must be non-empty and of equal length")
        n_feat = len(X[0])
        # epsilon proportional to the largest overall feature variance (sklearn convention)
        overall = []
        for f in range(n_feat):
            col = [r[f] for r in X]
            m = sum(col) / len(col)
            overall.append(sum((v - m) ** 2 for v in col) / len(col))
        eps = self.var_smoothing * max(overall + [1e-12])
        groups = {}
        for row, label in zip(X, y):
            groups.setdefault(label, []).append(row)
        self.classes = sorted(groups)
        n = float(len(X))
        for c in self.classes:
            rows = groups[c]
            self.priors[c] = len(rows) / n
            mu, var = [], []
            for f in range(n_feat):
                col = [r[f] for r in rows]
                m = sum(col) / len(col)
                mu.append(m)
                var.append(sum((v - m) ** 2 for v in col) / len(col) + eps)
            self.means[c] = mu
            self.vars[c] = var
        return self

    def feature_log_likelihood(self, c, f, value):
        """log N(value; mu_cf, var_cf) for one class/feature."""
        var = self.vars[c][f]
        d = value - self.means[c][f]
        return -0.5 * (LOG_2PI + math.log(var) + d * d / var)

    def joint_log_likelihood(self, x):
        out = {}
        for c in self.classes:
            s = math.log(self.priors[c])
            for f, v in enumerate(x):
                s += self.feature_log_likelihood(c, f, v)
            out[c] = s
        return out

    def predict_proba(self, x):
        jll = self.joint_log_likelihood(x)
        mx = max(jll.values())
        exps = {c: math.exp(v - mx) for c, v in jll.items()}   # log-sum-exp for stability
        z = sum(exps.values())
        return {c: e / z for c, e in exps.items()}

    def predict(self, x):
        p = self.predict_proba(x)
        return max(p, key=p.get)

    def explain(self, x, top, versus):
        """Per-feature log-likelihood contribution of `top` over `versus`.

        Sum of the returned feature deltas + prior delta = log-odds(top vs versus).
        Positive = this input pushed the decision towards `top`.
        """
        deltas = []
        for f, v in enumerate(x):
            deltas.append(self.feature_log_likelihood(top, f, v)
                          - self.feature_log_likelihood(versus, f, v))
        prior_delta = math.log(self.priors[top]) - math.log(self.priors[versus])
        return deltas, prior_delta
