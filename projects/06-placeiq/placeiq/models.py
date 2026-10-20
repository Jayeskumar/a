"""From-scratch models: standard scaler, logistic regression (batch gradient descent
with L2), ridge linear regression (normal equations + Gaussian elimination) and
deterministic data splitting helpers. Pure Python lists, no numpy."""

import math
import random


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class StandardScaler:
    """z = (x - mean) / std, column-wise. Constant columns get std = 1."""

    def fit(self, X):
        n, d = len(X), len(X[0])
        self.mean = [sum(r[j] for r in X) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((r[j] - self.mean[j]) ** 2 for r in X) / n
            s = math.sqrt(var)
            self.std.append(s if s > 1e-12 else 1.0)
        return self

    def transform_row(self, x):
        return [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]

    def transform(self, X):
        return [self.transform_row(r) for r in X]

    def to_dict(self):
        return {"mean": self.mean, "std": self.std}


class LogisticRegression:
    """Binary logistic regression trained by full-batch gradient descent.

    Loss  L(w,b) = -1/n * sum[y log p + (1-y) log(1-p)] + lambda/2 * ||w||^2
    Grad  dL/dw  =  1/n * X^T (p - y) + lambda * w ;  dL/db = mean(p - y)
    The bias is not penalised. Stops when max |gradient| < tol or after max_iter.
    """

    def __init__(self, lr=0.5, l2=0.01, max_iter=3000, tol=1e-6):
        self.lr, self.l2, self.max_iter, self.tol = lr, l2, max_iter, tol
        self.w, self.b = None, 0.0
        self.n_iter, self.loss_history = 0, []

    def fit(self, X, y):
        n, d = len(X), len(X[0])
        w, b = [0.0] * d, 0.0
        cols = list(zip(*X))  # column-major copy for fast dot products
        self.loss_history = []
        for it in range(1, self.max_iter + 1):
            z = [b] * n
            for j in range(d):
                wj = w[j]
                if wj:
                    cj = cols[j]
                    z = [zi + wj * xij for zi, xij in zip(z, cj)]
            p = [sigmoid(zi) for zi in z]
            err = [pi - yi for pi, yi in zip(p, y)]
            gb = sum(err) / n
            gw = [sum(e * x for e, x in zip(err, cols[j])) / n + self.l2 * w[j] for j in range(d)]
            if it == 1 or it % 25 == 0:
                self.loss_history.append(round(self._loss(p, y, w), 6))
            gmax = max(abs(gb), max(abs(g) for g in gw))
            b -= self.lr * gb
            w = [wj - self.lr * g for wj, g in zip(w, gw)]
            if gmax < self.tol:
                break
        self.w, self.b, self.n_iter = w, b, it
        self.converged = gmax < self.tol
        return self

    def _loss(self, p, y, w):
        eps = 1e-12
        n = len(y)
        ll = -sum(yi * math.log(pi + eps) + (1 - yi) * math.log(1 - pi + eps) for pi, yi in zip(p, y)) / n
        return ll + 0.5 * self.l2 * sum(v * v for v in w)

    def decision(self, x):
        return self.b + sum(wi * xi for wi, xi in zip(self.w, x))

    def predict_proba_row(self, x):
        return sigmoid(self.decision(x))

    def predict_proba(self, X):
        return [self.predict_proba_row(x) for x in X]

    def predict(self, X, threshold=0.5):
        return [1 if p >= threshold else 0 for p in self.predict_proba(X)]


def solve_linear(A, b):
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [list(map(float, A[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(col + 1, n):
            f = M[r][col] / pv
            if f:
                Mr, Mc = M[r], M[col]
                for c in range(col, n + 1):
                    Mr[c] -= f * Mc[c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


class LinearRegression:
    """Ridge regression on standardised inputs via the normal equations:
    (X^T X + alpha I) w = X^T (y - mean(y)),  b = mean(y)."""

    def __init__(self, alpha=1.0):
        self.alpha = alpha

    def fit(self, X, y):
        n, d = len(X), len(X[0])
        ym = sum(y) / n
        yc = [v - ym for v in y]
        cols = list(zip(*X))
        A = [[sum(a * c for a, c in zip(cols[i], cols[j])) + (self.alpha if i == j else 0.0)
              for j in range(d)] for i in range(d)]
        rhs = [sum(a * v for a, v in zip(cols[i], yc)) for i in range(d)]
        self.w = solve_linear(A, rhs)
        self.b = ym
        return self

    def predict_row(self, x):
        return self.b + sum(wi * xi for wi, xi in zip(self.w, x))

    def predict(self, X):
        return [self.predict_row(x) for x in X]


def stratified_split(y, test_fraction=0.25, seed=2026):
    """Return (train_idx, test_idx), preserving the class ratio. Deterministic."""
    rng = random.Random(seed)
    train, test = [], []
    for cls in sorted(set(y)):
        idx = [i for i, v in enumerate(y) if v == cls]
        rng.shuffle(idx)
        k = int(round(len(idx) * test_fraction))
        test.extend(idx[:k])
        train.extend(idx[k:])
    return sorted(train), sorted(test)


def kfold_indices(n, k=5, seed=2026):
    """Yield (train_idx, test_idx) for k shuffled folds."""
    rng = random.Random(seed)
    idx = list(range(n))
    rng.shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    for i in range(k):
        test = sorted(folds[i])
        tset = set(test)
        yield [j for j in range(n) if j not in tset], test
