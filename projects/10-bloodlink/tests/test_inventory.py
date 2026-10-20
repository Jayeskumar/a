import unittest

import _helpers  # noqa: F401
from bloodlink import inventory as inv
from bloodlink.config import BANKS, BLOOD_GROUPS, SEED

TWO_BANKS = [
    {"id": "A", "name": "Alpha (demo)", "lat": 11.40, "lon": 77.90},
    {"id": "B", "name": "Beta (demo)", "lat": 11.60, "lon": 78.10},
]


def unit(uid, group, expires, bank="A", collected=-10, **kw):
    u = {"id": uid, "group": group, "expires": expires, "collected": collected, "additive": "SAGM", "bank": bank}
    u.update(kw)
    return u


class Fefo(unittest.TestCase):
    def test_earliest_expiry_first(self):
        stock = [unit("u3", "O+", 30), unit("u1", "O+", 5), unit("u2", "O+", 12)]
        got, short = inv.fefo_issue(stock, "O+", 2, today=0)
        self.assertEqual([u["id"] for u in got], ["u1", "u2"])
        self.assertEqual(short, 0)
        self.assertEqual([u["id"] for u in stock], ["u3"])

    def test_never_issues_expired(self):
        stock = [unit("old", "O+", 0), unit("ok", "O+", 9)]
        got, short = inv.fefo_issue(stock, "O+", 2, today=0)
        self.assertEqual([u["id"] for u in got], ["ok"])
        self.assertEqual(short, 1)

    def test_substitutes_only_after_exact(self):
        stock = [unit("o-", "O-", 2), unit("a1", "A+", 20), unit("o+", "O+", 3), unit("b+", "B+", 1)]
        got, short = inv.fefo_issue(stock, "A+", 3, today=0)
        self.assertEqual([u["id"] for u in got], ["a1", "o+", "o-"])   # exact, then O+, then O-
        self.assertEqual(short, 0)
        self.assertEqual([u["id"] for u in stock], ["b+"])               # incompatible untouched

    def test_no_substitutes(self):
        stock = [unit("o-", "O-", 2)]
        got, short = inv.fefo_issue(stock, "A+", 1, today=0, allow_substitutes=False)
        self.assertEqual(got, [])
        self.assertEqual(short, 1)

    def test_rh_negative_patient_never_gets_positive(self):
        stock = [unit("p", "O+", 2), unit("n", "O-", 9)]
        got, _ = inv.fefo_issue(stock, "A-", 2, today=0)
        self.assertEqual([u["id"] for u in got], ["n"])

    def test_remove_expired(self):
        stock = [unit("a", "O+", 3), unit("b", "O+", 4)]
        gone = inv.remove_expired(stock, 3)
        self.assertEqual([u["id"] for u in gone], ["a"])
        self.assertEqual([u["id"] for u in stock], ["b"])


class Forecast(unittest.TestCase):
    def test_moving_average(self):
        self.assertEqual(inv.moving_average([1, 2, 3, 4, 5, 6, 7, 8], 7), 5.0)
        self.assertEqual(inv.moving_average([4, 2], 7), 3.0)
        self.assertEqual(inv.moving_average([], 7), 0.0)

    def test_sparse_fallback(self):
        series = [1] + [0] * 27            # one unit in 28 days, none in the last 7
        self.assertAlmostEqual(inv.forecast_rate(series), 1 / 28)
        self.assertAlmostEqual(inv.forecast_rate([2] * 28), 2.0)

    def test_backtest(self):
        r = inv.backtest_moving_average([5] * 30)
        self.assertEqual(r["mae_ma"], 0)
        self.assertEqual(r["mae_naive"], 0)
        self.assertIsNone(inv.backtest_moving_average([1, 2]))

    def test_at_risk_flags(self):
        self.assertEqual(inv.at_risk_flags([1, 2, 3], 1.0), [False, False, False])
        self.assertEqual(inv.at_risk_flags([1, 1, 1], 1.0), [False, True, True])
        self.assertEqual(inv.at_risk_flags([1, 1, 1, 1], 4.0), [False] * 4)
        self.assertEqual(inv.at_risk_flags([5, 5], 0.0), [True, True])
        # an expiring unit does not consume demand time
        self.assertEqual(inv.at_risk_flags([1, 1, 2], 1.0), [False, True, False])

    def test_group_status(self):
        self.assertEqual(inv.group_status([], 2.0, 0)["status"], "short")
        self.assertEqual(inv.group_status([unit(str(i), "O+", 30) for i in range(5)], 2.0, 0)["status"], "low")
        self.assertEqual(inv.group_status([unit(str(i), "O+", 30) for i in range(8)], 2.0, 0)["status"], "ok")
        self.assertEqual(inv.group_status([unit(str(i), "O+", 3) for i in range(20)], 2.0, 0)["status"], "expiry-risk")
        self.assertEqual(inv.group_status([unit("x", "O+", 30)], 0.0, 0)["status"], "idle")
        s = inv.group_status([unit(str(i), "O+", 30) for i in range(6)], 1.0, 0)
        self.assertEqual((s["units"], s["days_cover"], s["target"], s["deficit"]), (6, 6.0, 3, 0))


