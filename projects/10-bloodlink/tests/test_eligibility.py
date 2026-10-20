import datetime as dt
import unittest

import _helpers  # noqa: F401
from bloodlink.eligibility import ProfileError, evaluate

TODAY = dt.date(2026, 10, 23)


def p(**kw):
    base = {"sex": "M", "age": 30, "weight_kg": 65, "last_donation": None}
    base.update(kw)
    return base


def days_ago(n):
    return (TODAY - dt.timedelta(days=n)).isoformat()


class Interval(unittest.TestCase):
    def test_men_90_days(self):
        r = evaluate(p(last_donation=days_ago(89)), TODAY)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["codes"], ["interval"])
        self.assertEqual(r["next_eligible_date"], (TODAY + dt.timedelta(days=1)).isoformat())
        self.assertEqual(r["days_until_eligible"], 1)
        self.assertTrue(evaluate(p(last_donation=days_ago(90)), TODAY)["eligible"])

    def test_women_120_days(self):
        self.assertFalse(evaluate(p(sex="F", last_donation=days_ago(119)), TODAY)["eligible"])
        self.assertTrue(evaluate(p(sex="F", last_donation=days_ago(120)), TODAY)["eligible"])
        self.assertTrue(evaluate(p(sex="M", last_donation=days_ago(100)), TODAY)["eligible"])
        self.assertFalse(evaluate(p(sex="F", last_donation=days_ago(100)), TODAY)["eligible"])

    def test_other_sex_uses_longer_interval(self):
        self.assertFalse(evaluate(p(sex="O", last_donation=days_ago(100)), TODAY)["eligible"])
        self.assertEqual(evaluate(p(sex="O"), TODAY)["interval_days"], 120)

    def test_never_donated(self):
        r = evaluate(p(), TODAY)
        self.assertTrue(r["eligible"])
        self.assertEqual(r["next_eligible_date"], TODAY.isoformat())


class AgeWeight(unittest.TestCase):
    def test_age_bounds(self):
        self.assertFalse(evaluate(p(age=17), TODAY)["eligible"])
        self.assertTrue(evaluate(p(age=18), TODAY)["eligible"])
        self.assertTrue(evaluate(p(age=65), TODAY)["eligible"])
        r = evaluate(p(age=66), TODAY)
        self.assertFalse(r["eligible"])
        self.assertIsNone(r["next_eligible_date"])   # permanent under these rules

    def test_minor_gets_18th_birthday(self):
        r = evaluate({"sex": "F", "dob": "2009-03-15", "weight_kg": 50}, TODAY)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["age"], 17)
        self.assertEqual(r["next_eligible_date"], "2027-03-15")

    def test_dob_age_computation_and_leap_day(self):
        self.assertEqual(evaluate({"sex": "M", "dob": "2008-10-23", "weight_kg": 60}, TODAY)["age"], 18)
        self.assertEqual(evaluate({"sex": "M", "dob": "2008-10-24", "weight_kg": 60}, TODAY)["age"], 17)
        r = evaluate({"sex": "M", "dob": "2008-02-29", "weight_kg": 60}, dt.date(2026, 1, 1))
        self.assertEqual(r["next_eligible_date"], "2026-02-28")

    def test_weight(self):
        self.assertFalse(evaluate(p(weight_kg=44.9), TODAY)["eligible"])
        self.assertTrue(evaluate(p(weight_kg=45), TODAY)["eligible"])


class OtherRules(unittest.TestCase):
    def test_hb_optional(self):
        r = evaluate(p(), TODAY)
        hb = [x for x in r["rules"] if x["code"] == "hb"][0]
        self.assertIsNone(hb["pass"])
        self.assertFalse(evaluate(p(hb=12.4), TODAY)["eligible"])
        self.assertTrue(evaluate(p(hb=12.5), TODAY)["eligible"])

    def test_unwell_is_temporary(self):
        r = evaluate(p(unwell=True), TODAY)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["days_until_eligible"], 1)

    def test_deferral(self):
        r = evaluate(p(deferred_until="2026-12-01"), TODAY)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["next_eligible_date"], "2026-12-01")
        self.assertTrue(evaluate(p(deferred_until="2026-10-01"), TODAY)["eligible"])

    def test_multiple_reasons_take_latest_date(self):
        r = evaluate(p(last_donation=days_ago(10), deferred_until="2027-06-01"), TODAY)
        self.assertEqual(set(r["codes"]), {"interval", "deferral"})
        self.assertEqual(r["next_eligible_date"], "2027-06-01")
        self.assertEqual(len(r["reasons"]), 2)

    def test_bad_input(self):
        for bad in [p(sex="X"), p(last_donation="2030-01-01"), {"sex": "M", "weight_kg": 60},
                    p(weight_kg="heavy"), p(last_donation="23/10/2026"), p(hb=99), "nope"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ProfileError):
                    evaluate(bad, TODAY)


if __name__ == "__main__":
    unittest.main()
