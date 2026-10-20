import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phishguard.logreg import LogisticRegression, sigmoid  # noqa: E402


class LogisticRegressionTest(unittest.TestCase):
    def setUp(self):
        # y = 1 when feature 0 is on; feature 1 is noise
        self.X = [[1, 0], [1, 1], [0, 1], [0, 0], [1, 0.5], [0, 0.5]]
        self.y = [1, 1, 0, 0, 1, 0]

    def test_learns_separable_data(self):
        lr = LogisticRegression(learning_rate=1.0, epochs=400).fit(self.X, self.y)
        self.assertEqual([lr.predict(x) for x in self.X], self.y)
        self.assertGreater(lr.weights[0], 2.0)
        self.assertLess(abs(lr.weights[1]), abs(lr.weights[0]))

    def test_loss_decreases(self):
        lr = LogisticRegression(learning_rate=0.5, epochs=200).fit(self.X, self.y)
        self.assertAlmostEqual(lr.loss_history[0], math.log(2), places=6)  # w = 0 -> p = 0.5
        self.assertLess(lr.loss_history[-1], lr.loss_history[0] / 2)
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(lr.loss_history, lr.loss_history[1:])))

    def test_single_gradient_step_by_hand(self):
        # one sample x=[1], y=1, w=0,b=0: p=0.5, grad_w = grad_b = -0.5; lr=0.1 -> w=b=0.05
        lr = LogisticRegression(learning_rate=0.1, epochs=1).fit([[1.0]], [1])
        self.assertAlmostEqual(lr.weights[0], 0.05)
        self.assertAlmostEqual(lr.bias, 0.05)

    def test_l2_shrinks_weights(self):
        a = LogisticRegression(1.0, 300, l2=0.0).fit(self.X, self.y)
        b = LogisticRegression(1.0, 300, l2=0.1).fit(self.X, self.y)
        self.assertLess(abs(b.weights[0]), abs(a.weights[0]))

    def test_contributions_add_up(self):
        lr = LogisticRegression(1.0, 200).fit(self.X, self.y)
        x = [1, 0.5]
        total = sum(c for _, _, _, c in lr.contributions(x, ["a", "b"]))
        self.assertAlmostEqual(total + lr.bias, lr.decision(x))

    def test_sigmoid_is_stable(self):
        self.assertEqual(sigmoid(0), 0.5)
        self.assertAlmostEqual(sigmoid(1000), 1.0)
        self.assertAlmostEqual(sigmoid(-1000), 0.0)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            LogisticRegression().fit([], [])


if __name__ == "__main__":
    unittest.main()