class Transfers(unittest.TestCase):
    def setUp(self):
        # Alpha: 10 O+ units expiring in 6 days but only 0.2/day demand; Beta: 5/day, empty.
        self.stock = {"A": [unit("A%d" % i, "O+", 6) for i in range(10)], "B": []}
        self.rates = {"A": {"O+": 0.2}, "B": {"O+": 5.0}}

    def test_moves_at_risk_units_to_short_bank(self):
        s = inv.suggest_transfers(self.stock, self.rates, 0, banks=TWO_BANKS)
        self.assertEqual(len(s), 1)
        t = s[0]
        self.assertEqual((t["from"], t["to"], t["group"]), ("A", "B", "O+"))
        self.assertEqual(t["units"], 9)               # Alpha keeps the 1 unit it can use
        self.assertEqual(t["at_risk_units"], 9)
        self.assertEqual(t["priority"], "high")
        self.assertIn("would expire unused", t["reason"])

    def test_never_to_self_and_respects_distance(self):
        s = inv.suggest_transfers(self.stock, self.rates, 0, banks=TWO_BANKS, max_km=5)
        self.assertEqual(s, [])
        for t in inv.suggest_transfers(self.stock, self.rates, 0, banks=TWO_BANKS):
            self.assertNotEqual(t["from"], t["to"])

    def test_receiver_must_use_before_expiry(self):
        rates = {"A": {"O+": 0.2}, "B": {"O+": 0.3}}  # Beta could not use them either
        s = inv.suggest_transfers(self.stock, rates, 0, banks=TWO_BANKS)
        moved = sum(t["units"] for t in s)
        self.assertLessEqual(moved, 1)               # at most what Beta can use in ~5 days

    def test_units_too_close_to_expiry_stay(self):
        stock = {"A": [unit("A%d" % i, "O+", 1) for i in range(5)], "B": []}
        self.assertEqual(inv.suggest_transfers(stock, self.rates, 0, banks=TWO_BANKS), [])

    def test_moved_units_not_moved_again(self):
        stock = {"A": [unit("A%d" % i, "O+", 6, moved=True) for i in range(10)], "B": []}
        self.assertEqual(inv.suggest_transfers(stock, self.rates, 0, banks=TWO_BANKS), [])

    def test_excess_only_goes_to_deficit(self):
        # 40 fresh units at Alpha (1/day): beyond a week of cover is excess, Beta short
        stock = {"A": [unit("A%d" % i, "O+", 40) for i in range(40)], "B": []}
        rates = {"A": {"O+": 1.0}, "B": {"O+": 4.0}}
        s = inv.suggest_transfers(stock, rates, 0, banks=TWO_BANKS)
        moved = sum(t["units"] for t in s)
        self.assertGreater(moved, 0)
        self.assertGreaterEqual(40 - moved, 7)       # sender keeps a week of its own demand
        # Beta well stocked (no deficit) -> Alpha's excess stays home
        rates_b_ok = {"A": {"O+": 1.0}, "B": {"O+": 1.0}}
        stock2 = {"A": [unit("A%d" % i, "O+", 40) for i in range(20)],
                  "B": [unit("B%d" % i, "O+", 40, bank="B") for i in range(10)]}
        self.assertEqual(inv.suggest_transfers(stock2, rates_b_ok, 0, banks=TWO_BANKS), [])


class Network(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = inv.build_snapshot(SEED)

    def test_events_deterministic(self):
        self.assertEqual(inv.generate_events(4, 5), inv.generate_events(4, 5))
        self.assertNotEqual(inv.generate_events(4, 5), inv.generate_events(5, 5))

    def test_snapshot_shape(self):
        self.assertEqual(set(self.base.stock), {b["id"] for b in BANKS})
        for st in self.base.stock.values():
            for u in st:
                self.assertGreater(u["expires"], 0)
                self.assertIn(u["group"], BLOOD_GROUPS)

    def test_transfers_reduce_waste_and_shortage(self):
        r = inv.compare_month(self.base, range(1, 4))
        s = r["summary"]
        self.assertEqual(s["with"]["demand"]["mean"], s["without"]["demand"]["mean"])
        self.assertLess(s["with"]["expired"]["mean"], s["without"]["expired"]["mean"])
        self.assertLessEqual(s["with"]["unmet"]["mean"], s["without"]["unmet"]["mean"])
        self.assertEqual(s["without"]["moved"]["mean"], 0)

    def test_simulation_conserves_units(self):
        net = self.base.clone()
        start = sum(len(v) for v in net.stock.values())
        added = issued = expired = 0
        for ev in inv.generate_events(9, 10):
            added += sum(sum(b["collected"].values()) for b in ev["banks"].values())
            m = net.step(ev, transfers=True)
            issued += m["issued"]
            expired += m["expired"]
        end = sum(len(v) for v in net.stock.values()) + len(net.in_transit)
        self.assertEqual(start + added - issued - expired, end)

    def test_clone_is_independent(self):
        c = self.base.clone()
        c.stock["BB1"].clear()
        self.assertTrue(self.base.stock["BB1"])


if __name__ == "__main__":
    unittest.main()
