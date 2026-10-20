import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurocanvas.mlp import MLP, SGDMomentum, cross_entropy, log_softmax, softmax  # noqa: E402


def numeric_grad(f, get, set_, eps=1e-5):
    v = get()
    set_(v + eps)
    a = f()
    set_(v - eps)
    b = f()
    set_(v)
    return (a - b) / (2 * eps)


def rel_err(a, b):
    return abs(a - b) / max(1e-8, abs(a) + abs(b))


class GradientCheck(unittest.TestCase):
    """Backprop must agree with central finite differences on every parameter."""

    def _check(self, activation, sizes, l2):
        r = random.Random(11)
        m = MLP(sizes, activation, seed=5)
        for bl in m.b:                       # non-zero biases so their gradients are tested too
            for j in range(len(bl)):
                bl[j] = r.uniform(-0.3, 0.3)
        X = [[r.uniform(-1, 1) for _ in range(sizes[0])] for _ in range(5)]
        Y = [r.randrange(sizes[-1]) for _ in range(5)]
        gW, gb = m.gradients(X, Y, l2=l2)
        f = lambda: m.loss(X, Y, l2=l2)      # noqa: E731
        worst = 0.0
        for l in range(len(m.W)):
            for j in range(len(m.W[l])):
                for i in range(len(m.W[l][j])):
                    def get(l=l, j=j, i=i):
                        return m.W[l][j][i]

                    def set_(v, l=l, j=j, i=i):
                        m.W[l][j][i] = v
                    worst = max(worst, rel_err(numeric_grad(f, get, set_), gW[l][j][i]))
                def getb(l=l, j=j):
                    return m.b[l][j]

                def setb(v, l=l, j=j):
                    m.b[l][j] = v
                worst = max(worst, rel_err(numeric_grad(f, getb, setb), gb[l][j]))
        return worst

    def test_relu_two_hidden_layers_with_l2(self):
        self.assertLess(self._check("relu", [7, 6, 5, 4], 0.01), 1e-6)

    def test_tanh_two_hidden_layers(self):
        self.assertLess(self._check("tanh", [7, 6, 5, 4], 0.0), 1e-6)

    def test_single_hidden_layer(self):
        self.assertLess(self._check("relu", [5, 3, 3], 0.001), 1e-6)

    def test_input_gradient_is_saliency(self):
        r = random.Random(3)
        for act in ("relu", "tanh"):
            m = MLP([9, 7, 5, 4], act, seed=2)
            x = [r.uniform(0, 1) for _ in range(9)]
            for target in ("logit", "logprob"):
                cls = 2
                g = m.input_gradient(x, cls, target)

                def score():
                    z = m.forward(x)[0][-1]
                    return z[cls] if target == "logit" else log_softmax(z)[cls]
                for i in range(9):
                    def get(i=i):
                        return x[i]

                    def set_(v, i=i):
                        x[i] = v
                    self.assertLess(rel_err(numeric_grad(score, get, set_), g[i]), 1e-6, (act, target, i))


class SoftmaxNumerics(unittest.TestCase):
    def test_huge_logits_do_not_overflow(self):
        p = softmax([1000.0, 1001.0, 999.0])
        self.assertAlmostEqual(sum(p), 1.0, places=12)
        self.assertTrue(all(math.isfinite(v) for v in p))
        self.assertAlmostEqual(p[1], math.exp(1) / (1 + math.exp(1) + math.exp(-1)), places=12)

    def test_tiny_probabilities_keep_finite_log(self):
        lp = log_softmax([0.0, -800.0])
        self.assertTrue(math.isfinite(lp[1]))
        self.assertAlmostEqual(lp[1], -800.0, places=6)
        self.assertAlmostEqual(cross_entropy([0.0, -800.0], 1), 800.0, places=6)

    def test_shift_invariance(self):
        z = [0.3, -1.2, 2.5, 0.0]
        a = softmax(z)
        b = softmax([v + 123.4 for v in z])
        for u, v in zip(a, b):
            self.assertAlmostEqual(u, v, places=12)

    def test_cross_entropy_gradient_is_p_minus_onehot(self):
        z = [0.5, -0.3, 1.7, 0.2]
        y = 1
        p = softmax(z)
        for k in range(4):
            def get(k=k):
                return z[k]

            def set_(v, k=k):
                z[k] = v
            num = numeric_grad(lambda: cross_entropy(z, y), get, set_)
            self.assertAlmostEqual(num, p[k] - (1.0 if k == y else 0.0), places=7)

    def test_uniform_logits_give_log10_loss(self):
        self.assertAlmostEqual(cross_entropy([0.0] * 10, 3), math.log(10), places=12)


