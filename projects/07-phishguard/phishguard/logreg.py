"""Binary logistic regression trained with full-batch gradient descent + L2.

    p(y=1 | x) = sigmoid(w . x + b)
    loss       = mean(-y log p - (1-y) log(1-p)) + (l2 / 2) * |w|^2
    grad_w     = mean((p - y) * x) + l2 * w
    grad_b     = mean(p - y)

Features are expected to be pre-scaled to roughly [0, 1] (see urlfeatures.py)
so the weights are directly comparable and each contribution w_i * x_i is
an honest, explainable share of the log-odds.
"""
import math


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogisticRegression:
    def __init__(self, learning_rate=0.5, epochs=500, l2=0.0):
        self.learning_rate = float(learning_rate)
        self.epochs = int(epochs)
        self.l2 = float(l2)
        self.weights = []
        self.bias = 0.0
        self.loss_history = []

    def fit(self, X, y):
        if not X or len(X) != len(y):
            raise ValueError("X and y must be non-empty and the same length")
        n, d = len(X), len(X[0])
        w = [0.0] * d
        b = 0.0
        lr, l2 = self.learning_rate, self.l2
        self.loss_history = []
        for epoch in range(self.epochs):
            gw = [0.0] * d
            gb = 0.0
            loss = 0.0
            for xi, yi in zip(X, y):
                z = b
                for j in range(d):
                    z += w[j] * xi[j]
                p = sigmoid(z)
                err = p - yi
                gb += err
                for j in range(d):
                    if xi[j]:
                        gw[j] += err * xi[j]
                pc = min(max(p, 1e-12), 1 - 1e-12)
                loss -= yi * math.log(pc) + (1 - yi) * math.log(1 - pc)
            loss = loss / n + 0.5 * l2 * sum(v * v for v in w)
            for j in range(d):
                w[j] -= lr * (gw[j] / n + l2 * w[j])
            b -= lr * gb / n
            if epoch % 10 == 0 or epoch == self.epochs - 1:
                self.loss_history.append(loss)
        self.weights, self.bias = w, b
        return self

    def decision(self, x):
        return self.bias + sum(wj * xj for wj, xj in zip(self.weights, x))

    def predict_proba(self, x):
        return sigmoid(self.decision(x))

    def predict(self, x, threshold=0.5):
        return 1 if self.predict_proba(x) >= threshold else 0

    def contributions(self, x, names):
        """(name, value, weight, weight*value) for every non-zero feature."""
        out = []
        for name, xj, wj in zip(names, x, self.weights):
            if xj:
                out.append((name, xj, wj, wj * xj))
        out.sort(key=lambda r: -abs(r[3]))
        return out
