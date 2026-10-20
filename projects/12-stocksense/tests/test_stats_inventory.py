import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stocksense import config, inventory  # noqa: E402
from stocksense.stats import (expected_shortage, inv_norm, norm_cdf, norm_loss,  # noqa: E402
                              prob_exceed, solve)


class TestInverseNormal(unittest.TestCase):
    def test_textbook_quantiles(self):
        # values from standard normal tables
        known = {0.5: 0.0, 0.8: 0.841621, 0.9: 1.281552, 0.95: 1.644854, 0.975: 1.959964,
                 0.98: 2.053749, 0.99: 2.326348, 0.995: 2.575829, 0.999: 3.090232}
        for p, z in known.items():
            self.assertAlmostEqual(inv_norm(p), z, places=5, msg="p=%s" % p)

    def test_round_trip_and_symmetry_across_regions(self):
        # covers the lower tail (< 0.02425), central and upper-tail branches of Acklam's method
        for p in (1e-10, 1e-6, 0.001, 0.01, 0.02, 0.02425, 0.1, 0.3, 0.5, 0.7, 0.9, 0.97575, 0.99, 0.9999):
            z = inv_norm(p)
            self.assertLess(abs(norm_cdf(z) - p), 1e-12 + 1e-9 * p, msg="p=%s" % p)
            self.assertAlmostEqual(inv_norm(1 - p), -z, places=6)

    def test_monotone_and_domain(self):
        ps = [i / 1000 for i in range(1, 1000)]
        zs = [inv_norm(p) for p in ps]
        self.assertTrue(all(b > a for a, b in zip(zs, zs[1:])))
        for bad in (0.0, 1.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                inv_norm(bad)

    def test_loss_function(self):
        self.assertAlmostEqual(norm_loss(0.0), 1 / math.sqrt(2 * math.pi), places=12)
        self.assertAlmostEqual(norm_loss(1.0), 0.083315, places=5)   # table value G(1)
        self.assertAlmostEqual(expected_shortage(100, 100, 10), 3.989423, places=5)
        self.assertAlmostEqual(prob_exceed(116.4485, 100, 10), 0.05, places=5)

    def test_solver(self):
        x = solve([[2, 1, -1], [-3, -1, 2], [-2, 1, 2]], [8, -11, -3])
        for got, want in zip(x, [2, 3, -1]):
            self.assertAlmostEqual(got, want, places=10)
        with self.assertRaises(ValueError):
            solve([[1, 2], [2, 4]], [1, 2])


ITEM = {"sku": "T", "name": "Test", "price": 12.0, "cost": 10.0, "shelf_life": 365,
        "lead_time": 5, "lead_sd": 0.0, "pack": 1}


class TestEoqRop(unittest.TestCase):
    def test_eoq_textbook(self):
        # D = 1200/yr, S = 100 per order, H = 6 per unit-year -> sqrt(2*1200*100/6) = 200
        self.assertAlmostEqual(inventory.eoq(1200, 100, 6), 200.0, places=9)
        self.assertEqual(inventory.eoq(0, 100, 6), 0.0)

    def test_safety_stock_and_rop(self):
        # d = 10/day, L = 5, sigma = 2/day, 95% -> SS = 1.6449 * 2 * sqrt(5) = 7.356, ROP = 57.356
        z = inv_norm(0.95)
        ss, sig = inventory.safety_stock(z, 2.0, 5)
        self.assertAlmostEqual(sig, 2 * math.sqrt(5), places=9)
        self.assertAlmostEqual(ss, 7.3560, places=3)
        self.assertAlmostEqual(inventory.reorder_point(50, ss), 57.3560, places=3)
        # lead-time variability term: sqrt(L s^2 + d^2 sL^2)
        _, sig2 = inventory.safety_stock(z, 2.0, 5, d_avg=10, lead_sd=1.0)
        self.assertAlmostEqual(sig2, math.sqrt(5 * 4 + 100), places=9)

    def test_policy_uses_protection_interval(self):
        fc = [10.0] * 28
        p = inventory.policy(ITEM, fc, 2.0, 0.95)
        P = ITEM["lead_time"] + config.REVIEW_DAYS
        self.assertEqual(p["protection_days"], P)
        self.assertAlmostEqual(p["prot_demand"], 10 * P)
        self.assertAlmostEqual(p["ss"], inv_norm(0.95) * 2 * math.sqrt(P), places=6)
        self.assertAlmostEqual(p["rop"], 10 * P + p["ss"], places=6)
        h = ITEM["cost"] * config.HOLDING_RATE
        self.assertAlmostEqual(p["eoq"], math.sqrt(2 * 3650 * config.ORDER_COST / h), places=6)

    def test_pack_rounding(self):
        self.assertEqual(inventory.ceil_pack(25, 12), 36)
        self.assertEqual(inventory.ceil_pack(24, 12), 24)
        self.assertEqual(inventory.floor_pack(25, 12), 24)
        self.assertEqual(inventory.ceil_pack(0, 6), 0)

    def test_perishable_cap(self):
        milk = dict(ITEM, shelf_life=4, lead_time=1, pack=6, price=27.0, cost=24.0)
        p = inventory.policy(milk, [60.0] * 28, 5.0, 0.95)
        self.assertTrue(p["perishable"])
        self.assertEqual(p["usable_days"], 3)       # 75% of 4 days
        self.assertEqual(p["q_binding"], "shelf life")
        self.assertLessEqual(p["q_star"], 180)       # never more than 3 days of sales
        qty = inventory.order_quantity(p, 0, 6)
        self.assertEqual(qty % 6, 0)
        self.assertLessEqual(qty, p["shelf_cap"] + p["ss"])

    def test_order_only_below_rop(self):
        fc = [10.0] * 28
        p = inventory.policy(ITEM, fc, 2.0, 0.95)
        self.assertEqual(inventory.order_quantity(p, p["rop"] + 1, 1), 0)
        q = inventory.order_quantity(p, 20, 1)
        self.assertGreaterEqual(20 + q, p["rop"] + p["q_star"] - 1)

    def test_plan_item_status_and_risk(self):
        fc = [10.0] * 28
        urgent = inventory.plan_item(ITEM, fc, 2.0, on_hand=5)
        self.assertEqual(urgent["status"], "urgent")
        self.assertGreater(urgent["order_qty"], 0)
        self.assertGreater(urgent["risk_skip"], 0.99)
        self.assertGreater(urgent["sales_at_risk"], 0)
        ok = inventory.plan_item(ITEM, fc, 2.0, on_hand=90)
        self.assertEqual(ok["status"], "ok")
        self.assertLess(ok["risk_skip"], 0.05)
        over = inventory.plan_item(ITEM, fc, 2.0, on_hand=5000)
        self.assertEqual(over["status"], "overstock")
        self.assertGreater(over["excess_value"], 0)

    def test_tradeoff_curve_shape(self):
        items = [(ITEM, [10.0] * 28, 3.0), (dict(ITEM, sku="U", price=50.0, cost=30.0), [4.0] * 28, 2.0)]
        pts = inventory.tradeoff(items, [0.8, 0.9, 0.95, 0.99])["points"]
        holds = [p["holding_cost"] for p in pts]
        outs = [p["stockout_cost"] for p in pts]
        self.assertEqual(holds, sorted(holds))                 # more service -> more safety stock
        self.assertEqual(outs, sorted(outs, reverse=True))     # ... and fewer stock-outs
        fills = [p["fill_rate"] for p in pts]
        self.assertEqual(fills, sorted(fills))

    def test_optimal_service(self):
        # P(stockout) = HQ / (HQ + D m): H = 2.4, Q = 100, D = 3650, m = 2 -> 240 / 7540
        sl = inventory.optimal_service(ITEM, 100, 3650)
        self.assertAlmostEqual(sl, 1 - 240 / (240 + 7300), places=6)


if __name__ == "__main__":
    unittest.main()
