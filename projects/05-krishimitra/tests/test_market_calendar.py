import datetime as dt
import unittest

import _path  # noqa: F401
from krishimitra import config, cropcal, market


class TestMarket(unittest.TestCase):
    day = dt.date(2026, 10, 20)

    def test_deterministic_series(self):
        a = market.price_series("rice", self.day)
        b = market.price_series("rice", self.day)
        self.assertEqual(a, b)
        # extending the date must not change history (prices depend only on the week)
        c = market.price_series("rice", self.day + dt.timedelta(weeks=4))
        self.assertEqual(a, c[:len(a)])

    def test_moving_average(self):
        self.assertEqual(market.moving_average([1, 2, 3, 4, 5], 2), [None, 1.5, 2.5, 3.5, 4.5])

    def test_ols_slope(self):
        slope, intercept = market.ols_slope([1, 3, 5, 7])
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(intercept, 1.0)

    def test_seasonal_index_recovers_peak(self):
        for crop in ("tomato", "banana", "turmeric"):
            r = market.analyse(crop, self.day)
            si = r["seasonal_index"]
            self.assertAlmostEqual(sum(si) / 12, 1.0, places=3)
            peak = si.index(max(si)) + 1
            hm = config.MARKET[crop]["high_month"]
            self.assertLessEqual(min(abs(peak - hm), 12 - abs(peak - hm)), 1)

    def test_decision_rules(self):
        for crop in config.CROPS:
            r = market.analyse(crop, self.day)
            d = r["decision"]
            self.assertIn(d["action"], ("sell", "hold"))
            self.assertLessEqual(d["weeks"], config.MARKET[crop]["max_hold"])
            self.assertLess(d["band"][0], d["band"][1])
            self.assertIn("en", d["text"])
            self.assertIn("ta", d["text"])
            if d["action"] == "hold":
                self.assertGreaterEqual(d["gain_pct"], config.MARKET_MIN_GAIN * 100)
        self.assertEqual(market.analyse("sugarcane", self.day)["decision"]["action"], "sell")

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            market.analyse("rice", dt.date(2021, 1, 1))
        with self.assertRaises(ValueError):
            market.analyse("gold", self.day)


class TestCalendar(unittest.TestCase):
    def test_stages_are_contiguous(self):
        sow = dt.date(2026, 7, 1)
        c = cropcal.calendar("rice", sow, dt.date(2026, 8, 1))
        crop_stages = [s for s in c["stages"] if s["key"] in ("initial", "development", "mid", "late")]
        for a, b in zip(crop_stages, crop_stages[1:]):
            self.assertEqual(a["end"], b["start"])
        self.assertEqual(crop_stages[0]["start"], "2026-07-01")
        self.assertEqual(c["duration_days"], sum(config.STAGE_DAYS["rice"]))
        self.assertEqual(c["days_after_sowing"], 31)
        self.assertTrue(any(s["key"] == "nursery" for s in c["stages"]))   # transplanted

    def test_perennial(self):
        c = cropcal.calendar("coconut", dt.date(2026, 6, 1))
        self.assertTrue(c["perennial"])
        self.assertFalse(any(s["key"] == "land_prep" for s in c["stages"]))


if __name__ == "__main__":
    unittest.main()
