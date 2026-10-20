import unittest

import _path  # noqa: F401
from agrisky import config, field, indices


class TestField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = field.generate(42)

    def test_shape_and_flights(self):
        self.assertEqual(len(self.data["flights"]), len(config.FLIGHT_DAYS))
        for f in self.data["flights"]:
            for b in config.BANDS:
                self.assertEqual(len(f["bands"][b]), field.W * field.H)
                self.assertTrue(all(0 < v < 1 for v in f["bands"][b]))

    def test_deterministic_and_seed_dependent(self):
        again = field.generate(42)
        self.assertEqual(again["flights"][2]["bands"]["nir"], self.data["flights"][2]["bands"]["nir"])
        other = field.generate(7)
        self.assertNotEqual(other["flights"][2]["bands"]["nir"], self.data["flights"][2]["bands"]["nir"])

    def test_furniture(self):
        t = self.data["flights"][0]["truth"]
        W = field.W
        soil, water = config.CLASSES.index("soil"), config.CLASSES.index("water")
        self.assertEqual(t[0], soil)                                  # corner bund
        self.assertEqual(t[1 * W + 50], water)                        # channel row
        self.assertEqual(t[40 * W + config.INNER_BUND_X], soil)       # inner bund

    def test_all_scenarios_present(self):
        last = self.data["flights"][-1]["truth"]
        for c in config.CLASSES:
            self.assertGreater(last.count(config.CLASSES.index(c)), 50, c)

    def test_pest_grows_every_week(self):
        p = config.CLASSES.index("pest")
        areas = [f["truth"].count(p) for f in self.data["flights"]]
        self.assertTrue(all(b > a for a, b in zip(areas, areas[1:])), areas)

    def test_spectral_signatures(self):
        f = self.data["flights"][-1]
        idx = indices.compute_all(f["bands"])

        def mean(key, cls, src=None):
            c = config.CLASSES.index(cls)
            arr = (src or idx)[key]
            vals = [arr[i] for i, t in enumerate(f["truth"]) if t == c]
            return sum(vals) / len(vals)
        self.assertGreater(mean("ndvi", "healthy"), 0.75)
        self.assertLess(mean("ndvi", "soil"), 0.35)
        self.assertGreater(mean("ndwi", "water"), 0.0)
        # pest removes NIR; nitrogen deficiency mainly hits the red-edge index
        self.assertLess(mean("nir", "pest", f["bands"]), 0.7 * mean("nir", "healthy", f["bands"]))
        self.assertGreater(mean("nir", "nitrogen", f["bands"]), 0.85 * mean("nir", "healthy", f["bands"]))
        self.assertLess(mean("ndre", "nitrogen"), 0.8 * mean("ndre", "healthy"))

    def test_control_field_has_no_pest(self):
        ctrl = field.generate(42, pest=False)
        p = config.CLASSES.index("pest")
        self.assertTrue(all(f["truth"].count(p) == 0 for f in ctrl["flights"]))

    def test_front_radius_linear(self):
        lay = self.data["layout"]
        r0, r7 = field.pest_front_radius(lay, 0), field.pest_front_radius(lay, 7)
        self.assertAlmostEqual(r7 - r0, 7 * lay["pest_speed"])


if __name__ == "__main__":
    unittest.main()
