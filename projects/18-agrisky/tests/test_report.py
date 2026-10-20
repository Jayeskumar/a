import csv
import io
import unittest

import _path  # noqa: F401
from agrisky import report
from agrisky.pipeline import Store


def has_tamil(s):
    return any("஀" <= ch <= "௿" for ch in s)


class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        cls.scene = cls.store.scene(42, 4)
        cls.a = cls.store.analysis(42, 4)
        cls.p = cls.store.prescription(42, 4, "pesticide")
        cls.u = cls.store.prescription(42, 4, "urea")

    def test_bilingual_lines(self):
        lines = self.scene["report"]["lines"]
        keys = {l["key"] for l in lines}
        for k in ("field", "pest", "spray", "nitrogen", "waterlogging", "savings", "safety"):
            self.assertIn(k, keys)
        for l in lines:
            self.assertTrue(l["en"])
            self.assertTrue(has_tamil(l["ta"]), l["ta"])

    def test_csv(self):
        text = report.prescription_csv(self.a, self.p, self.u)
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), len(self.a["zones"]) + 1)
        total = rows[-1]
        self.assertEqual(total["zone_id"], "TOTAL")
        self.assertAlmostEqual(float(total["pesticide_l"]), self.p["vra"]["amount"], places=2)
        self.assertAlmostEqual(float(total["urea_kg"]), self.u["vra"]["amount"], places=1)
        self.assertEqual(float(total["area_m2"]), 9600.0)

    def test_geojson(self):
        g = report.prescription_geojson(self.a, self.p, self.u)
        self.assertEqual(g["type"], "FeatureCollection")
        self.assertEqual(len(g["features"]), len(self.a["zones"]))
        for f in g["features"]:
            self.assertEqual(f["geometry"]["type"], "MultiPolygon")
            ring = f["geometry"]["coordinates"][0][0]
            self.assertEqual(ring[0], ring[-1])                    # closed ring
            lon, lat = ring[0]
            self.assertTrue(77 < lon < 79 and 11 < lat < 12)
            # rectangles cover the zone area exactly
        cells = {}
        for z in self.a["zones_grid"]:
            cells[z] = cells.get(z, 0) + 1
        for z in self.a["zones"]:
            idx = [i for i, v in enumerate(self.a["zones_grid"]) if v == z["id"]]
            rects = report.rectangles(idx, 120)
            self.assertEqual(sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in rects), cells[z["id"]])


if __name__ == "__main__":
    unittest.main()
