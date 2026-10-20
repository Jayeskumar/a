import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wastewise import forecast as F  # noqa: E402

WEEK = [0.8, 0.8, 2.0, 1.1, 0.9, 0.7, 0.7]  # Wed = market day


def synthetic(days=56, base=0.3, noise=0.05, seed=1):
    r = random.Random(seed)
    return [(d % 7, base * WEEK[d % 7] * math.exp(r.gauss(0, noise))) for d in range(days)]


class LinearAlgebraTest(unittest.TestCase):
    def test_solve_linear(self):
        A = [[2, 1, -1], [-3, -1, 2], [-2, 1, 2]]
        b = [8, -11, -3]
        x = F.solve_linear(A, b)
        for got, want in zip(x, [2, 3, -1]):
            self.assertAlmostEqual(got, want, places=9)

    def test_singular_raises(self):
        with self.assertRaises(ValueError):
            F.solve_linear([[1, 2], [2, 4]], [1, 2])

    def test_ols_recovers_trend_and_weekday_effects(self):
        eff = [0, 0.1, 0.5, 0.2, 0, -0.1, -0.2]  # Monday reference
        obs = [(t % 7, 2.0 + 0.01 * t + eff[t % 7]) for t in range(35)]
        X = [F.weekday_design(t, d) for t, (d, _) in enumerate(obs)]
        beta = F.ols(X, [v for _, v in obs], ridge=0.0)
        self.assertAlmostEqual(beta[0], 2.0, places=6)
        self.assertAlmostEqual(beta[1], 0.01, places=6)
        for k in range(1, 7):
            self.assertAlmostEqual(beta[1 + k], eff[k], places=6)
        pred, _ = F.ols_weekday_forecast(obs, 35 % 7)
        self.assertAlmostEqual(pred, 2.0 + 0.35 + eff[0], places=6)


class SeasonalESTest(unittest.TestCase):
    def test_learns_market_day_index(self):
        m = F.fit_seasonal_es(synthetic())
        self.assertGreater(m.season[2], 1.6)            # Wednesday spike learned
        self.assertLess(max(m.season[k] for k in (0, 1, 5, 6)), 1.0)
        self.assertAlmostEqual(m.forecast(2), 0.3 * 2.0, delta=0.06)
        self.assertGreater(m.sigma, 0)
        self.assertIn(m.alpha, F.ALPHAS)
        self.assertIn(m.gamma, F.GAMMAS)

    def test_beats_naive_in_backtest(self):
        mae = F.backtest(synthetic(days=70, noise=0.1, seed=5))
        self.assertLess(mae["seasonal_es"], 0.6 * mae["naive"])
        self.assertLess(mae["seasonal_es"], mae["ses"])

    def test_online_update_tracks_level_shift(self):
        obs = synthetic(days=42)
        m = F.fit_seasonal_es(obs)
        before = m.forecast(0)
        for d in range(42, 70):  # waste doubles (new shops opened)
            m.update(d % 7, 2 * 0.3 * WEEK[d % 7])
        self.assertGreater(m.forecast(0), 1.6 * before)

    def test_ses(self):
        self.assertAlmostEqual(F.ses_forecast([1, 1, 1]), 1.0)
        self.assertAlmostEqual(F.ses_forecast([0, 1], alpha=0.5), 0.5)
        self.assertEqual(F.ses_forecast([]), 0.0)


class HoursToFullTest(unittest.TestCase):
    def test_constant_fill(self):
        # 0.18/day over an 18 h window = 1%/hour. From 50% at 00:00: 68% end of day 0,
        # 86% end of day 1, then 14 more hours after 05:00 on day 2 -> 19:00 -> 67 h.
        self.assertAlmostEqual(F.hours_to_full(0.5, [0.18] * 5), 67.0)

    def test_same_day(self):
        # 90% at 00:00, 0.36/day = 2%/h -> 5 h after 05:00 -> 10:00
        self.assertAlmostEqual(F.hours_to_full(0.9, [0.36]), 10.0)

    def test_start_mid_day(self):
        # at 12:00 with 50%, 0.36/day: 2%/h -> full at 12 + 25 h (crosses into day 1)
        h = F.hours_to_full(0.5, [0.36, 0.36], start_h=12.0)
        # day 0 adds 11 h * 2% = 22% -> 72%; day 1 needs 28% -> 14 h after 05:00 = 19:00 -> 31 h
        self.assertAlmostEqual(h, 31.0)

    def test_edges(self):
        self.assertEqual(F.hours_to_full(1.0, [0.1]), 0.0)
        self.assertIsNone(F.hours_to_full(0.1, [0.0] * 14))


if __name__ == "__main__":
    unittest.main()
