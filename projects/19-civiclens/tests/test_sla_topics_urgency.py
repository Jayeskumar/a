import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civiclens import topics as T  # noqa: E402
from civiclens import urgency as U  # noqa: E402
from civiclens.sla import kaplan_meier, km_median, resolution_stats, survival_at, survival_grid  # noqa: E402


class TestKaplanMeier(unittest.TestCase):
    def test_no_censoring_equals_empirical_survival(self):
        d = [1, 2, 2, 3, 5]
        curve = kaplan_meier(d, [1] * 5)
        self.assertEqual(curve[0], (0.0, 1.0))
        self.assertAlmostEqual(survival_at(curve, 1.5), 0.8)
        self.assertAlmostEqual(survival_at(curve, 2), 0.4)
        self.assertAlmostEqual(survival_at(curve, 10), 0.0)
        self.assertEqual(km_median(curve), 2)

    def test_censoring_by_hand(self):
        # times 1(event) 2(censored) 3(event) 4(event): S(1)=3/4, S(3)=3/4*(1-1/2)=3/8, S(4)=0
        curve = kaplan_meier([1, 2, 3, 4], [1, 0, 1, 1])
        self.assertAlmostEqual(survival_at(curve, 1), 0.75)
        self.assertAlmostEqual(survival_at(curve, 2.5), 0.75)    # censoring does not drop the curve
        self.assertAlmostEqual(survival_at(curve, 3), 0.375)
        self.assertAlmostEqual(survival_at(curve, 4), 0.0)

    def test_all_censored_stays_at_one(self):
        curve = kaplan_meier([1, 2, 3], [0, 0, 0])
        self.assertEqual(survival_at(curve, 99), 1.0)
        self.assertIsNone(km_median(curve))

    def test_grid_is_monotone(self):
        grid, _ = survival_grid([0.5, 1, 1.5, 4, 7, 8, 9], [1, 1, 0, 1, 1, 0, 1], max_days=10, step=1)
        vals = [g["open_pct"] for g in grid]
        self.assertEqual(vals[0], 100.0)
        self.assertTrue(all(a >= b for a, b in zip(vals, vals[1:])))

    def test_resolution_stats(self):
        s = resolution_stats([1, 2, 3, 4, 5])
        self.assertEqual(s["median"], 3)
        self.assertEqual(s["p25"], 2)
        self.assertEqual(resolution_stats([]), {"n": 0})


class TestTopics(unittest.TestCase):
    def test_kmeans_separates_topics(self):
        docs = [["noise", "loudspeaker", "night"], ["noise", "music", "night"], ["loudspeaker", "noise"],
                ["tree", "fallen", "branch"], ["tree", "fallen", "road"], ["branch", "tree"],
                ["parking", "gate", "vehicle"], ["parking", "wrong", "gate"], ["vehicle", "parking"]]
        vecs, _ = T.tfidf_dicts(docs, min_df=1)
        labels, cents, inertia = T.kmeans(vecs, 3, seed=1, restarts=4)
        self.assertEqual(len(set(labels[0:3])), 1)
        self.assertEqual(len(set(labels[3:6])), 1)
        self.assertEqual(len(set(labels[6:9])), 1)
        self.assertEqual(len(set(labels)), 3)
        self.assertGreater(T.silhouette(vecs, labels), 0.3)
        self.assertEqual(T.purity(labels, ["n"] * 3 + ["t"] * 3 + ["p"] * 3), 1.0)
        top = T.top_terms(cents[labels[0]], 2)
        self.assertIn("noise", top)

    def test_cosine_and_normalize(self):
        a = T.normalize({"x": 3.0, "y": 4.0})
        self.assertAlmostEqual(a["x"], 0.6)
        self.assertAlmostEqual(T.cos(a, a), 1.0)
        self.assertEqual(T.normalize({}), {})


class TestUrgencyRules(unittest.TestCase):
    def ids(self, text):
        return {f["id"] for f in U.fired_rules(text)}

    def test_live_wire_in_three_languages(self):
        for t in ("Live wire hanging near the school", "மின் கம்பி அறுந்து தொங்குகிறது, ஆபத்து",
                  "current wire thongitu iruku, danger"):
            self.assertIn("live_wire", self.ids(t), t)

    def test_other_critical_rules(self):
        self.assertIn("sewage_drinking", self.ids("Sewage mixing in drinking water near the tank"))
        self.assertIn("sewage_drinking", self.ids("குடிநீரில் சாக்கடை நீர் கலக்கிறது"))
        self.assertIn("open_manhole", self.ids("manhole moodi illa"))
        self.assertIn("accident", self.ids("big pothole, acident happened yesterday"))    # typo-tolerant
        self.assertIn("dog_bite", self.ids("stray dog bit a child"))

    def test_long_wait_from_number_of_days(self):
        self.assertEqual(U.long_wait_days("garbage not collected for 10 days"), 10)
        self.assertEqual(U.long_wait_days("10 நாட்களாக குப்பை எடுக்கவில்லை"), 10)
        self.assertIn("long_wait", self.ids("kuppai edukala 12 naala"))
        self.assertNotIn("long_wait", self.ids("garbage not collected for 2 days"))

    def test_no_false_alarm_on_plain_complaint(self):
        fired = U.fired_rules("Street lamps not glowing on Gandhi Street")
        self.assertFalse([f for f in fired if f["kind"] != "soft"])

    def test_combine_policy(self):
        crit = [{"id": "live_wire", "label": "Live wire", "kind": "critical"}]
        high = [{"id": "tree_fall", "label": "Tree", "kind": "high"}]
        self.assertEqual(U.combine([0.05, 0.05, 0.8, 0.1], crit)[0], 1)       # rule overrides the model
        self.assertEqual(U.combine([0.05, 0.05, 0.8, 0.1], high)[0], 2)
        self.assertEqual(U.combine([0.6, 0.3, 0.1, 0.0], high)[0], 1)         # never lowers the model
        self.assertEqual(U.combine([0.1, 0.1, 0.2, 0.6], [])[0], 4)
        self.assertEqual(U.rules_only_priority(crit), 1)
        self.assertEqual(U.rules_only_priority([]), 3)


if __name__ == "__main__":
    unittest.main()
