import math
import os
import random
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stocksense import backtest, config, forecast  # noqa: E402
from stocksense.forecast import SkuContext  # noqa: E402

SEASON = [10.0, -5.0, -8.0, -3.0, 0.0, 15.0, -9.0]   # weekly pattern, sums to zero


def seasonal_series(n, level=100.0, slope=0.5, noise=0.0, seed=1):
    rng = random.Random(seed)
    return [level + slope * t + SEASON[t % 7] + noise * (rng.random() - 0.5) for t in range(n)]


class TestHoltWinters(unittest.TestCase):
    def test_recovers_trend_and_season_without_noise(self):
        y = seasonal_series(140)
        level, trend, seas, _ = forecast.hw_fit(y, 0.3, 0.1, 0.2, phi=1.0)
        self.assertAlmostEqual(trend, 0.5, places=2)
        fc = forecast.hw_forecast((level, trend, seas), len(y), 14, phi=1.0)
        truth = [100 + 0.5 * t + SEASON[t % 7] for t in range(140, 154)]
        for f, t in zip(fc, truth):
            self.assertAlmostEqual(f, t, delta=0.25)

    def test_noisy_series_beats_naive_and_tracks_season(self):
        y = seasonal_series(210, noise=8.0, seed=7)
        abg = forecast.hw_grid_search(y[:196])
        state = forecast.hw_fit(y[:196], *abg, phi=1.0)
        fc = forecast.hw_forecast(state, 196, 14, phi=1.0)
        truth = [100 + 0.5 * t + SEASON[t % 7] for t in range(196, 210)]
        mape = sum(abs(f - t) / t for f, t in zip(fc, truth)) / 14
        self.assertLess(mape, 0.03)
        # seasonal indices keep the shape: Saturday (index 5) highest, Sunday (6) lowest
        seas = state[2]
        self.assertEqual(max(range(7), key=lambda i: seas[i]), 5)
        self.assertEqual(min(range(7), key=lambda i: seas[i]), 6)

    def test_damping_limits_extrapolation(self):
        y = seasonal_series(140)
        state = forecast.hw_fit(y, 0.3, 0.1, 0.2, phi=0.9)
        far = forecast.hw_forecast(state, 140, 70, phi=0.9)
        # damped trend adds at most trend*phi/(1-phi) = ~9x the slope, never 70x
        self.assertLess(far[-1] - far[6], 0.5 * 12)


class TestBaselinesAndRegression(unittest.TestCase):
    def test_seasonal_naive_and_moving_average(self):
        y = list(range(1, 22))   # 21 days
        self.assertEqual(forecast.seasonal_naive(y, 9), [15, 16, 17, 18, 19, 20, 21, 15, 16])
        self.assertEqual(forecast.moving_average(y, 3, window=4), [19.5] * 3)

    def _ctx(self, y, start=date(2026, 2, 2)):
        dates = [start + timedelta(days=i) for i in range(len(y))]
        return SkuContext(y, [False] * len(y), [0] * len(y), dates)

    def test_regression_recovers_day_of_week_effects(self):
        start = date(2026, 2, 2)   # a Monday, no festival nearby within 6 weeks
        y = [20 + (6 if (start + timedelta(days=t)).weekday() == 5 else 0) for t in range(42)]
        ctx = self._ctx(y, start)
        beta = forecast.linreg_fit(ctx, 42, lam=1e-9)
        coef = dict(zip(forecast.REG_FEATURES, beta))
        self.assertAlmostEqual(coef["Base level"], 20, places=4)
        self.assertAlmostEqual(coef["Sat vs Mon"], 6, places=4)
        self.assertAlmostEqual(coef["Tue vs Mon"], 0, places=4)

    def test_festival_uplift_learned_and_reapplied(self):
        # flat demand of 10/day with Diwali 2025 (Oct 20) peaking at 3x (uplift 2.0)
        start = date(2025, 8, 1)
        n = 120
        dates = [start + timedelta(days=i) for i in range(n)]
        y = []
        for d in dates:
            off = (d - date(2025, 10, 20)).days
            y.append(10.0 * (1 + 2.0 * config.FEST_SHAPE.get(off, 0.0)))
        ctx = SkuContext(y, [False] * n, [0] * n, dates)
        u = ctx.festival_uplift(n)
        self.assertAlmostEqual(u["diwali"], 2.0, places=6)
        self.assertEqual(u["pongal"], 0.0)
        adj = ctx.adjusted(n, u)
        self.assertTrue(all(abs(v - 10.0) < 1e-9 for v in adj))


