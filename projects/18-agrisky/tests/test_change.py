import math
import unittest

import _path  # noqa: F401
from agrisky import change
from agrisky.field import W, H


def quarter_disc(r):
    """Cells within r metres of the bottom-right corner."""
    ox, oy = W - 1.0, H - 1.0
    return [math.hypot((i % W) + 0.5 - ox, (i // W) + 0.5 - oy) <= r for i in range(W * H)]


class TestChange(unittest.TestCase):
    def test_ols_exact(self):
        a, b, r2 = change.ols([0, 1, 2, 3], [1, 3, 5, 7])
        self.assertAlmostEqual(a, 1)
        self.assertAlmostEqual(b, 2)
        self.assertAlmostEqual(r2, 1)
        with self.assertRaises(ValueError):
            change.ols([1], [1])

    def test_uniform_growth_is_not_flagged(self):
        a = [0.6] * (W * H)
        b = [0.65] * (W * H)               # the whole field greened up
        d = change.ndvi_difference(a, b, [True] * (W * H))
        self.assertAlmostEqual(d["field_shift"], 0.05)
        self.assertEqual(d["declining_cells"], 0)
        self.assertEqual(d["hotspots"], [])

    def test_patch_drop_detected(self):
        a = [0.8] * (W * H)
        b = [0.82] * (W * H)
        patch = [y * W + x for y in range(10, 15) for x in range(20, 26)]   # 30 cells
        for i in patch:
            b[i] = 0.6
        d = change.ndvi_difference(a, b, [True] * (W * H))
        self.assertEqual(d["declining_cells"], 30)
        self.assertEqual(len(d["hotspots"]), 1)
        self.assertEqual(d["hotspots"][0]["bbox"], [20, 10, 25, 14])
        self.assertAlmostEqual(d["hotspots"][0]["mean_change"], -0.22, places=6)

    def test_front_advance(self):
        fa = change.front_advance(quarter_disc(10), quarter_disc(17))
        self.assertAlmostEqual(fa["p90_m"], 7, delta=1.0)
        self.assertIsNone(change.front_advance([False] * (W * H), quarter_disc(5)))

    def test_spread_rate_and_alert(self):
        days = [0, 7, 14, 21]
        masks = [quarter_disc(6 + d) for d in days]           # truth: 1 m/day
        sp = change.spread(days, masks, crop_cells=8800)
        self.assertAlmostEqual(sp["front_speed_m_day"], 1.0, delta=0.15)
        self.assertGreater(sp["trend"]["r2"], 0.99)
        # quarter disc: sqrt(A) = sqrt(pi)/2 * r -> slope 0.886 per day
        self.assertAlmostEqual(sp["trend"]["sqrt_b"], math.sqrt(math.pi) / 2, delta=0.05)
        self.assertEqual(sp["alert"]["level"], "red")
        self.assertIsNotNone(sp["projection"])
        self.assertIn("ta", sp["alert"])

    def test_no_pest_green(self):
        sp = change.spread([0, 7], [[False] * (W * H)] * 2, crop_cells=8800)
        self.assertEqual(sp["alert"]["level"], "green")
        self.assertIsNone(sp["trend"])

    def test_new_patch_with_fast_decline_is_red(self):
        empty = [False] * (W * H)
        sp = change.spread([0, 7], [empty, quarter_disc(8)], crop_cells=8800, decline_rate=-0.15)
        self.assertIsNone(sp["front_speed_m_day"])
        self.assertEqual(sp["alert"]["level"], "red")
        self.assertIn("New pest", sp["alert"]["en"])

    def test_stable_patch_amber(self):
        m = quarter_disc(10)
        sp = change.spread([0, 7, 14], [m, m, m], crop_cells=8800)
        self.assertEqual(sp["alert"]["level"], "amber")


if __name__ == "__main__":
    unittest.main()
