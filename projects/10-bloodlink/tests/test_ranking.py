import datetime as dt
import unittest

from _helpers import make_donor
from bloodlink import ranking
from bloodlink.config import HOSPITALS, W_COMPAT, W_DISTANCE, W_FAIRNESS, W_RESPONSE, WAVE_MAX, WAVE_MIN

NOW = dt.datetime(2026, 10, 23, 10, 0)
TODAY = NOW.date()
REQ = {"group": "A+", "units": 2, "urgency": "critical", "lat": 11.38, "lon": 77.89,
       "hospital_id": None, "place": "Test"}


def run(donors, req=REQ):
    return ranking.rank(donors, req, NOW, TODAY)


class Gates(unittest.TestCase):
    def test_incompatible_excluded_with_reason(self):
        r = run([make_donor("D-0001", "B+"), make_donor("D-0002", "A+")])
        self.assertEqual([x["id"] for x in r["ranked"]], ["D-0002"])
        ex = r["excluded"][0]
        self.assertEqual(ex["code"], "incompatible")
        self.assertIn("anti-B", ex["reason"])

    def test_ineligible_excluded_with_next_date(self):
        recent = (TODAY - dt.timedelta(days=30)).isoformat()
        r = run([make_donor("D-0001", "A+", last_donation=recent)])
        self.assertEqual(r["ranked"], [])
        ex = r["excluded"][0]
        self.assertEqual(ex["code"], "interval")
        self.assertEqual(ex["next_eligible_date"], (TODAY + dt.timedelta(days=60)).isoformat())
        self.assertIn("eligible from", ex["reason"])
        self.assertEqual(r["counts"]["ineligible_by_rule"], {"interval": 1})

    def test_unavailable_excluded(self):
        r = run([make_donor("D-0001", "A+", available=False)])
        self.assertEqual(r["excluded"][0]["code"], "unavailable")

    def test_counts_add_up(self):
        ds = [make_donor("D-%04d" % i, g) for i, g in enumerate(["A+", "B+", "O-", "AB+", "O+", "A-"])]
        c = run(ds)["counts"]
        self.assertEqual(c["compatible"] + c["incompatible"], c["registry"])
        self.assertEqual(c["ranked"] + c["unavailable"] + c["ineligible"], c["compatible"])
        self.assertEqual(c["ranked"], 4)   # A+, O-, O+, A-


class Scoring(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(W_COMPAT + W_DISTANCE + W_RESPONSE + W_FAIRNESS, 1.0)

    def test_exact_match_preferred(self):
        r = run([make_donor("D-0001", "O-"), make_donor("D-0002", "A+"), make_donor("D-0003", "O+")])
        ids = [x["id"] for x in r["ranked"]]
        self.assertEqual(ids[0], "D-0002")
        self.assertEqual(ids[-1], "D-0001")  # O- double penalty: conserve universal donors

    def test_nearer_ranks_higher(self):
        r = run([make_donor("D-0001", "A+", lat=11.60), make_donor("D-0002", "A+", lat=11.40)])
        self.assertEqual(r["ranked"][0]["id"], "D-0002")
        self.assertLess(r["ranked"][0]["km"], r["ranked"][1]["km"])

    def test_better_responder_ranks_higher(self):
        r = run([make_donor("D-0001", "A+", received=10, accepted=1),
                 make_donor("D-0002", "A+", received=10, accepted=9)])
        self.assertEqual(r["ranked"][0]["id"], "D-0002")

    def test_fairness_penalises_recent_contact(self):
        recent = (NOW - dt.timedelta(hours=6)).isoformat()
        r = run([make_donor("D-0001", "A+", last_contacted=recent), make_donor("D-0002", "A+")])
        self.assertEqual(r["ranked"][0]["id"], "D-0002")
        fair = {x["id"]: [c for c in x["components"] if c["key"] == "fairness"][0]["value"] for x in r["ranked"]}
        self.assertEqual(fair["D-0002"], 1.0)
        self.assertLess(fair["D-0001"], 0.05)

    def test_components_sum_to_score(self):
        r = run([make_donor("D-%04d" % i, g, lat=11.3 + i * 0.02) for i, g in enumerate(["A+", "O+", "A-", "O-"])])
        for x in r["ranked"]:
            self.assertAlmostEqual(sum(c["points"] for c in x["components"]), x["score"], places=3)
            self.assertEqual([c["key"] for c in x["components"]], ["compat", "distance", "response", "fairness"])

    def test_ranks_and_explanations(self):
        r = run([make_donor("D-%04d" % i, "A+", lat=11.3 + i * 0.03) for i in range(5)])
        self.assertEqual([x["rank"] for x in r["ranked"]], [1, 2, 3, 4, 5])
        scores = [x["score"] for x in r["ranked"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIn("Ahead of #2", r["ranked"][0]["explanation"])
        self.assertIn("Exact match A+", r["ranked"][0]["explanation"])

    def test_deterministic(self):
        ds = [make_donor("D-%04d" % i, g) for i, g in enumerate(["A+", "O+", "A-", "O-", "A+"])]
        self.assertEqual(run(ds), run(ds))

    def test_urgency_changes_distance_points(self):
        d = [make_donor("D-0001", "A+", lat=11.55)]
        crit = run(d)["ranked"][0]["components"][1]["points"]
        plan = run(d, dict(REQ, urgency="planned"))["ranked"][0]["components"][1]["points"]
        self.assertLess(crit, plan)

    def test_response_estimate_prior(self):
        self.assertEqual(ranking.response_estimate(0, 0), 0.5)
        self.assertAlmostEqual(ranking.response_estimate(10, 10), 12 / 14)
        self.assertAlmostEqual(ranking.response_estimate(3, 9), 5 / 7)  # accepted capped at received


class Requests(unittest.TestCase):
    def test_normalize_hospital(self):
        r = ranking.normalize_request({"hospital_id": "H2", "group": "o neg", "units": "3"}, HOSPITALS)
        self.assertEqual((r["group"], r["units"], r["urgency"]), ("O-", 3, "urgent"))
        self.assertEqual(r["lat"], HOSPITALS[1]["lat"])

    def test_bad_requests(self):
        for bad in [{"hospital_id": "H1", "group": "Z+"}, {"hospital_id": "H1", "group": "A+", "units": 0},
                    {"hospital_id": "H1", "group": "A+", "units": 11}, {"hospital_id": "H9", "group": "A+"},
                    {"hospital_id": "H1", "group": "A+", "urgency": "whenever"}, {"group": "A+"},
                    {"group": "A+", "lat": 95, "lon": 77}, []]:
            with self.subTest(bad=bad):
                with self.assertRaises(ranking.RequestError):
                    ranking.normalize_request(bad, HOSPITALS)

    def test_first_wave_bounds(self):
        ds = [make_donor("D-%04d" % i, "A+", lat=11.3 + i * 0.005) for i in range(40)]
        r = run(ds)
        self.assertTrue(WAVE_MIN <= r["first_wave"] <= WAVE_MAX)
        self.assertEqual(run(ds[:1])["first_wave"], 1)
        self.assertEqual(run([])["first_wave"], 0)


if __name__ == "__main__":
    unittest.main()
