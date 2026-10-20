import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from wattwise import anomaly, carbon, config, dataset, forecast, leaderboard, solar, whatif  # noqa: E402
from wattwise.stats import mad, median, mape, percentile, solve, wape  # noqa: E402

DS = dataset.generate()


class StatsTests(unittest.TestCase):
    def test_median_mad_percentile(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([4, 1, 2, 3]), 2.5)
        self.assertEqual(mad([1, 2, 3, 4, 100]), 1)
        self.assertAlmostEqual(percentile([0, 10], 0.25), 2.5)

    def test_solve_matches_known_solution(self):
        a = [[2.0, 1.0, -1.0], [-3.0, -1.0, 2.0], [-2.0, 1.0, 2.0]]
        x = solve(a, [8.0, -11.0, -3.0])
        for got, want in zip(x, [2.0, 3.0, -1.0]):
            self.assertAlmostEqual(got, want, places=9)

    def test_solve_singular(self):
        with self.assertRaises(ValueError):
            solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def test_mape_wape(self):
        self.assertAlmostEqual(mape([10, 20], [11, 18]), 10.0)
        self.assertAlmostEqual(wape([10, 30], [12, 30]), 5.0)
        self.assertEqual(mape([0.1], [5]), 0.0)  # below floor is ignored


class DatasetTests(unittest.TestCase):
    def test_deterministic(self):
        again = dataset.generate()
        self.assertEqual(DS.loads, again.loads)
        self.assertEqual(DS.temps, again.temps)
        self.assertNotEqual(DS.loads["admin"], dataset.generate(seed=7).loads["admin"])

    def test_shape_and_patterns(self):
        self.assertEqual(DS.n_hours, 56 * 24)
        self.assertEqual(set(DS.loads), set(dataset.BUILDING_IDS))
        self.assertEqual(len(DS.forecast_temps), 168)
        lab = DS.loads["cse_lab"]
        # weekday 11 AM much busier than 3 AM for the lab block
        day = [lab[d * 24 + 11] for d in range(56) if d % 7 < 5]
        night = [lab[d * 24 + 3] for d in range(56) if d % 7 < 5]
        self.assertGreater(median(day), 5 * median(night))
        self.assertTrue(all(v >= 0 for s in DS.loads.values() for v in s))

    def test_holiday_is_sunday_like(self):
        self.assertEqual(dataset.daytype_of(datetime(2026, 10, 2).date()), "sunday")

    def test_save_load_roundtrip(self):
        tmp = tempfile.mkdtemp()
        try:
            dataset.save(DS, tmp)
            back = dataset.load(tmp)
            self.assertEqual(back.loads, DS.loads)
            self.assertEqual(back.timestamps, DS.timestamps)
            self.assertEqual(len(back.events), len(DS.events))
        finally:
            shutil.rmtree(tmp)


