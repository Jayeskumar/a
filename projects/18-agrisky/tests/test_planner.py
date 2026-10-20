import math
import unittest

import _path  # noqa: F401
from agrisky import planner

W, H = 40, 30
RATE = 20.0 / 10000          # 20 L/ha tank mix -> L per m^2


def rect_mask(x0, y0, x1, y1, base=None):
    m = list(base) if base else [False] * (W * H)
    for y in range(y0, y1):
        for x in range(x0, x1):
            m[y * W + x] = True
    return m


def run(target, **kw):
    kw.setdefault("home", (-5.0, 15.0))
    return planner.plan(target, [RATE if t else 0.0 for t in target], W, H, **kw)


class TestCoverage(unittest.TestCase):
    def test_every_target_exactly_once_swath1(self):
        t = rect_mask(5, 5, 15, 12)
        t = rect_mask(25, 18, 33, 27, t)            # second, separate block
        t[3 * W + 30] = True                        # an isolated cell
        res = run(t, swath=1)
        tot = res["totals"]
        self.assertEqual(tot["missed"], 0)
        self.assertEqual(tot["covered_multi"], 0)
        self.assertEqual(tot["covered_once"], sum(t))
        self.assertEqual(tot["overspray_cells"], 0)  # 1 m swath = pixel-exact
        cov = res["coverage"]
        self.assertTrue(all(cov[i] == (1 if t[i] else 0) for i in range(W * H)))
        self.assertEqual(len(res["blocks"]), 3)

    def test_wide_swath_no_double_spray(self):
        # irregular L-shape + disc; swath 4 must still spray each target exactly once
        t = rect_mask(3, 3, 20, 7)
        t = rect_mask(3, 7, 8, 25, t)
        for i in range(W * H):
            if math.hypot(i % W - 30, i // W - 20) <= 6:
                t[i] = True
        res = run(t, swath=4)
        tot = res["totals"]
        self.assertEqual(tot["missed"], 0)
        self.assertEqual(tot["covered_multi"], 0)
        self.assertEqual(max(res["coverage"]), 1)
        self.assertLess(tot["overspray_pct"], 25)
        self.assertEqual(tot["coverage_pct"], 100.0)

    def test_empty(self):
        res = run([False] * (W * H))
        self.assertEqual(res["totals"]["sorties"], 0)
        self.assertEqual(res["totals"]["coverage_pct"], 100.0)


class TestCapacity(unittest.TestCase):
    def test_tank_splits_sorties(self):
        t = rect_mask(0, 0, W, H)                    # 1200 m^2 -> 2.4 L at 20 L/ha
        res = run(t, swath=4, tank=0.5, endurance_s=3600)
        self.assertGreaterEqual(res["totals"]["sorties"], 5)
        for s in res["sorties"]:
            self.assertLessEqual(s["payload"], 0.5 + 1e-9)
        self.assertEqual(res["totals"]["missed"], 0)
        self.assertEqual(res["totals"]["covered_multi"], 0)
        self.assertAlmostEqual(res["totals"]["payload"], sum(s["payload"] for s in res["sorties"]))

    def test_battery_budget_and_rth(self):
        t = rect_mask(0, 0, W, H)
        endurance, reserve = 120.0, 0.2
        res = run(t, swath=2, tank=100, endurance_s=endurance, reserve=reserve)
        self.assertGreater(res["totals"]["sorties"], 1)
        home = [-5.0, 15.0]
        for s in res["sorties"]:
            self.assertLessEqual(s["time_s"], endurance * (1 - reserve) + 1e-6)
            self.assertEqual(s["legs"][0]["kind"], "ferry")
            self.assertEqual(s["legs"][0]["pts"][0], home)
            self.assertEqual(s["legs"][-1]["kind"], "rth")
            self.assertEqual(s["legs"][-1]["pts"][-1], home)
        self.assertEqual(res["totals"]["missed"], 0)
        tot = res["totals"]
        self.assertAlmostEqual(tot["mission_time_s"],
                               tot["flight_time_s"] + (tot["sorties"] - 1) * res["params"]["turnaround_s"], places=3)

    def test_infeasible(self):
        t = rect_mask(30, 10, 35, 15)
        with self.assertRaises(planner.PlanError):
            run(t, endurance_s=5)
        with self.assertRaises(planner.PlanError):
            run(t, swath=0)

    def test_payload_matches_rate(self):
        t = rect_mask(4, 4, 12, 12)                  # 64 m^2, swath 4 fits exactly
        res = run(t, swath=4)
        self.assertAlmostEqual(res["totals"]["payload"], 64 * RATE, places=9)


class TestTurns(unittest.TestCase):
    def test_tall_strip_prefers_north_south(self):
        t = rect_mask(10, 0, 14, H)                  # 4 m wide, 30 m tall
        auto = run(t, swath=4)
        h = run(t, swath=4, orient="h")
        self.assertEqual(auto["blocks"][0]["orientation"], "v")
        self.assertEqual(auto["totals"]["turns"], 0)
        self.assertGreater(h["totals"]["turns"], 5)
        self.assertLess(auto["totals"]["flight_time_s"], h["totals"]["flight_time_s"])

    def test_boustrophedon_alternates(self):
        t = rect_mask(0, 0, 20, 8)
        res = run(t, swath=2, orient="h")
        sprays = [leg["pts"] for leg in res["sorties"][0]["legs"] if leg["kind"] == "spray"]
        dirs = [math.copysign(1, p[-1][0] - p[0][0]) for p in sprays]
        self.assertEqual(len(dirs), 4)
        self.assertTrue(all(a == -b for a, b in zip(dirs, dirs[1:])))


if __name__ == "__main__":
    unittest.main()
