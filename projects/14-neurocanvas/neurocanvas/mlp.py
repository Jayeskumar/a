"""A multi-layer perceptron with backpropagation written out by hand.

Notation (one sample, layers l = 0 .. L-1, W[l] has shape n_out x n_in):

    a_0 = x                                   input pixels
    z_l = W_l a_l + b_l                       pre-activation of layer l
    a_{l+1} = f(z_l)                          f = ReLU or tanh for hidden layers
    p = softmax(z_{L-1})                      output probabilities
    loss = -log p_y  (+ L2/2 * sum W^2)       cross-entropy with the true class y

Backward pass (chain rule), the part a framework's ``loss.backward()`` hides:

    dL/dz_{L-1} = p - onehot(y)               softmax + cross-entropy simplify to this
    dL/dW_l     = dL/dz_l  outer  a_l         (+ L2 * W_l)
    dL/db_l     = dL/dz_l
    dL/da_l     = W_l^T dL/dz_l
    dL/dz_{l-1} = dL/da_l * f'(z_{l-1})       ReLU' = 1 if z > 0 else 0;  tanh' = 1 - a^2

Vectors are plain Python lists; inner products use ``sum(map(mul, ...))`` which
runs the loop in C and is the fastest pure-Python option.
"""

import math
import random
from itertools import repeat
from operator import add, mul

ACTIVATIONS = ("relu", "tanh")


# ---- numerically stable softmax / cross-entropy ------------------------------

def softmax(z):
    """exp(z - max) / sum: subtracting the max avoids overflow for big logits."""
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def log_softmax(z):
    """log p via log-sum-exp; never takes log(0) even for extreme logits."""
    m = max(z)
    lse = m + math.log(sum(math.exp(v - m) for v in z))
    return [v - lse for v in z]


def cross_entropy(z, y):
    return -log_softmax(z)[y]


def _zeros_like(mats):
    return [[[0.0] * len(row) for row in m] for m in mats]