class TestBacktestSplits(unittest.TestCase):
    def test_rolling_origin_split_logic(self):
        splits = backtest.rolling_origin_splits(400, folds=4, horizon=14, step=14, min_train=28)
        self.assertEqual(splits, [(344, 358), (358, 372), (372, 386), (386, 400)])
        for tr, te in splits:
            self.assertEqual(te - tr, 14)          # test window = horizon
            self.assertGreaterEqual(tr, 28)        # enough training data
        self.assertEqual(splits[-1][1], 400)       # last window ends at the data end
        origins = [tr for tr, _ in splits]
        self.assertEqual(origins, sorted(origins))  # oldest first, strictly expanding windows

    def test_overlapping_and_short_series(self):
        s = backtest.rolling_origin_splits(100, folds=3, horizon=14, step=7, min_train=28)
        self.assertEqual(s, [(72, 86), (79, 93), (86, 100)])
        # folds whose training window would be too short are dropped
        s = backtest.rolling_origin_splits(60, folds=4, horizon=14, step=14, min_train=28)
        self.assertEqual(s, [(32, 46), (46, 60)])
        self.assertEqual(backtest.rolling_origin_splits(30, 4, 14, 14, 28), [])

    def test_no_future_leak_in_backtest(self):
        # spike on the very last day must not change forecasts for earlier folds
        y = seasonal_series(200, noise=4, seed=3)
        dates = [date(2026, 2, 2) + timedelta(days=i) for i in range(200)]
        a = backtest.backtest_sku(SkuContext(y, [False] * 200, [0] * 200, dates), 200)
        y2 = list(y)
        y2[-1] = 10000.0
        b = backtest.backtest_sku(SkuContext(y2, [False] * 200, [0] * 200, dates), 200)
        rows_a = [r for r in a["holdout_naive_pairs"]][:-1]
        rows_b = [r for r in b["holdout_naive_pairs"]][:-1]
        self.assertEqual(rows_a, rows_b)
        self.assertEqual(a["hw_params"], b["hw_params"])   # tuned on the oldest training window only

    def test_metrics_and_selection(self):
        m = backtest.metrics([10, 20, 0], [12, 18, 0])
        self.assertAlmostEqual(m["mape"], 100 * (0.2 + 0.1) / 2, places=6)
        self.assertAlmostEqual(m["smape"], 100 * (2 * 2 / 22 + 2 * 2 / 38) / 2, places=2)
        self.assertAlmostEqual(m["mae"], 4 / 3, places=3)
        self.assertEqual(backtest.choose({"snaive": {"smape": 30, "mape": 30}, "hw": {"smape": 20, "mape": 25},
                                          "ma": {"smape": 20, "mape": 22}}), "ma")   # tie -> simpler model

    def test_selection_prefers_seasonal_models_on_seasonal_data(self):
        y = seasonal_series(200, slope=0.0, noise=2, seed=5)
        dates = [date(2026, 2, 2) + timedelta(days=i) for i in range(200)]
        res = backtest.backtest_sku(SkuContext(y, [False] * 200, [0] * 200, dates), 200)
        self.assertIn(res["chosen"], ("hw", "linreg", "snaive"))
        self.assertLess(res["models"][res["chosen"]]["smape"], res["models"]["ma"]["smape"])
        self.assertTrue(math.isfinite(res["sigma"]) and res["sigma"] > 0)


if __name__ == "__main__":
    unittest.main()
