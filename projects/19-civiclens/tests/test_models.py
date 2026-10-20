import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civiclens import metrics as M  # noqa: E402
from civiclens.features import TfidfVectorizer, doc_terms  # noqa: E402
from civiclens.models import LogisticRegression, MultinomialNB, OneVsRest, logsumexp, sigmoid  # noqa: E402

DOCS = [("pothole on the main road", 0), ("big pothole near school road", 0), ("road damaged potholes", 0),
        ("garbage not collected", 1), ("garbage bin overflowing smell", 1), ("kuppai garbage dump", 1),
        ("street light not working", 2), ("streetlight off dark night", 2), ("light pole wire", 2)]


def toy():
    terms = [doc_terms(t) for t, _ in DOCS]
    v = TfidfVectorizer(min_df=1).fit(terms)
    return v, terms, [y for _, y in DOCS]


class TestNaiveBayes(unittest.TestCase):
    def test_learns_toy_departments(self):
        v, terms, y = toy()
        nb = MultinomialNB(3, v.n_features, alpha=0.5).fit(v.counts(terms), y)
        self.assertEqual([nb.predict(x) for x in v.counts(terms)], y)
        self.assertEqual(nb.predict(v.counts_one(doc_terms("pothole on the road"))), 0)
        self.assertEqual(nb.predict(v.counts_one(doc_terms("garbage smell"))), 1)

    def test_probabilities_are_normalised(self):
        v, terms, y = toy()
        nb = MultinomialNB(3, v.n_features).fit(v.counts(terms), y)
        p = nb.predict_proba(v.counts_one(doc_terms("dark street")))
        self.assertAlmostEqual(sum(p), 1.0, places=9)
        self.assertEqual(max(range(3), key=p.__getitem__), 2)

    def test_matches_hand_computed_likelihood(self):
        # two classes, two features: P(f|c) = (N_cf + a) / (N_c + a V)
        X = [((0,), (2.0,)), ((1,), (1.0,))]
        nb = MultinomialNB(2, 2, alpha=1.0).fit(X, [0, 1])
        self.assertAlmostEqual(math.exp(nb.log_prob[0][0]), 3 / 4)
        self.assertAlmostEqual(math.exp(nb.log_prob[1][0]), 1 / 3)
        self.assertAlmostEqual(math.exp(nb.log_prior[0]), 0.5)

    def test_top_features(self):
        v, terms, y = toy()
        nb = MultinomialNB(3, v.n_features).fit(v.counts(terms), y)
        self.assertIn("w:garbage", [f for f, _ in nb.top_features(1, v.names, 3)])


class TestLogisticRegression(unittest.TestCase):
    def test_sigmoid_is_stable(self):
        self.assertEqual(sigmoid(1000), 1.0)
        self.assertAlmostEqual(sigmoid(-1000), 0.0)
        self.assertAlmostEqual(sigmoid(0), 0.5)
        self.assertAlmostEqual(logsumexp([1000, 1000]), 1000 + math.log(2))

    def test_separable_sparse_problem(self):
        rng = random.Random(3)
        X, y = [], []
        for _ in range(200):
            label = rng.random() < 0.5
            feat = 0 if label else 1
            X.append(((feat, 2), (1.0, rng.random())))
            y.append(1 if label else 0)
        m = LogisticRegression(3, epochs=20, lr=0.5, l2=1e-4).fit(X, y)
        self.assertEqual([1 if m.predict_proba(x) > 0.5 else 0 for x in X], y)
        self.assertGreater(m.w[0], 1.0)
        self.assertLess(m.w[1], -1.0)
        self.assertLess(m.loss_history[-1], m.loss_history[0])

    def test_contributions_sum_to_decision(self):
        m = LogisticRegression(3)
        m.w, m.b = [0.5, -1.0, 2.0], 0.25
        x = ((0, 2), (2.0, 0.5))
        self.assertAlmostEqual(m.b + sum(c for _, c in m.contributions(x)), m.decision(x))

    def test_one_vs_rest(self):
        v, terms, y = toy()
        X = v.transform(terms)
        m = OneVsRest(3, v.n_features, epochs=30, lr=0.8, l2=1e-5).fit(X, y)
        self.assertEqual([m.predict(x) for x in X], y)
        p = m.predict_proba(v.transform_one(doc_terms("garbage bin")))
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertEqual(max(range(3), key=p.__getitem__), 1)


class TestMetrics(unittest.TestCase):
    def test_classification_metrics(self):
        y, p = [0, 0, 1, 1, 2], [0, 1, 1, 1, 2]
        self.assertAlmostEqual(M.accuracy(y, p), 0.8)
        self.assertEqual(M.confusion(y, p, 3), [[1, 1, 0], [0, 2, 0], [0, 0, 1]])
        pc = M.per_class(y, p, 3)
        self.assertAlmostEqual(pc[1]["precision"], 2 / 3)
        self.assertAlmostEqual(M.macro_f1(y, p, 3), (2 / 3 + 0.8 + 1.0) / 3)

    def test_auc(self):
        self.assertAlmostEqual(M.roc_auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]), 0.75)
        self.assertAlmostEqual(M.roc_auc([0, 1], [0.5, 0.5]), 0.5)        # ties count half

    def test_pairwise_cluster_metrics(self):
        r = M.pair_prf(["a", "a", "b", "b"], [1, 1, 1, 2])
        self.assertEqual(r["true_pairs"], 2)
        self.assertEqual(r["pred_pairs"], 3)
        self.assertAlmostEqual(r["precision"], 1 / 3)
        self.assertAlmostEqual(r["recall"], 1 / 2)

    def test_calibration_error(self):
        self.assertAlmostEqual(M.expected_calibration_error([0.9, 0.9], [True, False]), 0.4)
        self.assertAlmostEqual(M.expected_calibration_error([1.0], [True]), 0.0)


if __name__ == "__main__":
    unittest.main()