class MLP:
    def __init__(self, sizes, activation="relu", seed=0):
        if activation not in ACTIVATIONS:
            raise ValueError("activation must be one of %s" % (ACTIVATIONS,))
        if len(sizes) < 2 or any(int(s) < 1 for s in sizes):
            raise ValueError("sizes must list at least an input and an output layer")
        self.sizes = [int(s) for s in sizes]
        self.activation = activation
        rng = random.Random(seed)
        self.W, self.b = [], []
        last = len(self.sizes) - 2
        for l, (n_in, n_out) in enumerate(zip(self.sizes, self.sizes[1:])):
            if activation == "relu" and l < last:
                std = math.sqrt(2.0 / n_in)              # He init: keeps ReLU variance stable
            else:
                std = math.sqrt(2.0 / (n_in + n_out))    # Xavier/Glorot for tanh and the output
            self.W.append([[rng.gauss(0.0, std) for _ in range(n_in)] for _ in range(n_out)])
            self.b.append([0.0] * n_out)

    # ---- bookkeeping ----
    @property
    def n_params(self):
        return sum(len(m) * len(m[0]) + len(b) for m, b in zip(self.W, self.b))

    def copy(self):
        c = MLP.__new__(MLP)
        c.sizes = list(self.sizes)
        c.activation = self.activation
        c.W = [[list(r) for r in m] for m in self.W]
        c.b = [list(v) for v in self.b]
        return c

    def to_dict(self, digits=6):
        return {"sizes": self.sizes, "activation": self.activation,
                "W": [[[round(v, digits) for v in r] for r in m] for m in self.W],
                "b": [[round(v, digits) for v in r] for r in self.b]}

    @classmethod
    def from_dict(cls, d):
        m = cls.__new__(cls)
        m.sizes = [int(s) for s in d["sizes"]]
        m.activation = d.get("activation", "relu")
        if m.activation not in ACTIVATIONS:
            raise ValueError("bad activation")
        m.W = [[[float(v) for v in r] for r in mat] for mat in d["W"]]
        m.b = [[float(v) for v in r] for r in d["b"]]
        for l, (n_in, n_out) in enumerate(zip(m.sizes, m.sizes[1:])):
            if len(m.W[l]) != n_out or any(len(r) != n_in for r in m.W[l]) or len(m.b[l]) != n_out:
                raise ValueError("weight shapes do not match sizes")
        return m

    # ---- activation helpers ----
    def _f(self, z):
        if self.activation == "relu":
            return [v if v > 0.0 else 0.0 for v in z]
        return list(map(math.tanh, z))

    def _df(self, z, a):
        if self.activation == "relu":
            return [1.0 if v > 0.0 else 0.0 for v in z]
        return [1.0 - t * t for t in a]

    # ---- forward ----
    def forward(self, x):
        """Returns (zs, acts): zs[l] = pre-activation of layer l (zs[-1] = logits),
        acts[l] = input to layer l (acts[0] = x)."""
        if len(x) != self.sizes[0]:
            raise ValueError("expected %d inputs, got %d" % (self.sizes[0], len(x)))
        acts, zs = [x], []
        a = x
        last = len(self.W) - 1
        for l, (Wl, bl) in enumerate(zip(self.W, self.b)):
            z = [bj + sum(map(mul, row, a)) for row, bj in zip(Wl, bl)]
            zs.append(z)
            if l < last:
                a = self._f(z)
                acts.append(a)
        return zs, acts

    def predict_proba(self, x):
        return softmax(self.forward(x)[0][-1])

    def predict(self, x):
        p = self.predict_proba(x)
        return max(range(len(p)), key=p.__getitem__)

    # ---- backward ----
    def _wt_dot(self, l, delta):
        """W_l^T delta, skipping zero deltas (dead ReLUs)."""
        Wl = self.W[l]
        out = [0.0] * self.sizes[l]
        for j, d in enumerate(delta):
            if d:
                out = list(map(add, out, map(mul, Wl[j], repeat(d))))
        return out

    def backward(self, zs, acts, dout, to_input=False):
        """Backpropagate dL/dlogits. Returns (deltas, dx) where deltas[l] = dL/dz_l."""
        L = len(self.W)
        deltas = [None] * L
        delta = dout
        deltas[L - 1] = delta
        for l in range(L - 1, 0, -1):
            da = self._wt_dot(l, delta)                       # dL/da_l
            delta = list(map(mul, da, self._df(zs[l - 1], acts[l])))   # through f'
            deltas[l - 1] = delta
        dx = self._wt_dot(0, deltas[0]) if to_input else None
        return deltas, dx

    def accumulate(self, acts, deltas, gW, gb):
        """gW_l += delta_l outer a_l ; gb_l += delta_l (in place)."""
        for l, delta in enumerate(deltas):
            a = acts[l]
            gWl, gbl = gW[l], gb[l]
            for j, d in enumerate(delta):
                if d:
                    gbl[j] += d
                    gWl[j] = list(map(add, gWl[j], map(mul, a, repeat(d))))

    def batch_gradients(self, X, Y):
        """Summed gradients over a batch. Returns (loss_sum, n_correct, gW, gb)."""
        gW = _zeros_like(self.W)
        gb = [[0.0] * len(v) for v in self.b]
        loss = 0.0
        correct = 0
        for x, y in zip(X, Y):
            zs, acts = self.forward(x)
            logits = zs[-1]
            lp = log_softmax(logits)
            loss -= lp[y]
            if max(range(len(logits)), key=logits.__getitem__) == y:
                correct += 1
            d = [math.exp(v) for v in lp]                     # p
            d[y] -= 1.0                                       # p - onehot(y)
            deltas, _ = self.backward(zs, acts, d)
            self.accumulate(acts, deltas, gW, gb)
        return loss, correct, gW, gb

    def loss(self, X, Y, l2=0.0):
        """Mean cross-entropy (+ L2/2 * ||W||^2): what the gradient check differentiates."""
        total = sum(cross_entropy(self.forward(x)[0][-1], y) for x, y in zip(X, Y)) / len(X)
        if l2:
            total += 0.5 * l2 * sum(v * v for m in self.W for r in m for v in r)
        return total

    def gradients(self, X, Y, l2=0.0):
        """Gradient of ``loss`` (mean over the batch, with L2) - used by the gradient check."""
        _, _, gW, gb = self.batch_gradients(X, Y)
        n = float(len(X))
        gW = [[[g / n + l2 * w for g, w in zip(gr, wr)] for gr, wr in zip(gm, wm)]
              for gm, wm in zip(gW, self.W)]
        gb = [[g / n for g in v] for v in gb]
        return gW, gb

    def input_gradient(self, x, cls, target="logit"):
        """d(score)/dx: the saliency map. target='logit' uses z_cls, 'logprob' uses log p_cls."""
        zs, acts = self.forward(x)
        if target == "logit":
            dout = [0.0] * len(zs[-1])
            dout[cls] = 1.0
        else:
            p = softmax(zs[-1])
            dout = [-v for v in p]
            dout[cls] += 1.0                                  # d log p_c / dz = onehot - p
        _, dx = self.backward(zs, acts, dout, to_input=True)
        return dx


class SGDMomentum:
    """v <- mu v - lr (g/n + l2 W);  W <- W + v   (classical momentum, L2 on weights only)."""

    def __init__(self, model, lr=0.05, momentum=0.9, l2=0.0):
        self.model, self.lr, self.momentum, self.l2 = model, lr, momentum, l2
        self.vW = _zeros_like(model.W)
        self.vb = [[0.0] * len(v) for v in model.b]

    def step(self, gW, gb, n):
        inv, lr, mu, l2 = 1.0 / n, self.lr, self.momentum, self.l2
        m = self.model
        for l in range(len(m.W)):
            Wl, vWl, gWl = m.W[l], self.vW[l], gW[l]
            for j in range(len(Wl)):
                v = [mu * vi - lr * (gi * inv + l2 * wi) for vi, gi, wi in zip(vWl[j], gWl[j], Wl[j])]
                vWl[j] = v
                Wl[j] = list(map(add, Wl[j], v))
            vb = [mu * vi - lr * gi * inv for vi, gi in zip(self.vb[l], gb[l])]
            self.vb[l] = vb
            m.b[l] = list(map(add, m.b[l], vb))
