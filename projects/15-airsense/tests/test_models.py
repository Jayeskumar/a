"""Calibration regression, IDW / kriging, fault detectors, forecaster, health rules."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from airsense import calibration, faults, forecast, health, interpolate  # noqa: E402
from airsense.mathx import errors, inverse, least_squares, matvec, solve  # noqa: E402


class LinearAlgebra(unittest.TestCase):
    def test_solve_and_inverse(self):
        a = [[4.0, 1.0, 2.0], [1.0, 5.0, 1.0], [2.0, 1.0, 6.0]]
        b = [1.0, 2.0, 3.0]
        x = solve(a, b)
        for row, bv in zip(a, b):
            self.assertAlmostEqual(sum(r * xv for r, xv in zip(row, x)), bv, places=9)
        inv = inverse(a)
        for i in range(3):
            col = matvec(a, [inv[r][i] for r in range(3)])
            for j in range(3):
                self.assertAlmostEqual(col[j], 1.0 if i == j else 0.0, places=9)

    def test_singular(self):
        with self.assertRaises(ValueError):
            solve([[1, 2], [2, 4]], [1, 2])

    def test_least_squares_exact(self):
        rows = [[x, x * x % 7] for x in range(30)]
        y = [3 + 2 * r[0] - 0.5 * r[1] for r in rows]
        m = least_squares(rows, y)
        self.assertAlmostEqual(m["intercept"], 3, places=6)
        self.assertAlmostEqual(m["coef"][0], 2, places=6)
        self.assertAlmostEqual(m["coef"][1], -0.5, places=6)


class Calibration(unittest.TestCase):
    def make(self, n, kappa=0.3, gain=1.3, offset=4.0, seed=1):
        rng = random.Random(seed)
        out = []
        for i in range(n):
            ref = rng.uniform(10, 120)
            rh = rng.uniform(40, 94)
            t = rng.uniform(22, 34)
            raw = gain * ref * calibration.growth(rh, kappa) + offset + rng.gauss(0, 0.5)
            out.append((raw, rh, t, ref))
        return out

    def test_growth_factor(self):
        self.assertAlmostEqual(calibration.growth(0, 0.3), 1.0)
        self.assertAlmostEqual(calibration.growth(80, 0.33), 1 + 0.2 * 4.0, places=9)
        self.assertEqual(calibration.growth(99, 0.3), calibration.growth(95, 0.3))   # capped

    def test_recovers_kappa_and_beats_raw(self):
        train, test = self.make(150, seed=1), self.make(60, seed=2)
        res = calibration.calibrate_sensor(train, test)
        self.assertAlmostEqual(res["model"]["kappa"], 0.3, delta=0.06)
        t = res["test"]
        self.assertLess(t["hybrid"]["rmse"], 0.2 * t["raw"]["rmse"])
        self.assertLess(t["hybrid"]["rmse"], t["mlr"]["rmse"])
        self.assertGreater(t["hybrid"]["r2"], 0.97)
        # MLR coefficient on dry PM ~ 1/gain
        self.assertAlmostEqual(res["model"]["coef"][0], 1 / 1.3, delta=0.08)

    def test_apply_and_explain(self):
        m = calibration.fit(self.make(80))
        self.assertIsNone(calibration.apply(m, None, 60, 25))
        self.assertGreaterEqual(calibration.apply(m, 0.0, 60, 25), 0.0)
        e = calibration.explain(m, 80.0, 85.0, 28.0)
        total = sum(p["value"] for p in e["parts"])
        self.assertAlmostEqual(total, e["calibrated"], delta=0.1)

    def test_needs_data(self):
        with self.assertRaises(ValueError):
            calibration.fit([(1, 50, 25, 1)] * 5)


class IDW(unittest.TestCase):
    PTS = [(0.0, 0.0, 10.0), (2.0, 0.0, 30.0), (0.0, 2.0, 50.0), (3.0, 3.0, 20.0)]

    def test_exact_at_sensor(self):
        for x, y, v in self.PTS:
            self.assertEqual(interpolate.idw(self.PTS, x, y), v)

    def test_midpoint_of_two(self):
        self.assertAlmostEqual(interpolate.idw([(0, 0, 10), (2, 0, 30)], 1, 0), 20.0)

    def test_power_and_bounds(self):
        v = interpolate.idw(self.PTS, 0.4, 0.3)
        self.assertTrue(10 <= v <= 50)
        near1 = interpolate.idw(self.PTS, 0.4, 0.3, power=1)
        near3 = interpolate.idw(self.PTS, 0.4, 0.3, power=3)
        self.assertLess(abs(near3 - 10), abs(near1 - 10))   # higher power -> closer to nearest

    def test_weights_sum_to_one(self):
        w = interpolate.idw_weights(self.PTS, 0.6, 0.4)
        self.assertAlmostEqual(sum(w), 1.0)
        self.assertEqual(max(range(4), key=lambda i: w[i]), 0)

    def test_constant_field(self):
        pts = [(x, y, 42.0) for x, y, _ in self.PTS]
        self.assertAlmostEqual(interpolate.idw(pts, 1.7, 2.2), 42.0)
        loo = interpolate.idw_loo(pts)
        self.assertEqual(len(loo), 4)
        for v in loo:  # float sums differ in the last bit before Python 3.12
            self.assertAlmostEqual(v, 42.0)


class Kriging(unittest.TestCase):
    V = {"model": "exponential", "nugget": 0.0, "psill": 1.0, "range": 1.5}

    def pts(self, n=12, seed=3):
        rng = random.Random(seed)
        return [(rng.uniform(0, 10), rng.uniform(0, 8), 30 + 10 * math.sin(i)) for i in range(n)]

    def test_exact_with_zero_variance_at_data(self):
        p = self.pts()
        k = interpolate.Kriging(p, self.V, 4.0)
        for x, y, v in p:
            e, sd, w = k.predict(x, y)
            self.assertAlmostEqual(e, v, places=6)
            self.assertAlmostEqual(sd, 0.0, places=4)

    def test_weights_sum_and_variance_grows(self):
        p = self.pts()
        k = interpolate.Kriging(p, self.V, 4.0)
        e, sd_near, w = k.predict(p[0][0] + 0.05, p[0][1])
        self.assertAlmostEqual(sum(w), 1.0, places=9)
        _, sd_far, _ = k.predict(20.0, 20.0)
        self.assertGreater(sd_far, sd_near)

    def test_dubrule_loo_matches_bruteforce(self):
        p = self.pts(10)
        k = interpolate.Kriging(p, self.V, 2.0)
        fast = [v - r for (x, y, v), r in zip(p, k.loo_residuals())]
        slow = interpolate.kriging_loo_bruteforce(p, self.V, 2.0)
        for a, b in zip(fast, slow):
            self.assertAlmostEqual(a, b, places=6)

    def test_variogram_fit_recovers_range(self):
        bins = [{"h": h, "gamma": 0.2 + 0.8 * (1 - math.exp(-h / 2.0)), "n": 100}
                for h in [0.3 + 0.6 * i for i in range(12)]]
        v = interpolate.fit_variogram(bins)
        self.assertAlmostEqual(v["range"], 2.0, delta=0.15)
        self.assertAlmostEqual(v["nugget"], 0.2, delta=0.05)

    def test_grid_shapes(self):
        p = self.pts()
        g = interpolate.grid(p, "kriging", 6, 4, vario=self.V)
        self.assertEqual(len(g["values"]), 4)
        self.assertEqual(len(g["values"][0]), 6)
        self.assertEqual(len(g["sd"][0]), 6)
        g2 = interpolate.grid(p, "idw", 5, 3)
        self.assertIsNone(g2["sd"])


class FaultDetectors(unittest.TestCase):
    def test_stuck(self):
        raw = [10.1, 11.0, 12.3, 12.3, 12.3, 12.3, 12.3, 12.3, 9.0, None, 9.0, 9.0]
        self.assertEqual(faults.detect_stuck(raw, 5), [(2, 7, 12.3)])
        self.assertEqual(faults.detect_stuck([1.0, 1.0, 1.0, 1.0], 5), [])

    def network(self, n_hours=24 * 14, seed=7):
        rng = random.Random(seed)
        sensors = [{"id": "S%02d" % i, "x": (i % 4) * 1.0, "y": (i // 4) * 1.0} for i in range(12)]
        base = [30 + 15 * math.sin(2 * math.pi * t / 24) + rng.gauss(0, 2) for t in range(n_hours)]
        vals = {s["id"]: [max(1.0, b * rng.uniform(0.95, 1.05) * (1.2 if s["id"] == "S03" else 1.0))
                          for b in base] for s in sensors}
        return sensors, vals

    def test_isolated_spike_flagged_but_citywide_event_not(self):
        sensors, vals = self.network()
        vals["S05"][100] *= 6           # isolated spike
        for s in sensors:               # city-wide event (fireworks): everybody x4 for 3 h
            for t in (200, 201, 202):
                vals[s["id"]][t] *= 4
        res = faults.run(sensors, {k: list(v) for k, v in vals.items()}, vals, len(vals["S01"]))
        spikes = [(e["sensor"], e["start_hour"]) for e in res["events"] if e["type"] == "spike"]
        self.assertIn(("S05", 100), spikes)
        self.assertFalse(any(200 <= t <= 202 for _, t in spikes))

    def test_drift_detected_only_on_drifting_sensor(self):
        sensors, vals = self.network()
        n = len(vals["S01"])
        for t in range(24 * 6, n):            # S07 gain drifts +4%/day from day 6
            vals["S07"][t] *= 1 + 0.04 * (t - 24 * 6) / 24
        res = faults.run(sensors, {k: list(v) for k, v in vals.items()}, vals, n)
        drift = [e for e in res["events"] if e["type"] == "drift"]
        self.assertEqual([e["sensor"] for e in drift], ["S07"])
        self.assertGreaterEqual(drift[0]["start_hour"], 24 * 6)
        self.assertLessEqual(drift[0]["start_hour"], 24 * 12)

    def test_evaluate_counts(self):
        inj = [{"sensor": "A", "type": "spike", "start_hour": 5, "end_hour": 5},
               {"sensor": "B", "type": "spike", "start_hour": 9, "end_hour": 9}]
        det = [{"sensor": "A", "type": "spike", "start_hour": 5, "end_hour": 5},
               {"sensor": "C", "type": "spike", "start_hour": 1, "end_hour": 1}]
        ev = faults.evaluate(det, inj, 20)
        self.assertEqual(ev["spike"]["event_precision"], 0.5)
        self.assertEqual(ev["spike"]["event_recall"], 0.5)
        self.assertEqual(ev["spike"]["hour_recall"], 0.5)


class Forecaster(unittest.TestCase):
    def series(self, n=24 * 28, seed=5):
        rng = random.Random(seed)
        hods = [t % 24 for t in range(n + 24)]
        w = {"ws": [], "rain": [], "rh": [], "wdir": [], "sunday": []}
        a = 0.0
        vals = []
        for t in range(n + 24):
            ws = 2.5 + 1.2 * math.sin(2 * math.pi * (t % 24 - 9) / 24) + rng.gauss(0, 0.3)
            w["ws"].append(max(0.3, ws))
            w["rain"].append(0.0)
            w["rh"].append(70.0)
            w["wdir"].append(90.0)
            w["sunday"].append((t // 24) % 7 == 6)
            a = 0.85 * a + rng.gauss(0, 0.15)
            prof = math.log(40) + 0.4 * math.cos(2 * math.pi * (t % 24 - 21) / 24)
            if t < n:
                vals.append(math.exp(prof + a - 0.3 * math.log(max(0.3, ws) + 0.5)) - 5)
        return vals, hods, w

    def test_beats_persistence_and_shapes(self):
        vals, hods, w = self.series()
        train_end = len(vals) - 24 * 7
        res = forecast.backtest(vals, hods, w, train_end)
        model = sum(sum(h) for h in res["model"]) / sum(len(h) for h in res["model"])
        pers = sum(sum(h) for h in res["persistence"]) / sum(len(h) for h in res["persistence"])
        self.assertLess(model, pers)
        fc = forecast.SensorForecaster(vals, hods, w, len(vals))
        out = fc.forecast(len(vals) - 1, 24)
        self.assertEqual(len(out), 24)
        self.assertTrue(all(v >= 0 for v in out))
        # learns the persistence of the anomaly (true AR(1) coefficient 0.85)
        self.assertAlmostEqual(fc.model["coef"][0] + fc.model["coef"][1], 0.85, delta=0.1)

    def test_missing_data_falls_back_to_profile(self):
        vals, hods, w = self.series()
        vals = [None] * len(vals)
        fc = forecast.SensorForecaster(vals, hods, w, len(vals))
        self.assertIsNone(fc.model)
        out = fc.forecast(len(vals) - 1, 24)
        self.assertEqual(len(out), 24)

    def test_interval_quantiles(self):
        q = forecast.interval_quantiles([[-1, 0, 1, 2], [0.5]])
        self.assertLess(q[0][0], q[0][1])
        self.assertEqual(q[1], (0.5, 0.5))


class Health(unittest.TestCase):
    def test_best_run_picks_cleanest_daytime_hour(self):
        hods = list(range(24))
        aqi = [300] * 24
        aqi[3] = 20          # night: outside the run window
        aqi[7] = 60
        aqi[18] = 80
        b = health.best_run(hods, aqi)
        self.assertEqual(b["hour"], 7)
        self.assertTrue(b["ok_for_profile"])
        self.assertEqual(b["worst_aqi"], 300)

    def test_best_run_uses_upper_bound(self):
        hods = [6, 7]
        b = health.best_run(hods, [60, 62], upper=[140, 70])
        self.assertEqual(b["hour"], 7)

    def test_alerts_group_hours_by_profile(self):
        aqi = [80, 120, 130, 90, 210, 220, 60]
        labels = ["h%d" % i for i in range(7)]
        gen = health.alerts(list(range(7)), aqi, "general", labels)
        self.assertEqual(len(gen), 1)
        self.assertEqual((gen[0]["start"], gen[0]["end"], gen[0]["peak_aqi"]), ("h4", "h5", 220))
        asth = health.alerts(list(range(7)), aqi, "asthma", labels)
        self.assertEqual([(a["start"], a["end"]) for a in asth], [("h1", "h2"), ("h4", "h5")])

    def test_advice_and_profiles(self):
        a = health.advice(150, "children")
        self.assertEqual(a["category"], "Moderate")
        self.assertIn("PE", a["advice"])
        with self.assertRaises(health.ProfileError):
            health.advice(50, "astronaut")

    def test_errors_helper(self):
        e = errors([1, 2, None], [1, 4, 3])
        self.assertEqual(e["n"], 2)
        self.assertAlmostEqual(e["mae"], 1.0)


if __name__ == "__main__":
    unittest.main()
