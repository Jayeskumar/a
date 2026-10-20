import unittest

import _path  # noqa: F401
from krishimitra import fertiliser


class TestFertiliser(unittest.TestCase):
    def test_hand_computed_rice(self):
        """Rice dose 150:50:50 kg/ha; soil N 80, P 40, K 40; credits 0.4 / 0.3 / 0.3.
        deficit N = 150 - 32 = 118, P2O5 = 50 - 12 = 38, K2O = 50 - 12 = 38 kg/ha
        DAP  = 38 / 0.46 = 82.61 kg/ha  (supplies 0.18 * 82.61 = 14.87 kg N)
        Urea = (118 - 14.87) / 0.46 = 224.2 kg/ha
        MOP  = 38 / 0.60 = 63.33 kg/ha
        per acre (x 0.404686): DAP 33.4, Urea 90.7, MOP 25.6"""
        r = fertiliser.advise("rice", 80, 40, 40, 6.5, 1.0)
        self.assertEqual(r["deficit_kg_ha"], {"N": 118.0, "P2O5": 38.0, "K2O": 38.0})
        kg = {p["product"]: p["kg_per_acre"] for p in r["products"]}
        self.assertAlmostEqual(kg["dap"], 33.4, places=1)
        self.assertAlmostEqual(kg["urea"], 90.7, places=1)
        self.assertAlmostEqual(kg["mop"], 25.6, places=1)

    def test_products_per_ha_math(self):
        p = fertiliser.products_per_ha(100, 46, 60)
        self.assertAlmostEqual(p["dap"], 100.0)
        self.assertAlmostEqual(p["n_from_dap"], 18.0)
        self.assertAlmostEqual(p["urea"], (100 - 18) / 0.46)
        self.assertAlmostEqual(p["mop"], 100.0)

    def test_dap_n_exceeding_need_gives_zero_urea(self):
        p = fertiliser.products_per_ha(5, 46, 0)
        self.assertEqual(p["urea"], 0.0)

    def test_rich_soil_needs_nothing(self):
        r = fertiliser.advise("groundnut", 300, 300, 400, 7.0)
        self.assertTrue(all(p["kg_per_acre"] == 0 for p in r["products"]))
        self.assertTrue(all(v == 0 for v in r["deficit_kg_ha"].values()))

    def test_area_and_bags(self):
        r = fertiliser.advise("maize", 80, 50, 40, 7.0, 2.5)
        for p in r["products"]:
            self.assertAlmostEqual(p["kg_total"], p["kg_per_acre"] * 2.5, delta=0.15)
            self.assertAlmostEqual(p["bags_total"], p["kg_total"] / p["bag_kg"], delta=0.06)

    def test_organic_replaces_quarter_of_n(self):
        r = fertiliser.advise("rice", 80, 40, 40, 6.5)
        n_def_acre = r["deficit_kg_acre"]["N"]
        for o in r["organic"]:
            self.assertAlmostEqual(o["supplies"]["N"], 0.25 * n_def_acre, delta=0.5)

    def test_tips_and_bilingual(self):
        acid = fertiliser.advise("ragi", 40, 30, 30, 5.0)
        self.assertTrue(any("lime" in t["en"] for t in acid["tips"]))
        legume = fertiliser.advise("blackgram", 20, 40, 20, 7.0)
        self.assertTrue(any("Rhizobium" in t["en"] for t in legume["tips"]))
        self.assertIn("யூரியா", acid["summary"]["ta"])

    def test_unknown_crop(self):
        with self.assertRaises(ValueError):
            fertiliser.advise("wheatgrass", 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