class ForecastTests(unittest.TestCase):
    def _synthetic(self, n_days=35, waste=False):
        rng = random.Random(1)
        start = datetime(2026, 1, 5)  # Monday
        ts = [start + timedelta(hours=i) for i in range(n_days * 24)]
        temps = [28 + 4 * math.cos(2 * math.pi * (t.hour - 14) / 24) + rng.gauss(0, 1) for t in ts]
        y = []
        for t, tc in zip(ts, temps):
            occ = 1.0 if (t.weekday() < 5 and 9 <= t.hour < 17) else 0.0
            v = 5 + 30 * occ + 2.0 * occ * max(0, tc - 24)
            y.append(v)
        if waste:
            for i in range(100, 110):
                y[i] += 40
        return ts, temps, y

    def test_recovers_exact_linear_signal(self):
        ts, temps, y = self._synthetic()
        m = forecast.LinearForecaster(ridge=1e-6, robust_z=None, half_life_days=None).fit(ts, temps, y)
        pred = m.predict(ts, temps)
        self.assertLess(mape(y, pred), 0.5)
        # learned weather slope for a weekday 1 PM should be ~2 kWh per degC
        k = forecast.N_CAT + 0 * 24 + 13
        self.assertAlmostEqual(m.coef[k], 2.0, places=1)

    def test_robust_fit_ignores_waste(self):
        ts, temps, y = self._synthetic(waste=True)
        m = forecast.LinearForecaster(ridge=1e-6).fit(ts, temps, y)
        self.assertGreaterEqual(m.trimmed, 10)
        pred = m.predict(ts[100:110], temps[100:110])
        clean = self._synthetic()[2][100:110]
        self.assertLess(mape(clean, pred), 2.0)

    def test_explain_adds_up(self):
        ts, temps, y = self._synthetic()
        m = forecast.LinearForecaster().fit(ts, temps, y)
        e = m.explain(ts[13], temps[13])
        self.assertAlmostEqual(e["calendar_baseline_kwh"] + e["weather_effect_kwh"], e["forecast_kwh"], places=1)

    def test_holt_winters_constant_series(self):
        y = [float(h % 24) for h in range(24 * 21)]
        hw = forecast.fit_holt_winters(y, season=24)
        fc = hw.forecast(24)
        for h, v in enumerate(fc):
            self.assertAlmostEqual(v, float(h % 24), places=3)

    def test_backtest_on_campus_beats_baselines(self):
        r = forecast.backtest(DS, "admin")
        self.assertEqual(len(r["predicted"]), 168)
        self.assertLess(r["mape"]["regression"], 10.0)
        self.assertLess(r["mape"]["regression"], r["mape"]["seasonal_naive"])

    def test_forecast_next_week(self):
        f = forecast.forecast_next_week(DS, "library")
        self.assertEqual(len(f["predicted"]), 168)
        self.assertGreater(f["total_kwh"], 0)
        self.assertTrue(f["timestamps"][0] > DS.timestamps[-1].isoformat())


class AnomalyTests(unittest.TestCase):
    def test_robust_z(self):
        self.assertAlmostEqual(anomaly.robust_z(10, 10, 1), 0)
        self.assertGreater(anomaly.robust_z(20, 3, 0.1), 3.5)
        # MAD floor prevents division blow-up on flat data
        self.assertLess(anomaly.robust_z(10.2, 10, 0.0), 3.5)

    def test_detects_injected_spike_with_reason(self):
        start = datetime(2026, 1, 5)
        ts = [start + timedelta(hours=i) for i in range(8 * 168)]
        rng = random.Random(3)
        y = [3 + rng.gauss(0, 0.1) + (20 if (t.weekday() < 5 and 9 <= t.hour < 17) else 0) for t in ts]
        # 2-6 AM on the 3rd Sunday: +15 kW
        s = 2 * 168 + 6 * 24 + 2
        for i in range(s, s + 4):
            y[i] += 15
        _, events = anomaly.detect(ts, y, "cse_lab")
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((e["start_index"], e["end_index"]), (s, s + 3))
        self.assertAlmostEqual(e["wasted_kwh"], 60, delta=2)
        self.assertEqual(e["rule"], "after_hours")
        self.assertIn("CSE Lab Block drew", e["reason"])
        self.assertIn("AM Sun", e["reason"])
        self.assertAlmostEqual(e["cost_inr"], e["wasted_kwh"] * config.TARIFF_INR_PER_KWH, delta=8)

    def test_single_hour_blip_is_ignored(self):
        start = datetime(2026, 1, 5)
        ts = [start + timedelta(hours=i) for i in range(8 * 168)]
        y = [3.0] * len(ts)
        y[500] = 30.0
        self.assertEqual(anomaly.detect(ts, y, "admin")[1], [])

    def test_campus_precision_recall(self):
        det = anomaly.detect_all(DS)
        ev = anomaly.evaluate(det, DS.events, DS.n_hours)
        self.assertGreaterEqual(ev["event_precision"], 0.9)
        self.assertGreaterEqual(ev["event_recall"], 0.8)
        self.assertEqual(ev["events_true"], len(dataset.WASTE_EVENTS))


