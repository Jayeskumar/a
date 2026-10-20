import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from neurocanvas.metrics import accuracy, evaluate  # noqa: E402
from neurocanvas.mlp import MLP  # noqa: E402
from neurocanvas.train import fit  # noqa: E402


class TrainingLearns(unittest.TestCase):
    def test_xor_is_learned(self):
        X = [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]]
        Y = [0, 1, 1, 0]
        m = MLP([2, 8, 2], "tanh", seed=3)
        before = m.loss(X, Y)
        hist = fit(m, X, Y, epochs=300, batch=4, lr=0.1, momentum=0.9, seed=1)
        self.assertLess(m.loss(X, Y), 0.05)
        self.assertLess(m.loss(X, Y), before / 10)
        self.assertEqual(accuracy(m, X, Y), 1.0)
        self.assertEqual(len(hist), 300)

    def test_relu_xor_with_two_hidden_layers(self):
        X = [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]] * 4
        Y = [0, 1, 1, 0] * 4
        m = MLP([2, 16, 8, 2], "relu", seed=2)
        fit(m, X, Y, epochs=150, batch=4, lr=0.05, momentum=0.9, seed=2)
        self.assertEqual(accuracy(m, X, Y), 1.0)

    def test_separable_blobs_loss_goes_down_every_few_epochs(self):
        r = random.Random(5)
        X, Y = [], []
        for _ in range(200):
            c = r.randrange(3)
            cx, cy = [(0, 0), (3, 0), (0, 3)][c]
            X.append([cx + r.gauss(0, 0.5), cy + r.gauss(0, 0.5)])
            Y.append(c)
        m = MLP([2, 10, 3], "relu", seed=1)
        hist = fit(m, X, Y, epochs=12, batch=16, lr=0.05, momentum=0.9, seed=3)
        losses = [h["loss"] for h in hist]
        self.assertLess(losses[-1], losses[0] / 3)
        self.assertGreater(accuracy(m, X, Y), 0.97)

    def test_stop_flag_interrupts(self):
        X = [[float(i % 2)] for i in range(64)]
        Y = [i % 2 for i in range(64)]
        m = MLP([1, 4, 2], seed=0)
        hist = fit(m, X, Y, epochs=50, batch=8, lr=0.1, should_stop=lambda: True)
        self.assertEqual(len(hist), 1)
        self.assertTrue(hist[0]["partial"])

    def test_absurd_learning_rate_is_reported_not_raised(self):
        X = [[1.0, 2.0], [2.0, 1.0], [0.0, 3.0], [3.0, 0.0]] * 8
        Y = [0, 1, 0, 1] * 8
        m = MLP([2, 16, 2], "relu", seed=1)
        hist = fit(m, X, Y, epochs=30, batch=4, lr=1e200, momentum=0.9, seed=1)
        last = hist[-1]
        self.assertTrue(last.get("diverged") or all(math.isfinite(h["loss"]) for h in hist))
        json.dumps(hist, allow_nan=False)          # always JSON-safe for the UI


class Metrics(unittest.TestCase):
    def test_confusion_matrix_counts(self):
        class Fixed:
            def __init__(self, preds):
                self.preds = iter(preds)

            def forward(self, x):
                z = [0.0] * 10
                z[next(self.preds)] = 5.0
                return [z], None
        Y = [0, 0, 1, 2, 2, 2]
        ev = evaluate(Fixed([0, 1, 1, 2, 2, 0]), [[0]] * 6, Y)
        self.assertEqual(ev["confusion"][0], [1, 1] + [0] * 8)
        self.assertEqual(ev["confusion"][2][0], 1)
        self.assertEqual(ev["correct"], 4)
        self.assertAlmostEqual(ev["accuracy"], 4 / 6, places=4)
        self.assertEqual(ev["n_wrong"], 2)
        self.assertEqual(ev["per_class"][1]["precision"], 0.5)
        self.assertEqual(ev["per_class"][2]["recall"], round(2 / 3, 4))
        self.assertEqual(sum(map(sum, ev["confusion"])), 6)


if __name__ == "__main__":
    unittest.main()