class Structure(unittest.TestCase):
    def test_he_init_scale(self):
        m = MLP([400, 200, 10], "relu", seed=1)
        w = [v for row in m.W[0] for v in row]
        std = math.sqrt(sum(v * v for v in w) / len(w))
        self.assertAlmostEqual(std, math.sqrt(2 / 400), delta=0.004)

    def test_serialisation_round_trip(self):
        m = MLP([6, 4, 3], "tanh", seed=4)
        m2 = MLP.from_dict(m.to_dict(digits=12))
        x = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        for a, b in zip(m.predict_proba(x), m2.predict_proba(x)):
            self.assertAlmostEqual(a, b, places=9)
        self.assertEqual(m2.n_params, 6 * 4 + 4 + 4 * 3 + 3)

    def test_bad_shapes_rejected(self):
        d = MLP([3, 2, 2]).to_dict()
        d["sizes"] = [3, 3, 2]
        with self.assertRaises(ValueError):
            MLP.from_dict(d)
        with self.assertRaises(ValueError):
            MLP([3, 2], "sigmoid")
        with self.assertRaises(ValueError):
            MLP([3, 2]).forward([1.0, 2.0])

    def test_copy_is_deep(self):
        m = MLP([3, 2, 2], seed=0)
        c = m.copy()
        c.W[0][0][0] += 1.0
        self.assertNotEqual(m.W[0][0][0], c.W[0][0][0])

    def test_relu_logit_decomposes_exactly_into_pixels_and_biases(self):
        """For a ReLU net, z_c = sum_i x_i dz/dx_i + sum_l sum_j b_lj dz/dz_lj (exact)."""
        r = random.Random(8)
        m = MLP([12, 8, 6, 5], "relu", seed=9)
        for bl in m.b:
            for j in range(len(bl)):
                bl[j] = r.uniform(-0.5, 0.5)
        x = [r.uniform(0, 1) for _ in range(12)]
        zs, acts = m.forward(x)
        c = 3
        onehot = [0.0] * 5
        onehot[c] = 1.0
        deltas, dx = m.backward(zs, acts, onehot, to_input=True)
        pixels = sum(a * b for a, b in zip(x, dx))
        biases = sum(b * d for bl, dl in zip(m.b, deltas) for b, d in zip(bl, dl))
        self.assertAlmostEqual(pixels + biases, zs[-1][c], places=10)

    def test_momentum_update_rule(self):
        m = MLP([1, 1], seed=0)
        m.W[0][0][0], m.b[0][0] = 0.5, 0.0
        opt = SGDMomentum(m, lr=0.1, momentum=0.9, l2=0.0)
        opt.step([[[2.0]]], [[0.0]], 1)       # v = -0.2 ; w = 0.3
        self.assertAlmostEqual(m.W[0][0][0], 0.3)
        opt.step([[[2.0]]], [[0.0]], 1)       # v = 0.9*-0.2 - 0.2 = -0.38 ; w = -0.08
        self.assertAlmostEqual(m.W[0][0][0], -0.08)


if __name__ == "__main__":
    unittest.main()
