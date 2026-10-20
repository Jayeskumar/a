import random
import unittest

import _path  # noqa: F401
from krishimitra import dataset
from krishimitra.forest import DecisionTree, RandomForest, gini_from_counts


class TestCART(unittest.TestCase):
    def test_gini(self):
        self.assertAlmostEqual(gini_from_counts([5, 5], 10), 0.5)
        self.assertAlmostEqual(gini_from_counts([10, 0], 10), 0.0)
        self.assertAlmostEqual(gini_from_counts([1, 1, 1], 3), 2 / 3.0)

    def test_best_split_hand_computed(self):
        # feature 0 separates perfectly between 3 and 7; feature 1 is noise
        X = [[1, 5], [2, 1], [3, 9], [7, 2], [8, 8], [9, 4]]
        y = [0, 0, 0, 1, 1, 1]
        tree = DecisionTree(max_depth=3)
        tree.n_classes, tree.n_features = 2, 2
        gain, f, thr = tree.best_split(X, y, list(range(6)), [0, 1])
        self.assertEqual(f, 0)
        self.assertAlmostEqual(thr, 5.0)
        self.assertAlmostEqual(gain, 0.5)        # parent gini 0.5 -> children 0

    def test_fits_separable_data_and_respects_depth(self):
        rng = random.Random(1)
        X = [[rng.uniform(0, 10), rng.uniform(0, 10)] for _ in range(200)]
        y = [1 if a + b > 10 else 0 for a, b in X]
        deep = DecisionTree(max_depth=12).fit(X, y)
        acc = sum(deep.predict(x) == t for x, t in zip(X, y)) / 200.0
        self.assertGreater(acc, 0.99)
        stump = DecisionTree(max_depth=1).fit(X, y)
        self.assertEqual(stump.depth(), 1)

    def test_tree_contributions_add_up(self):
        rng = random.Random(3)
        X = [[rng.uniform(0, 1) for _ in range(3)] for _ in range(150)]
        y = [int(x[0] > 0.5) + int(x[2] > 0.7) for x in X]
        tree = DecisionTree(max_depth=6).fit(X, y, 3)
        for x in X[:20]:
            for c in range(3):
                bias, contrib = tree.contributions(x, c)
                self.assertAlmostEqual(bias + sum(contrib), tree.predict_proba(x)[c])


class TestRandomForest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        X, y = dataset.generate()
        cls.Xtr, cls.ytr, cls.Xte, cls.yte = dataset.stratified_split(X, y)
        cls.rf = RandomForest(n_trees=12, max_depth=10, max_features=3, seed=5).fit(cls.Xtr, cls.ytr)

    def test_accuracy_and_oob(self):
        acc = sum(self.rf.predict(x) == t for x, t in zip(self.Xte, self.yte)) / float(len(self.yte))
        self.assertGreater(acc, 0.85)
        self.assertTrue(0.5 < self.rf.oob_score <= 1.0)

    def test_probabilities_and_importances(self):
        p = self.rf.predict_proba(self.Xte[0])
        self.assertAlmostEqual(sum(p.values()), 1.0)
        imp = self.rf.feature_importances()
        self.assertEqual(len(imp), 7)
        self.assertAlmostEqual(sum(imp), 1.0)

    def test_forest_contributions_add_up(self):
        x = self.Xte[5]
        p = self.rf.predict_proba(x)
        best = max(p, key=p.get)
        bias, contrib = self.rf.contributions(x, best)
        self.assertAlmostEqual(bias + sum(contrib), p[best])

    def test_deterministic(self):
        rf2 = RandomForest(n_trees=12, max_depth=10, max_features=3, seed=5).fit(self.Xtr, self.ytr)
        self.assertEqual(rf2.predict_proba(self.Xte[3]), self.rf.predict_proba(self.Xte[3]))

    def test_bootstrap_feature_bagging_produces_diverse_trees(self):
        roots = set((t.root.feature, round(t.root.threshold, 3)) for t in self.rf.trees)
        self.assertGreater(len(roots), 1)


if __name__ == "__main__":
    unittest.main()
