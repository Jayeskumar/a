import unittest

import _path  # noqa: F401
from agrisky import classify, config
from agrisky.pipeline import Store

REF = {"ndvi": 0.82, "gndvi": 0.66, "ndre": 0.32, "savi": 0.64, "ndwi": -0.66, "red": 0.045,
       "nir": 0.50, "green": 0.10, "rededge": 0.26, "dndvi": 0.02}


def zone(**kw):
    z = dict(REF)
    z.update(kw)
    return z


class TestRules(unittest.TestCase):
    def test_water(self):
        r = classify.classify_zone(zone(ndwi=0.3, ndvi=-0.2), REF)
        self.assertEqual(r["label"], "water")

    def test_soil(self):
        r = classify.classify_zone(zone(ndvi=0.27, ndwi=-0.4), REF)
        self.assertEqual(r["label"], "soil")

    def test_waterlogging_needs_dark_red(self):
        r = classify.classify_zone(zone(ndvi=0.72, ndwi=-0.50, red=0.05, nir=0.33), REF)
        self.assertEqual(r["label"], "waterlogging")
        # same wetness but bright red = exposed soil / damage, not standing water
        r2 = classify.classify_zone(zone(ndvi=0.55, ndwi=-0.50, red=0.10, nir=0.30), REF)
        self.assertEqual(r2["label"], "pest")

    def test_pest_and_spreading(self):
        r = classify.classify_zone(zone(ndvi=0.53, ndwi=-0.6, red=0.095, nir=0.30, dndvi=-0.10),
                                   REF, weeks=1.0)
        self.assertEqual(r["label"], "pest")
        self.assertTrue(r["spreading"])
        self.assertAlmostEqual(r["ndvi_rate_week"], -0.12)
        self.assertTrue(any(t["rule"] == "pest" and t["passed"] for t in r["trace"]))

    def test_nitrogen(self):
        r = classify.classify_zone(zone(ndvi=0.67, ndwi=-0.6, red=0.09, nir=0.46, ndre=0.21), REF)
        self.assertEqual(r["label"], "nitrogen")
        self.assertIn("nitrogen", r["why"])

    def test_healthy(self):
        r = classify.classify_zone(zone(ndvi=0.81, nir=0.49, ndre=0.31), REF)
        self.assertEqual(r["label"], "healthy")
        self.assertGreaterEqual(r["confidence"], 0.55)

    def test_percentile(self):
        self.assertEqual(classify.median([3, 1, 2]), 2)
        self.assertAlmostEqual(classify.percentile([0, 10], 75), 7.5)

    def test_confusion_hand(self):
        t = ["healthy", "healthy", "pest", "pest", "soil"]
        p = ["healthy", "pest", "pest", "pest", "soil"]
        c = classify.confusion(t, p)
        self.assertAlmostEqual(c["accuracy"], 0.8)
        self.assertAlmostEqual(c["per_class"]["pest"]["precision"], 2 / 3, places=4)
        self.assertAlmostEqual(c["per_class"]["healthy"]["recall"], 0.5)


class TestOnGeneratedField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        cls.als = cls.store.all_analyses(42)

    def test_accuracy_vs_ground_truth(self):
        for a in self.als:
            self.assertGreater(a["accuracy"]["accuracy"], 0.97)

    def test_final_flight_finds_every_condition(self):
        labels = {z["label"] for z in self.als[-1]["zones"]}
        for c in config.CLASSES:
            self.assertIn(c, labels)
        pest = [z for z in self.als[-1]["zones"] if z["label"] == "pest"]
        self.assertTrue(any(z["spreading"] for z in pest))

    def test_kmeans_converged(self):
        for a in self.als:
            self.assertTrue(a["kmeans"]["converged"])
            self.assertEqual(len(a["kmeans"]["centroids"]), config.KMEANS_K)

    def test_zone_stats_consistent(self):
        a = self.als[-1]
        self.assertEqual(sum(z["cells"] for z in a["zones"]), len(a["cell_class"]))
        self.assertAlmostEqual(sum(z["pct_field"] for z in a["zones"]), 100.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
