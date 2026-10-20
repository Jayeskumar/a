import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placeiq import metrics, stats  # noqa: E402


class TestMetrics(unittest.TestCase):
    def test_auc_hand_computed(self):
        # positives score 0.9, 0.8, 0.6 ; negatives 0.7, 0.55, 0.4
        # pairs won by the positive: 0.9 -> 3, 0.8 -> 3, 0.6 -> 2 (beats 0.55, 0.4) = 8 of 9
        y = [1, 1, 0, 1, 0, 0]
        s = [0.9, 0.8, 0.7, 0.6, 0.55, 0.4]
        self.assertAlmostEqual(metrics.roc_auc(y, s), 8 / 9)

    def test_auc_ties_count_half(self):
        self.assertAlmostEqual(metrics.roc_auc([1, 0], [0.5, 0.5]), 0.5)
        # pos {0.8, 0.5}, neg {0.5, 0.2}: 0.8 wins 2, 0.5 ties 1 (0.5) and wins 1 -> 3.5 / 4
        self.assertAlmostEqual(metrics.roc_auc([1, 1, 0, 0], [0.8, 0.5, 0.5, 0.2]), 3.5 / 4)

    def test_auc_perfect_and_inverted(self):
        self.assertEqual(metrics.roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertEqual(metrics.roc_auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]), 0.0)

    def test_auc_single_class_is_nan(self):
        v = metrics.roc_auc([1, 1], [0.2, 0.3])
        self.assertTrue(v != v)

    def test_auc_matches_trapezoid_area_under_roc_curve(self):
        y = [1, 0, 1, 1, 0, 1, 0, 0, 1, 0]
        s = [0.95, 0.9, 0.85, 0.6, 0.6, 0.55, 0.5, 0.3, 0.2, 0.1]
        pts = metrics.roc_curve(y, s)
        area = sum((b["fpr"] - a["fpr"]) * (a["tpr"] + b["tpr"]) / 2 for a, b in zip(pts, pts[1:]))
        self.assertAlmostEqual(area, metrics.roc_auc(y, s))
        self.assertEqual((pts[0]["fpr"], pts[0]["tpr"]), (0.0, 0.0))
        self.assertEqual((pts[-1]["fpr"], pts[-1]["tpr"]), (1.0, 1.0))

    def test_classification_report_hand_case(self):
        y_true = [1, 1, 1, 0, 0, 0, 0, 1]
        y_pred = [1, 1, 0, 0, 1, 0, 0, 1]
        r = metrics.classification_report(y_true, y_pred)
        self.assertEqual(r["confusion"], {"tp": 3, "tn": 3, "fp": 1, "fn": 1})
        self.assertAlmostEqual(r["accuracy"], 6 / 8)
        self.assertAlmostEqual(r["precision"], 3 / 4)
        self.assertAlmostEqual(r["recall"], 3 / 4)
        self.assertAlmostEqual(r["f1"], 0.75)
        self.assertAlmostEqual(r["fpr"], 1 / 4)

    def test_regression_metrics(self):
        y, yhat = [1, 2, 3, 4], [1, 2, 3, 5]
        self.assertAlmostEqual(metrics.mae(y, yhat), 0.25)
        self.assertAlmostEqual(metrics.r2_score(y, yhat), 1 - 1 / 5)
        self.assertAlmostEqual(metrics.r2_score(y, y), 1.0)


class TestStats(unittest.TestCase):
    def test_pearson(self):
        self.assertAlmostEqual(stats.pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(stats.pearson([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertEqual(stats.pearson([1, 1, 1], [1, 2, 3]), 0.0)

    def test_quantile_and_summary(self):
        xs = [1, 2, 3, 4]
        self.assertAlmostEqual(stats.quantile(xs, 0.5), 2.5)
        self.assertAlmostEqual(stats.quantile(xs, 0.25), 1.75)
        s = stats.summary(xs)
        self.assertEqual((s["min"], s["max"], s["count"]), (1, 4, 4))
        self.assertAlmostEqual(s["std"], (5 / 3) ** 0.5)

    def test_histogram_counts_everything(self):
        xs = [0.1 * i for i in range(100)]
        h = stats.histogram(xs, 10)
        self.assertEqual(sum(b["count"] for b in h), 100)
        self.assertEqual(len(h), 10)
        ints = stats.histogram([0, 0, 1, 3], 12, integer=True)
        self.assertEqual([b["count"] for b in ints], [2, 1, 0, 1])

    def test_correlation_matrix_symmetric(self):
        names, m = stats.correlation_matrix({"a": [1, 2, 3, 4], "b": [2, 1, 4, 3], "c": [4, 3, 2, 1]})
        self.assertEqual(names, ["a", "b", "c"])
        self.assertAlmostEqual(m[0][1], m[1][0])
        self.assertAlmostEqual(m[0][2], -1.0)
        self.assertEqual(m[1][1], 1.0)


if __name__ == "__main__":
    unittest.main()