class SolarTests(unittest.TestCase):
    def test_roof_limited_plan(self):
        p = solar.plan(400, monthly_kwh=20000)
        self.assertEqual(p["kwp"], 30.0)  # 400 * 0.75 / 10
        self.assertEqual(p["limited_by"], "roof area")
        self.assertEqual(p["annual_generation_kwh"], round(30 * config.SOLAR_YIELD_KWH_PER_KWP_YEAR))
        capex = 30 * config.SOLAR_COST_INR_PER_KWP
        saving = 30 * config.SOLAR_YIELD_KWH_PER_KWP_YEAR * config.TARIFF_INR_PER_KWH \
            - capex * config.SOLAR_OM_FRACTION_PER_YEAR
        self.assertAlmostEqual(p["simple_payback_years"], round(capex / saving, 1))
        self.assertEqual(len(p["cashflow"]), 25)

    def test_demand_limited_and_bill_input(self):
        p = solar.plan(10000, monthly_bill_inr=8000, tariff=8)
        self.assertEqual(p["inputs"]["monthly_kwh"], 1000)
        self.assertAlmostEqual(p["kwp"], round(12000 / config.SOLAR_YIELD_KWH_PER_KWP_YEAR, 1))
        self.assertTrue(p["limited_by"].startswith("annual consumption"))
        self.assertLessEqual(p["coverage_pct"], 100.5)

    def test_co2_and_degradation(self):
        p = solar.plan(1000, monthly_kwh=50000)
        self.assertAlmostEqual(p["co2_avoided_t_per_year"],
                               round(p["annual_generation_kwh"] * config.GRID_EMISSION_FACTOR_KG_PER_KWH / 1000, 2), places=1)
        gens = [c["generation_kwh"] for c in p["cashflow"]]
        self.assertTrue(all(a >= b for a, b in zip(gens, gens[1:])))
        self.assertLess(p["lifetime_generation_kwh"], 25 * p["annual_generation_kwh"])

    def test_validation(self):
        for bad in [dict(roof_area_m2=-1, monthly_kwh=10), dict(roof_area_m2="x", monthly_kwh=10),
                    dict(roof_area_m2=100), dict(roof_area_m2=100, monthly_kwh=10, tariff=500)]:
            with self.assertRaises(solar.SolarInputError):
                solar.plan(**bad)


class CarbonWhatIfLeaderboardTests(unittest.TestCase):
    def test_carbon(self):
        self.assertAlmostEqual(carbon.co2_kg(1000), 1000 * config.GRID_EMISSION_FACTOR_KG_PER_KWH)
        f = carbon.footprint(1000, 30)
        self.assertEqual(f["annual_kwh"], round(1000 * 365 / 30))
        self.assertEqual(carbon.trees_equivalent(config.TREE_KG_CO2_PER_YEAR), 1)

    def test_whatif_zero_levers_is_zero(self):
        r = whatif.simulate(DS)
        self.assertEqual(r["monthly_saving_kwh"], 0)

    def test_whatif_monotone_and_no_double_count(self):
        a = whatif.simulate(DS, ac_setpoint_delta=1)
        b = whatif.simulate(DS, ac_setpoint_delta=2)
        self.assertGreater(b["monthly_saving_kwh"], a["monthly_saving_kwh"])
        full = whatif.simulate(DS, 4, True, 21, 100, 100)
        self.assertLess(full["monthly_saving_kwh"], full["monthly_baseline_kwh"])
        hostel = [x for x in full["buildings"] if x["building"] == "hostel_a"][0]
        self.assertEqual(hostel["saving_kwh"]["auto_off"], 0)
        with self.assertRaises(whatif.WhatIfError):
            whatif.simulate(DS, ac_setpoint_delta=10)

    def test_leaderboard(self):
        lb = leaderboard.compute(DS, anomaly.detect_all(DS))
        rows = lb["rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual([r["rank"] for r in rows], list(range(1, 7)))
        pcts = [r["saving_pct"] for r in rows]
        self.assertEqual(pcts, sorted(pcts, reverse=True))
        self.assertIn("Green Champion", rows[0]["badges"])
        # the campaign building (10% cut) should win
        self.assertEqual(rows[0]["building"], "hostel_b")


if __name__ == "__main__":
    unittest.main()
