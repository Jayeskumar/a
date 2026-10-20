import math
import unittest

import _path  # noqa: F401
from krishimitra import dataset
from krishimitra.gnb import GaussianNB


class TestGaussianNB(unittest.TestCase):
    def setUp(self):
        # class a: values 1, 3 -> mean 2, var 1 ; class b: 10, 12 -> mean 11, var 1
        self.X = [[1.0], [3.0], [10.0], [12.0]]
        self.y = ["a", "a", "b", "b"]
        self.m = GaussianNB(var_smoothing=0.0).fit(self.X, self.y)

    def test_hand_computed_parameters(self):
        self.assertEqual(self.m.means["a"], [2.0])
        self.assertEqual(self.m.means["b"], [11.0])
        self.assertAlmostEqual(self.m.vars["a"][0], 1.0)
        self.assertAlmostEqual(self.m.priors["a"], 0.5)

    def test_log_likelihood_matches_formula(self):
        # log N(2; 2, 1) = -0.5 * log(2*pi)
        self.assertAlmostEqual(self.m.feature_log_likelihood("a", 0, 2.0), -0.5 * math.log(2 * math.pi))
        # one sd away: extra -0.5
        self.assertAlmostEqual(self.m.feature_log_likelihood("a", 0, 3.0), -0.5 * math.log(2 * math.pi) - 0.5)

    def test_posterior_hand_computed(self):
        # x = 6.5 is equidistant from both means -> 50/50
        p = self.m.predict_proba([6.5])
        self.assertAlmostEqual(p["a"], 0.5)
        # x = 5: log-odds a vs b = -0.5*(9) + 0.5*(36) = 13.5
        p = self.m.predict_proba([5.0])
        self.assertAlmostEqual(math.log(p["a"] / p["b"]), 13.5, places=6)
        self.assertEqual(self.m.predict([2.4]), "a")
        self.assertEqual(self.m.predict([11.5]), "b")

    def test_explain_sums_to_log_odds(self):
        x = [5.0]
        deltas, prior = self.m.explain(x, "a", "b")
        p = self.m.predict_proba(x)
        self.assertAlmostEqual(sum(deltas) + prior, math.log(p["a"] / p["b"]), places=6)

    def test_constant_feature_does_not_crash(self):
        m = GaussianNB().fit([[1, 5], [1, 6], [2, 9], [2, 8]], ["a", "a", "b", "b"])
        p = m.predict_proba([1, 5.5])
        self.assertAlmostEqual(sum(p.values()), 1.0)
        self.assertEqual(max(p, key=p.get), "a")

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            GaussianNB().fit([], [])

    def test_synthetic_holdout_accuracy(self):
        X, y = dataset.generate()
        Xtr, ytr, Xte, yte = dataset.stratified_split(X, y)
        m = GaussianNB().fit(Xtr, ytr)
        acc = sum(m.predict(x) == t for x, t in zip(Xte, yte)) / float(len(yte))
        self.assertGreater(acc, 0.85)


class TestDataset(unittest.TestCase):
    def test_deterministic_and_stratified(self):
        X1, y1 = dataset.generate()
        X2, y2 = dataset.generate()
        self.assertEqual(X1, X2)
        self.assertEqual(y1, y2)
        Xtr, ytr, Xte, yte = dataset.stratified_split(X1, y1)
        self.assertEqual(len(Xtr) + len(Xte), len(X1))
        for c in set(y1):
            self.assertEqual(yte.count(c), 30)   # 25% of 120 per crop


if __name__ == "__main__":
    unittest.main()
