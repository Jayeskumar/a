import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from airsense import aqi as A  # noqa: E402
from airsense import config as C  # noqa: E402


def rnd(p, c):
    return A.round_half_up(A.sub_index(p, c))


class Pm25Boundaries(unittest.TestCase):
    """Every published PM2.5 breakpoint (CPCB NAQI, 24-h, ug/m3)."""
    CASES = [(0, 0), (30, 50), (31, 51), (60, 100), (61, 101), (90, 200), (91, 201),
             (120, 300), (121, 301), (250, 400), (251, 401), (380, 500)]

    def test_each_boundary(self):
        for c, expected in self.CASES:
            self.assertEqual(rnd("pm25", c), expected, "PM2.5 %s" % c)

    def test_categories_at_boundaries(self):
        names = ["Good", "Good", "Satisfactory", "Satisfactory", "Moderate", "Moderate", "Poor",
                 "Poor", "Very Poor", "Very Poor", "Severe", "Severe"]
        for (c, _), name in zip(self.CASES, names):
            self.assertEqual(A.category(A.sub_index("pm25", c))["name"], name, "PM2.5 %s" % c)

    def test_interior_formula(self):
        # I = (100-51)/(60-31) * (45-31) + 51 = 74.66
        self.assertAlmostEqual(A.sub_index("pm25", 45), 49 / 29 * 14 + 51, places=6)
        self.assertAlmostEqual(A.sub_index("pm25", 105), 201 + 99 / 29 * 14, places=6)

    def test_above_table_capped(self):
        self.assertEqual(A.sub_index("pm25", 999), 500)


class Pm10Boundaries(unittest.TestCase):
    CASES = [(0, 0), (50, 50), (51, 51), (100, 100), (101, 101), (250, 200), (251, 201),
             (350, 300), (351, 301), (430, 400), (431, 401), (510, 500)]

    def test_each_boundary(self):
        for c, expected in self.CASES:
            self.assertEqual(rnd("pm10", c), expected, "PM10 %s" % c)

    def test_interior(self):
        self.assertAlmostEqual(A.sub_index("pm10", 175), 101 + 99 / 149 * 74, places=6)


class AllPollutants(unittest.TestCase):
    def test_every_row_start_and_end(self):
        for p, rows in C.BREAKPOINTS.items():
            for c_lo, c_hi, i_lo, i_hi in rows:
                self.assertAlmostEqual(A.sub_index(p, c_lo), i_lo, places=9, msg="%s %s" % (p, c_lo))
                self.assertAlmostEqual(A.sub_index(p, c_hi), i_hi, places=9, msg="%s %s" % (p, c_hi))

    def test_spot_values(self):
        self.assertEqual(rnd("co", 1.0), 50)
        self.assertEqual(rnd("co", 1.1), 51)
        self.assertEqual(rnd("co", 10), 200)
        self.assertEqual(rnd("o3", 168), 200)
        self.assertEqual(rnd("o3", 169), 201)
        self.assertEqual(rnd("so2", 380), 200)
        self.assertEqual(rnd("no2", 81), 101)
        self.assertEqual(rnd("nh3", 400), 100)

    def test_continuous_and_monotone(self):
        for p, rows in C.BREAKPOINTS.items():
            top = rows[-1][1]
            prev = -1.0
            steps = 4000
            for k in range(steps + 1):
                c = top * k / steps
                v = A.sub_index(p, c)
                self.assertGreaterEqual(v, prev - 1e-9, "%s not monotone at %s" % (p, c))
                if k:
                    self.assertLess(v - prev, 2.0, "%s jumps at %s" % (p, c))
                prev = v

    def test_gap_between_rows(self):
        v = A.sub_index("pm25", 30.5)
        self.assertTrue(50 < v < 51)
        self.assertEqual(A.category(v)["name"], "Satisfactory")   # 50.5 rounds up to 51

    def test_bad_input(self):
        with self.assertRaises(A.AQIError):
            A.sub_index("pm25", -1)
        with self.assertRaises(A.AQIError):
            A.sub_index("pm25", float("nan"))
        with self.assertRaises(A.AQIError):
            A.sub_index("lead", 1)
        with self.assertRaises(A.AQIError):
            A.sub_index("pm25", "abc")
        self.assertIsNone(A.sub_index("pm25", None))


class OverallRule(unittest.TestCase):
    def test_max_and_prominent(self):
        r = A.compute({"pm25": 84, "pm10": 160, "no2": 92})
        self.assertEqual(r["aqi"], 180)
        self.assertEqual(r["prominent"], ["pm25"])
        self.assertTrue(r["valid"])
        self.assertEqual(r["category"], "Moderate")

    def test_needs_three_pollutants(self):
        r = A.compute({"pm25": 84, "pm10": 160})
        self.assertFalse(r["valid"])
        self.assertIn("at least 3", r["reason"])
        self.assertEqual(r["aqi"], 180)   # still reported as indicative

    def test_needs_pm(self):
        r = A.compute({"no2": 50, "so2": 20, "co": 1.5, "o3": 60})
        self.assertFalse(r["valid"])
        self.assertIn("PM2.5 or PM10", r["reason"])

    def test_pm10_only_counts(self):
        self.assertTrue(A.compute({"pm10": 80, "no2": 50, "so2": 20})["valid"])

    def test_empty(self):
        r = A.compute({})
        self.assertIsNone(r["aqi"])
        self.assertFalse(r["valid"])

    def test_unknown_pollutant(self):
        with self.assertRaises(A.AQIError):
            A.compute({"pm1": 3})


class Averaging(unittest.TestCase):
    def test_24h_needs_16_hours(self):
        vals = [40.0] * 15 + [None] * 9
        self.assertIsNone(A.average_24h(vals)[-1])
        vals = [40.0] * 16 + [None] * 8
        self.assertAlmostEqual(A.average_24h(vals)[-1], 40.0)

    def test_24h_is_trailing(self):
        vals = [10.0] * 24 + [70.0] * 24
        out = A.average_24h(vals)
        self.assertAlmostEqual(out[23], 10.0)
        self.assertAlmostEqual(out[35], (12 * 10 + 12 * 70) / 24)
        self.assertAlmostEqual(out[47], 70.0)

    def test_8h_max_rule(self):
        vals = [1.0] * 10 + [5.0] * 8 + [1.0] * 6
        out = A.daily_max_8h(vals)
        self.assertAlmostEqual(out[-1], 5.0)
        self.assertEqual(A.averaged("co", vals), out)
        self.assertEqual(A.averaged("pm25", vals), A.average_24h(vals))

    def test_hourly_indicative(self):
        self.assertEqual(A.hourly_indicative(84, 160), 180)
        self.assertEqual(A.hourly_indicative(None, 100), 100)
        self.assertIsNone(A.hourly_indicative(None, None))

    def test_round_half_up(self):
        self.assertEqual(A.round_half_up(50.5), 51)
        self.assertEqual(A.round_half_up(100.49), 100)
        self.assertTrue(math.isclose(A.sub_index("pm25", 0.0), 0.0))


if __name__ == "__main__":
    unittest.main()
