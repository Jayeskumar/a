import datetime as dt
import unittest

from _helpers import make_donor
from bloodlink import simulation as sim
from bloodlink.config import DEMO_NOW, DEMO_TODAY, DONATION_MIN, HOSPITALS, PREP_MIN, TRAVEL_NOISE
from bloodlink.dataset import generate_donors

NOW = dt.datetime(2026, 10, 23, 10, 0)
TODAY = NOW.date()
REQ = {"group": "A+", "units": 2, "urgency": "critical", "lat": 11.38, "lon": 77.89,
       "hospital_id": None, "place": "Test"}


def pool(n=20, willingness=0.6, **kw):
    return [make_donor("D-%04d" % i, "A+", lat=11.38 + 0.004 * i, willingness=willingness,
                       list_order=n - i, **kw) for i in range(n)]


class Waves(unittest.TestCase):
    def test_deterministic(self):
        ds = pool()
        a = sim.compare(ds, REQ, NOW, TODAY, seed=5)
        b = sim.compare(ds, REQ, NOW, TODAY, seed=5)
        self.assertEqual(a, b)

    def test_fulfils_with_willing_donors(self):
        ds = pool(willingness=1.0, received=10, accepted=10)
        r = sim.compare(ds, REQ, NOW, TODAY, seed=1)["waves"]
        self.assertTrue(r["fulfilled"])
        self.assertEqual(r["collected"], 2)
        # cannot beat prep + minimum travel noise + donation time
        self.assertGreaterEqual(r["time_to_fulfil"], PREP_MIN * TRAVEL_NOISE[0] + DONATION_MIN)
        self.assertLess(r["alerts"], len(ds))           # did not alert everyone
        self.assertEqual(r["curve"][-1][1], 2)
        self.assertEqual(r["wasted_trips"], 0)
        kinds = [e["kind"] for e in r["events"]]
        self.assertEqual(kinds[0], "wave")
        self.assertIn("fulfilled", kinds)
        ts = [e["t"] for e in r["events"]]
        self.assertEqual(ts, sorted(ts))

    def test_no_candidates(self):
        r = sim.compare([make_donor("D-0001", "B+")], REQ, NOW, TODAY, seed=1)
        for s in sim.STRATEGIES:
            self.assertFalse(r[s]["fulfilled"])
            self.assertIsNone(r[s]["time_to_fulfil"])

    def test_only_eligible_alerted(self):
        recent = (TODAY - dt.timedelta(days=20)).isoformat()
        ds = pool(10, willingness=1.0) + [make_donor("D-0100", "A+", last_donation=recent, willingness=1.0)]
        r = sim.compare(ds, REQ, NOW, TODAY, seed=2)
        self.assertNotIn("D-0100", r["waves"]["notified_ids"])
        self.assertIn("D-0100", r["broadcast"]["notified_ids"])


class Baselines(unittest.TestCase):
    def test_broadcast_wastes_trips_on_ineligible(self):
        recent = (TODAY - dt.timedelta(days=20)).isoformat()
        ds = [make_donor("D-%04d" % i, "A+", last_donation=recent, willingness=1.0) for i in range(8)]
        ds += pool(3, willingness=0.0)
        r = sim.compare(ds, REQ, NOW, TODAY, seed=3, broadcast_factor=1.0)
        self.assertGreater(r["broadcast"]["wasted_trips"], 0)
        self.assertEqual(r["waves"]["wasted_trips"], 0)
        self.assertGreater(r["first_come"]["wasted_calls"], 0)  # phone screening catches them

    def test_first_come_calls_one_at_a_time(self):
        ds = pool(6, willingness=1.0)
        r = sim.compare(ds, REQ, NOW, TODAY, seed=4)["first_come"]
        accepts = [e for e in r["events"] if e["kind"] == "accept"]
        self.assertTrue(all(e["t"] >= 3.0 for e in accepts))
        self.assertEqual(r["alerts"], len(r["notified_ids"]))

    def test_broadcast_alerts_everyone_in_radius(self):
        ds = pool(12) + [make_donor("D-0500", "A+", lat=13.0)]  # ~180 km away
        r = sim.compare(ds, REQ, NOW, TODAY, seed=1)["broadcast"]
        self.assertEqual(r["alerts"], 12)


class MonteCarlo(unittest.TestCase):
    def test_registry_evaluation_sanity(self):
        donors = generate_donors()
        s = sim.evaluate_strategies(donors, HOSPITALS, DEMO_NOW, DEMO_TODAY, n=30, seed=3)
        for k in sim.STRATEGIES:
            self.assertEqual(s[k]["requests"], 30)
            self.assertTrue(0 <= s[k]["fulfilled_pct"] <= 100)
        self.assertLess(s["waves"]["median_min"], s["first_come"]["median_min"])
        self.assertLess(s["waves"]["mean_alerts"], s["broadcast"]["mean_alerts"])
        self.assertEqual(s["waves"]["mean_wasted_trips"], 0)


if __name__ == "__main__":
    unittest.main()
