import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import questionnaires as Q  # noqa: E402


def phq_with_total(total, item9=0):
    """Build a valid PHQ-9 answer list with the given total and item-9 answer."""
    answers = [0] * 9
    answers[8] = item9
    left = total - item9
    for i in range(8):
        take = min(3, left)
        answers[i] = take
        left -= take
    assert left == 0 and sum(answers) == total
    return answers


def gad_with_total(total):
    answers = [0] * 7
    left = total
    for i in range(7):
        take = min(3, left)
        answers[i] = take
        left -= take
    return answers


class TestBands(unittest.TestCase):
    def test_phq9_every_boundary(self):
        cases = {0: "minimal", 4: "minimal", 5: "mild", 9: "mild", 10: "moderate",
                 14: "moderate", 15: "moderately_severe", 19: "moderately_severe",
                 20: "severe", 27: "severe"}
        for total, band in cases.items():
            # items 1-8 max out at 24, so totals above that need item 9 > 0
            r = Q.score("phq9", phq_with_total(total, item9=max(0, total - 24)))
            self.assertEqual((r["total"], r["band"]), (total, band), total)

    def test_phq9_all_totals_have_exactly_one_band(self):
        for total in range(28):
            self.assertIn(Q.band_for("phq9", total), Q.BAND_LABELS)
        with self.assertRaises(ValueError):
            Q.band_for("phq9", 28)
        with self.assertRaises(ValueError):
            Q.band_for("phq9", -1)

    def test_gad7_every_boundary(self):
        cases = {0: "minimal", 4: "minimal", 5: "mild", 9: "mild", 10: "moderate",
                 14: "moderate", 15: "severe", 21: "severe"}
        for total, band in cases.items():
            r = Q.score("gad7", gad_with_total(total))
            self.assertEqual((r["total"], r["band"]), (total, band), total)
        with self.assertRaises(ValueError):
            Q.band_for("gad7", 22)

    def test_standard_item_counts_and_wording(self):
        self.assertEqual(len(Q.PHQ9_ITEMS), 9)
        self.assertEqual(len(Q.GAD7_ITEMS), 7)
        self.assertTrue(Q.PHQ9_ITEMS[8].startswith("Thoughts that you would be better off dead"))
        self.assertEqual(Q.GAD7_ITEMS[0], "Feeling nervous, anxious or on edge")
        self.assertEqual([o["value"] for o in Q.OPTIONS], [0, 1, 2, 3])
        self.assertEqual(Q.OPTIONS[3]["label"], "Nearly every day")


class TestItem9Rule(unittest.TestCase):
    def test_item9_triggers_support_even_with_minimal_total(self):
        r = Q.score("phq9", [0, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(r["band"], "minimal")
        self.assertTrue(r["support"]["show"])
        self.assertEqual(r["support"]["reason"], "item9")
        self.assertTrue(r["suggest_counsellor"])

    def test_item9_any_positive_value_any_total(self):
        for item9 in (1, 2, 3):
            for total in range(item9, 24 + item9 + 1):
                r = Q.score("phq9", phq_with_total(total, item9))
                self.assertTrue(r["support"]["show"], (total, item9))

    def test_no_support_when_item9_zero_even_if_severe(self):
        r = Q.score("phq9", [3, 3, 3, 3, 3, 3, 3, 3, 0])
        self.assertEqual((r["total"], r["band"]), (24, "severe"))
        self.assertFalse(r["support"]["show"])
        self.assertTrue(r["suggest_counsellor"])  # but counsellor is still suggested

    def test_gad7_never_uses_item9_rule(self):
        r = Q.score("gad7", [3, 3, 3, 3, 3, 3, 3])
        self.assertFalse(r["support"]["show"])


class TestValidationAndExplain(unittest.TestCase):
    def test_validation_errors(self):
        self.assertIsNotNone(Q.validate("phq9", [0] * 8)[1])
        self.assertIsNotNone(Q.validate("phq9", "000000000")[1])
        self.assertIn("answers[2]", Q.validate("phq9", [0, 0, 4, 0, 0, 0, 0, 0, 0])[1])
        self.assertIn("answers[0]", Q.validate("phq9", [True] + [0] * 8)[1])
        self.assertIn("answers[1]", Q.validate("gad7", [0, 1.5, 0, 0, 0, 0, 0])[1])
        self.assertIn("instrument", Q.validate("bdi", [0])[1])
        with self.assertRaises(ValueError):
            Q.score("gad7", [0] * 9)

    def test_float_integers_accepted(self):
        clean, err = Q.validate("gad7", [1.0, 0, 0, 0, 0, 0, 2.0])
        self.assertIsNone(err)
        self.assertEqual(clean, [1, 0, 0, 0, 0, 0, 2])

    def test_explanation_and_breakdown(self):
        r = Q.score("phq9", [1, 2, 0, 3, 0, 0, 0, 0, 0], difficulty=1)
        self.assertEqual(r["total"], 6)
        self.assertEqual(len(r["breakdown"]), 9)
        self.assertIn("energy (3)", r["explain"][2])
        self.assertIn("not a diagnosis", r["disclaimer"])
        self.assertEqual(r["difficulty"], "Somewhat difficult")
        self.assertEqual(r["band_range"], [5, 9])

    def test_definitions(self):
        d = Q.definitions()
        self.assertEqual(d["phq9"]["item9_index"], 8)
        self.assertEqual(len(d["phq9"]["bands"]), 5)
        self.assertEqual(len(d["gad7"]["bands"]), 4)
        self.assertEqual(d["gad7"]["bands"][-1], {"band": "severe", "label": "Severe",
                                                   "min": 15, "max": 21})


if __name__ == "__main__":
    unittest.main()
