import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placeiq.models import (LinearRegression, LogisticRegression, StandardScaler, kfold_indices,  # noqa: E402
                            sigmoid, solve_linear, stratified_split)


class TestLogisticRegression(unittest.TestCase):
    def toy(self):
        # Linearly separable: y = 1 iff x0 + x1 > 0, with a margin.
        rng = random.Random(1)
        X, y = [], []
        while len(X) < 120:
            a, b = rng.uniform(-3, 3), rng.uniform(-3, 3)
            if abs(a + b) < 0.5:
                continue
            X.append([a, b])
            y.append(1 if a + b > 0 else 0)
        return X, y

    def test_converges_on_separable_toy_set(self):
        X, y = self.toy()
        m = LogisticRegression(lr=0.5, l2=0.01, max_iter=5000, tol=1e-6).fit(X, y)
        self.assertEqual(m.predict(X), y)                       # perfect separation
        self.assertTrue(m.converged, "should stop on the gradient tolerance")
        self.assertLess(m.loss_history[-1], m.loss_history[0])  # loss went down
        # the learned boundary is (close to) x0 + x1 = 0: equal positive weights, ~zero bias
        self.assertGreater(m.w[0], 0)
        self.assertAlmostEqual(m.w[0] / m.w[1], 1.0, delta=0.25)
        self.assertLess(abs(m.b), 0.3)

    def test_loss_is_monotone_non_increasing(self):
        X, y = self.toy()
        m = LogisticRegression(lr=0.3, l2=0.05, max_iter=600, tol=0).fit(X, y)
        h = m.loss_history
        for a, b in zip(h, h[1:]):
            self.assertLessEqual(b, a + 1e-12)

    def test_l2_shrinks_weights(self):
        X, y = self.toy()
        weak = LogisticRegression(l2=0.001, max_iter=3000).fit(X, y)
        strong = LogisticRegression(l2=1.0, max_iter=3000).fit(X, y)
        self.assertLess(sum(abs(w) for w in strong.w), sum(abs(w) for w in weak.w))

    def test_probabilities_in_unit_interval_and_stable(self):
        self.assertAlmostEqual(sigmoid(0), 0.5)
        self.assertGreater(sigmoid(800), 0.999)   # no overflow
        self.assertLess(sigmoid(-800), 0.001)


class TestLinearAndScaler(unittest.TestCase):
    def test_solve_linear(self):
        A = [[2, 1, -1], [-3, -1, 2], [-2, 1, 2]]
        b = [8, -11, -3]
        x = solve_linear(A, b)
        for got, want in zip(x, [2, 3, -1]):
            self.assertAlmostEqual(got, want, places=9)

    def test_singular_raises(self):
        with self.assertRaises(ValueError):
            solve_linear([[1, 2], [2, 4]], [1, 2])

    def test_linear_regression_recovers_coefficients(self):
        # The model expects standardised (zero-mean) inputs, as the engine provides.
        rng = random.Random(3)
        raw = [[rng.gauss(2, 1.5), rng.gauss(-1, 0.5)] for _ in range(300)]
        y = [5 + 2 * a - 3 * b for a, b in raw]
        sc = StandardScaler().fit(raw)
        m = LinearRegression(alpha=1e-9).fit(sc.transform(raw), y)
        self.assertAlmostEqual(m.w[0] / sc.std[0], 2, places=4)
        self.assertAlmostEqual(m.w[1] / sc.std[1], -3, places=4)
        for xr, yt in zip(raw[:20], y[:20]):
            self.assertAlmostEqual(m.predict_row(sc.transform_row(xr)), yt, places=4)

    def test_scaler(self):
        sc = StandardScaler().fit([[1, 10], [3, 10], [5, 10]])
        self.assertEqual(sc.mean, [3, 10])
        self.assertEqual(sc.std[1], 1.0)  # constant column guarded
        z = sc.transform_row([5, 10])
        self.assertAlmostEqual(z[0], 2 / (8 / 3) ** 0.5)
        self.assertEqual(z[1], 0)


class TestSplits(unittest.TestCase):
    def test_stratified_split_preserves_ratio_and_is_deterministic(self):
        y = [1] * 60 + [0] * 40
        tr, te = stratified_split(y, 0.25, seed=5)
        self.assertEqual(len(te), 25)
        self.assertEqual(sum(y[i] for i in te), 15)
        self.assertEqual(set(tr) | set(te), set(range(100)))
        self.assertFalse(set(tr) & set(te))
        self.assertEqual((tr, te), stratified_split(y, 0.25, seed=5))

    def test_kfold_covers_every_row_once(self):
        seen = []
        for tr, te in kfold_indices(23, 5, seed=1):
            self.assertFalse(set(tr) & set(te))
            seen.extend(te)
        self.assertEqual(sorted(seen), list(range(23)))


if __name__ == "__main__":
    unittest.main()
