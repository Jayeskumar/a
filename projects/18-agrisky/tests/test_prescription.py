import unittest

import _path  # noqa: F401
from agrisky import config, prescription, segment
from agrisky.field import W, H
from agrisky.pipeline import Store


class TestPrescription(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        cls.a = cls.store.analysis(42, 4)
        cls.p = prescription.build(cls.a, "pesticide")
        cls.u = prescription.build(cls.a, "urea")

    def test_pesticide_targets_pest_plus_ring_only(self):
        cc = self.a["cell_class"]
        pest = [c == "pest" for c in cc]
        ring = segment.dilate(pest, W, H, config.PEST_BUFFER_M)
        blocked = prescription.no_spray_mask(cc)
        for i, r in enumerate(self.p["cell_rate"]):
            expect = ring[i] and cc[i] in config.CROP_CLASSES and not blocked[i]
            self.assertEqual(r > 0, expect)
            if r:
                self.assertEqual(r, config.PESTICIDE_PRODUCT_L_HA)    # never under-dosed

    def test_never_near_water(self):
        blocked = prescription.no_spray_mask(self.a["cell_class"])
        for rx in (self.p, self.u):
            self.assertFalse(any(r > 0 and b for r, b in zip(rx["cell_rate"], blocked)))

    def test_savings_arithmetic(self):
        for rx, price in ((self.p, config.PESTICIDE_PRICE_RS_PER_L), (self.u, config.UREA_PRICE_RS_PER_KG)):
            u, v, s = rx["uniform"]["amount"], rx["vra"]["amount"], rx["savings"]
            self.assertAlmostEqual(s["amount"], u - v, places=2)
            self.assertAlmostEqual(s["pct"], 100 * (u - v) / u, places=0)
            self.assertAlmostEqual(s["rs"], (u - v) * price, delta=1)
            self.assertGreater(s["pct"], 80)
        crop_ha = self.p["crop_area_m2"] / 1e4
        self.assertAlmostEqual(self.p["uniform"]["amount"], config.PESTICIDE_PRODUCT_L_HA * crop_ha, places=3)

    def test_urea_only_on_nitrogen_and_held_on_waterlogging(self):
        cc = self.a["cell_class"]
        for i, r in enumerate(self.u["cell_rate"]):
            if r > 0:
                self.assertEqual(cc[i], "nitrogen")
        labels = {row["label"] for row in self.u["rows"]}
        self.assertIn("waterlogging", labels)
        held = [row for row in self.u["rows"] if row["label"] == "waterlogging"][0]
        self.assertEqual(held["amount"], 0)

    def test_urea_dose_clamped(self):
        lo = prescription.urea_dose({"ratios": {"ndre": 0.99}})
        hi = prescription.urea_dose({"ratios": {"ndre": 0.10}})
        self.assertAlmostEqual(lo, config.UREA_BASE_KG_HA * config.UREA_MIN_FACTOR)
        self.assertAlmostEqual(hi, config.UREA_BASE_KG_HA * config.UREA_MAX_FACTOR)
        mid = prescription.urea_dose({"ratios": {"ndre": 1 - config.UREA_DEFICIT_REF}})
        self.assertAlmostEqual(mid, config.UREA_BASE_KG_HA)

    def test_bad_product(self):
        with self.assertRaises(ValueError):
            prescription.build(self.a, "gold")

    def test_mission_covers_prescription(self):
        m = self.store.mission(42, 4, "pesticide", "vra")
        self.assertEqual(m["totals"]["target_cells"], self.p["target_cells"])
        self.assertEqual(m["totals"]["missed"], 0)
        self.assertEqual(m["totals"]["covered_multi"], 0)
        uni = self.store.mission(42, 4, "pesticide", "uniform")
        self.assertLess(m["totals"]["distance_m"], uni["totals"]["distance_m"])
        self.assertLessEqual(m["totals"]["sorties"], uni["totals"]["sorties"])


if __name__ == "__main__":
    unittest.main()
