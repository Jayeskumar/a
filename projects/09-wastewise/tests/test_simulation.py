import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wastewise import config as C  # noqa: E402
from wastewise import planner  # noqa: E402
from wastewise.simulator import Simulation, end_of_day, simulate_month  # noqa: E402
from wastewise.town import Town, deposit_fraction  # noqa: E402

TOWN = Town()
SIM, DAYS = simulate_month(30, TOWN)


class _Bin:
    def __init__(self, bid, cap):
        self.id, self.capacity, self.ward = bid, cap, "W1"


class _StubTown:
    def __init__(self, delta):
        self.bins = [_Bin("X1", 1000)]
        self._d = delta

    def delta(self, b, day):
        return self._d


class _StubForecaster:
    def __init__(self, v, sigma):
        self.v, self.sigma = v, sigma

    def forecast(self, dow):
        return self.v


class TownTest(unittest.TestCase):
    def test_town_shape(self):
        self.assertEqual(len(TOWN.bins), C.N_BINS)
        self.assertEqual(len(TOWN.trucks), C.N_TRUCKS)
        self.assertEqual(sorted(b for t in TOWN.trucks for b in t["beat"]), sorted(TOWN.bin_by_id))
        for b in TOWN.bins:
            w = TOWN.ward_by_id[b.ward]["rect"]
            self.assertTrue(w[0] < b.x < w[2] and w[1] < b.y < w[3])
            self.assertIn(b.type, ("wet", "dry", "recyclable"))

    def test_deterministic(self):
        t2 = Town()
        self.assertEqual([b.to_json() for b in t2.bins], [b.to_json() for b in TOWN.bins])
        b = TOWN.bins[5]
        self.assertEqual(TOWN.delta(b, 3), t2.delta(b, 3))
        self.assertEqual(TOWN.history(b), t2.history(b))

    def test_market_day_effect(self):
        market = [b for b in TOWN.bins if b.zone == "market"]
        self.assertTrue(market)
        prof = market[0].profile
        self.assertEqual(max(range(7), key=lambda k: prof[k]), C.MARKET_WEEKDAY)


class RulesTest(unittest.TestCase):
    def test_rules_fire_as_documented(self):
        F = deposit_fraction(C.PLAN_ARRIVAL_H)
        b0, b1, b2 = TOWN.bins[0].id, TOWN.bins[1].id, TOWN.bins[2].id
        levels = {b.id: 0.0 for b in TOWN.bins}
        levels.update({b0: 0.70, b1: 0.40, b2: 0.10})
        fc = {b.id: _StubForecaster(0.4, 0.1) for b in TOWN.bins}
        dec = {d["bin"]: d for d in planner.decide(TOWN, levels, fc, 0)}
        self.assertAlmostEqual(dec[b0]["at_pickup"], round(0.70 + F * 0.4, 4))
        self.assertEqual(dec[b0]["rule"], "A")
        self.assertEqual(dec[b1]["rule"], "B")     # 0.4 + 0.4 + 0.25*0.4 + ~0.1 >= 1
        self.assertIsNone(dec[b2]["rule"])
        self.assertFalse(dec[b2]["collect"])

    def test_end_of_day_overflow_accounting(self):
        town = _StubTown(0.3)
        new, over = end_of_day(town, {"X1": 0.8}, {}, 0)          # not collected
        self.assertAlmostEqual(new["X1"], 1.0)
        self.assertAlmostEqual(over[0]["litres"], 100.0)
        visits = {"X1": {"arrive": 60.0}}                          # 07:00 -> 2/18 of the day's waste
        new, over = end_of_day(town, {"X1": 0.8}, visits, 0)
        self.assertEqual(over, [])
        self.assertAlmostEqual(new["X1"], (1 - 2 / 18) * 0.3, places=5)
        new, over = end_of_day(town, {"X1": 0.99}, visits, 0)     # spills before the truck came
        self.assertEqual(over[0]["when"], "before the truck came")


class SimulationTest(unittest.TestCase):
    def test_month_savings(self):
        f, s = SIM.worlds["fixed"].totals(), SIM.worlds["smart"].totals()
        self.assertEqual(f["days"], 30)
        self.assertLess(s["km"], 0.75 * f["km"])
        self.assertLess(s["fuel_l"], f["fuel_l"])
        self.assertLessEqual(s["overflow_bins"], f["overflow_bins"])
        self.assertGreater(s["avg_fill_at_pickup"], f["avg_fill_at_pickup"])
        # both worlds deal with the same waste: collected volumes are within 5%
        self.assertLess(abs(s["collected_l"] - f["collected_l"]) / f["collected_l"], 0.05)

    def test_capacity_and_shift_respected_every_day(self):
        sim = Simulation(TOWN)
        for _ in range(10):
            p = sim.preview()
            for trip in (t for tr in p["plan"]["trucks"] for t in tr["trips"]):
                self.assertLessEqual(trip["planned_load_l"], C.TRUCK_CAPACITY_L + 1e-6)
            for pol in ("smart", "fixed"):
                for tr in p["runs"][pol]["trucks"]:
                    self.assertLessEqual(tr["minutes"], C.SHIFT_MIN + 1e-6)
                    for e in tr["events"]:
                        self.assertLessEqual(e["load"], C.TRUCK_CAPACITY_L + 1e-6)
                visited = list(p["runs"][pol]["visits"])
                self.assertEqual(len(visited), len(set(visited)))
            sim.step()

    def test_deterministic_runs(self):
        a, _ = simulate_month(5, TOWN)
        b, _ = simulate_month(5, TOWN)
        self.assertEqual(a.worlds["smart"].totals(), b.worlds["smart"].totals())
        self.assertEqual(a.worlds["fixed"].totals(), b.worlds["fixed"].totals())

    def test_fixed_beat_resumes_where_it_stopped(self):
        sim = Simulation(TOWN)
        run = sim.preview()["runs"]["fixed"]
        sim.step()
        for t, tr in enumerate(run["trucks"]):
            self.assertEqual(sim.worlds["fixed"].pointers[t], tr["visited"] % len(TOWN.trucks[t]["beat"]))

    def test_preview_is_cached_and_step_advances(self):
        sim = Simulation(TOWN)
        self.assertIs(sim.preview(), sim.preview())
        sim.step()
        self.assertEqual(sim.day, 1)
        self.assertEqual(len(sim.obs[TOWN.bins[0].id]), C.HISTORY_DAYS + 1)

    def test_solver_is_fast(self):
        ms = [d for d in (SIM.preview()["plan"]["algorithm"]["total_ms"],)]
        self.assertLess(ms[0], 200.0)
        self.assertTrue(all(math.isfinite(x["kpis"]["smart"]["km"]) for x in DAYS))


if __name__ == "__main__":
    unittest.main()
