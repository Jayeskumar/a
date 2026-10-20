import math
import unittest

import _helpers  # noqa: F401
from bloodlink.config import EARTH_RADIUS_KM
from bloodlink.geo import haversine_km, travel_minutes


def law_of_cosines(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return EARTH_RADIUS_KM * math.acos(max(-1.0, min(1.0, c)))


class Haversine(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(haversine_km(11.38, 77.89, 11.38, 77.89), 0.0)

    def test_symmetry(self):
        a = haversine_km(11.664, 78.146, 11.341, 77.717)
        b = haversine_km(11.341, 77.717, 11.664, 78.146)
        self.assertAlmostEqual(a, b, places=9)

    def test_one_degree(self):
        one = EARTH_RADIUS_KM * math.pi / 180
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), one, places=6)
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), one, places=6)
        self.assertAlmostEqual(one, 111.195, places=2)

    def test_quarter_and_antipodal(self):
        self.assertAlmostEqual(haversine_km(0, 0, 90, 0), EARTH_RADIUS_KM * math.pi / 2, places=6)
        self.assertAlmostEqual(haversine_km(0, 0, 0, 180), EARTH_RADIUS_KM * math.pi, places=6)

    def test_matches_independent_formula(self):
        pairs = [(11.664, 78.146, 11.341, 77.717), (11.219, 78.167, 11.380, 77.894),
                 (13.08, 80.27, 11.0, 76.96), (-33.9, 151.2, 51.5, -0.12)]
        for p in pairs:
            with self.subTest(p=p):
                self.assertAlmostEqual(haversine_km(*p), law_of_cosines(*p), places=5)

    def test_local_distance_plausible(self):
        # Salem to Erode town centres: roughly 55-60 km straight line (approx.)
        d = haversine_km(11.664, 78.146, 11.341, 77.717)
        self.assertTrue(50 < d < 65, d)

    def test_invalid(self):
        for bad in [(91, 0, 0, 0), (0, 181, 0, 0), ("a", 0, 0, 0), (float("nan"), 0, 0, 0), (True, 0, 0, 0)]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    haversine_km(*bad)


class Travel(unittest.TestCase):
    def test_prep_only_at_zero(self):
        self.assertAlmostEqual(travel_minutes(0), 10.0)

    def test_formula(self):
        self.assertAlmostEqual(travel_minutes(10), 10 + 13 / 35 * 60, places=6)

    def test_monotonic(self):
        ts = [travel_minutes(k) for k in range(0, 60, 5)]
        self.assertEqual(ts, sorted(ts))

    def test_negative(self):
        with self.assertRaises(ValueError):
            travel_minutes(-1)


if __name__ == "__main__":
    unittest.main()
