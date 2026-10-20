import datetime as dt
import math
import unittest

import _path  # noqa: F401
from krishimitra import config, irrigation as irr
from krishimitra import weather


class TestFAO56Radiation(unittest.TestCase):
    def test_fao56_example_8(self):
        """FAO-56 Example 8: 20 deg S on 3 September (J = 246).
        Hand-computed in the guide: dr = 0.985, dec = 0.120 rad, ws = 1.527 rad,
        Ra = 32.2 MJ m-2 day-1."""
        lat, doy = -20.0, 246
        self.assertAlmostEqual(irr.inverse_distance(doy), 0.985, places=3)
        self.assertAlmostEqual(irr.declination(doy), 0.120, places=3)
        ws = irr.sunset_hour_angle(math.radians(lat), irr.declination(doy))
        self.assertAlmostEqual(ws, 1.527, places=3)
        self.assertAlmostEqual(irr.extraterrestrial_radiation(lat, doy), 32.2, places=1)

    def test_equator_equinox_symmetry(self):
        # near the equinox Ra is (almost) symmetric about the equator
        a = irr.extraterrestrial_radiation(11.0, 80)
        b = irr.extraterrestrial_radiation(-11.0, 80)
        self.assertLess(abs(a - b), 0.6)

    def test_polar_night_is_zero(self):
        self.assertEqual(irr.extraterrestrial_radiation(-80.0, 172), 0.0)


class TestHargreaves(unittest.TestCase):
    def test_hand_computed(self):
        # Tmin 22, Tmax 34, Ra 32.2: 0.0023*(28+17.8)*sqrt(12)*0.408*32.2
        expected = 0.0023 * 45.8 * math.sqrt(12) * 0.408 * 32.2
        self.assertAlmostEqual(expected, 4.794, places=3)
        self.assertAlmostEqual(irr.hargreaves_et0(22, 34, 32.2), expected, places=9)

    def test_swapped_and_equal_temperatures(self):
        self.assertAlmostEqual(irr.hargreaves_et0(34, 22, 32.2), irr.hargreaves_et0(22, 34, 32.2))
        self.assertEqual(irr.hargreaves_et0(25, 25, 30), 0.0)


class TestKcAndRain(unittest.TestCase):
    def test_kc_curve(self):
        l1, l2, l3, l4 = config.STAGE_DAYS["maize"]
        kc_ini, kc_mid, kc_end = config.KC["maize"]
        self.assertEqual(irr.crop_stage("maize", 0), ("initial", kc_ini))
        stage, kc = irr.crop_stage("maize", l1 + l2 / 2.0)
        self.assertEqual(stage, "development")
        self.assertAlmostEqual(kc, (kc_ini + kc_mid) / 2)
        self.assertEqual(irr.crop_stage("maize", l1 + l2 + 1), ("mid", kc_mid))
        self.assertEqual(irr.crop_stage("maize", l1 + l2 + l3 + l4)[0], "harvested")
        self.assertEqual(irr.crop_stage("maize", -3), (None, 0.0))
        self.assertEqual(irr.crop_stage("coconut", 400)[0], "initial")   # perennial wraps

    def test_effective_rain(self):
        self.assertEqual(irr.effective_rain(4.9), 0.0)
        self.assertAlmostEqual(irr.effective_rain(20), 16.0)


class TestPlan(unittest.TestCase):
    sow = dt.date(2026, 9, 1)
    start = dt.date(2026, 10, 20)

    def test_dry_week_needs_irrigation(self):
        fc = [{"tmax": 35, "tmin": 22, "rain": 0}] * 7
        p = irr.plan("maize", 11.0, self.sow, self.start, fc, "red", "furrow", 2.0)
        self.assertTrue(any(d["irrigate"] for d in p["days"]))
        d = [x for x in p["days"] if x["irrigate"]][0]
        self.assertGreaterEqual(d["net_mm"], config.SOIL_TYPES["red"]["refill_mm"])
        self.assertAlmostEqual(d["gross_mm"], d["net_mm"] / 0.70, delta=0.15)
        # 1 mm over 1 acre = 4046.86 litres (gross_mm is rounded to 0.1 mm in the output)
        self.assertAlmostEqual(d["litres_per_acre"], d["gross_mm"] * 4046.86, delta=0.05 * 4046.86 + 1)
        self.assertAlmostEqual(p["week"]["litres_total"], 2 * p["week"]["litres_per_acre"], delta=2)

    def test_wet_week_needs_none(self):
        fc = [{"tmax": 30, "tmin": 23, "rain": 25}] * 7
        p = irr.plan("maize", 11.0, self.sow, self.start, fc, "red", "furrow")
        self.assertFalse(any(d["irrigate"] for d in p["days"]))
        self.assertEqual(p["week"]["litres_per_acre"], 0)

    def test_drip_irrigates_daily(self):
        fc = [{"tmax": 34, "tmin": 22, "rain": 0}] * 7
        p = irr.plan("tomato", 11.0, self.sow, self.start, fc, "red", "drip")
        self.assertTrue(all(d["irrigate"] for d in p["days"]))

    def test_rice_includes_percolation(self):
        fc = [{"tmax": 33, "tmin": 23, "rain": 0}]
        sow = self.start - dt.timedelta(days=60)
        p = irr.plan("rice", 10.8, sow, self.start, fc, "alluvial", "flood")
        d = p["days"][0]
        self.assertAlmostEqual(d["etc"], round(d["kc"] * d["et0"] + config.PADDY_PERCOLATION_MM, 2), places=1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            irr.plan("rice", 11, self.sow, self.start, [], "moon", "flood")
        with self.assertRaises(ValueError):
            irr.plan("rice", 11, self.sow, self.start, [], "red", "teleport")

    def test_synth_forecast_deterministic(self):
        a = weather.synth_forecast(11.38, self.start)
        b = weather.synth_forecast(11.38, self.start)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 7)


if __name__ == "__main__":
    unittest.main()
