import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemesetu import rules  # noqa: E402
from schemesetu.rules import FAIL, PASS, UNKNOWN  # noqa: E402

PARAMS = {"LIMIT": {"value": 250000, "note": "test"}}


def st(rule, profile):
    return rules.evaluate(rule, profile, PARAMS)["status"]


class LeafTests(unittest.TestCase):
    def test_comparisons(self):
        p = {"x": 5, "c": "PHH", "b": True}
        self.assertEqual(st({"fact": "x", "op": "==", "value": 5}, p), PASS)
        self.assertEqual(st({"fact": "x", "op": "!=", "value": 5}, p), FAIL)
        self.assertEqual(st({"fact": "x", "op": "<", "value": 6}, p), PASS)
        self.assertEqual(st({"fact": "x", "op": "<=", "value": 5}, p), PASS)
        self.assertEqual(st({"fact": "x", "op": ">", "value": 5}, p), FAIL)
        self.assertEqual(st({"fact": "x", "op": ">=", "value": 5}, p), PASS)
        self.assertEqual(st({"fact": "b", "op": "==", "value": True}, p), PASS)

    def test_range_inclusive(self):
        r = {"fact": "age", "op": "between", "value": [18, 40]}
        self.assertEqual(st(r, {"age": 18}), PASS)
        self.assertEqual(st(r, {"age": 40}), PASS)
        self.assertEqual(st(r, {"age": 41}), FAIL)
        self.assertEqual(st(r, {"age": 17}), FAIL)

    def test_membership(self):
        r = {"fact": "c", "op": "in", "value": ["AAY", "PHH"]}
        self.assertEqual(st(r, {"c": "PHH"}), PASS)
        self.assertEqual(st(r, {"c": "NPHH"}), FAIL)
        self.assertEqual(st({"fact": "c", "op": "not_in", "value": ["AAY"]}, {"c": "PHH"}), PASS)

    def test_param_reference(self):
        r = {"fact": "inc", "op": "<=", "value": {"param": "LIMIT"}}
        self.assertEqual(st(r, {"inc": 250000}), PASS)
        self.assertEqual(st(r, {"inc": 250001}), FAIL)

    def test_missing_fact_is_unknown(self):
        self.assertEqual(st({"fact": "x", "op": "==", "value": 1}, {}), UNKNOWN)
        self.assertEqual(st({"fact": "x", "op": "==", "value": 1}, {"x": None}), UNKNOWN)


class LogicTests(unittest.TestCase):
    A = {"fact": "a", "op": "==", "value": True}
    B = {"fact": "b", "op": "==", "value": True}

    def test_all(self):
        r = {"all": [self.A, self.B]}
        self.assertEqual(st(r, {"a": True, "b": True}), PASS)
        self.assertEqual(st(r, {"a": True, "b": False}), FAIL)

    def test_any(self):
        r = {"any": [self.A, self.B]}
        self.assertEqual(st(r, {"a": False, "b": True}), PASS)
        self.assertEqual(st(r, {"a": False, "b": False}), FAIL)

    def test_not(self):
        r = {"not": self.A}
        self.assertEqual(st(r, {"a": True}), FAIL)
        self.assertEqual(st(r, {"a": False}), PASS)
        self.assertEqual(st(r, {}), UNKNOWN)

    def test_missing_data_gives_possibly(self):
        # all(): unknown + pass -> unknown ("possibly eligible")
        self.assertEqual(st({"all": [self.A, self.B]}, {"a": True}), UNKNOWN)
        # all(): a failing condition decides even with missing data
        self.assertEqual(st({"all": [self.A, self.B]}, {"a": False}), FAIL)
        # any(): a passing condition decides even with missing data
        self.assertEqual(st({"any": [self.A, self.B]}, {"a": True}), PASS)
        self.assertEqual(st({"any": [self.A, self.B]}, {"a": False}), UNKNOWN)

    def test_nested(self):
        r = {"all": [self.A, {"any": [self.B, {"not": {"fact": "c", "op": "in", "value": ["X"]}}]}]}
        self.assertEqual(st(r, {"a": True, "b": False, "c": "Y"}), PASS)
        self.assertEqual(st(r, {"a": True, "b": False, "c": "X"}), FAIL)
        self.assertEqual(st(r, {"a": True, "b": False}), UNKNOWN)

    def test_trace_is_full_and_explains(self):
        r = {"all": [self.A, self.B]}
        tr = rules.evaluate(r, {"a": False}, PARAMS)
        self.assertEqual([c["status"] for c in tr["children"]], [FAIL, UNKNOWN])  # no short-circuit
        self.assertEqual(rules.needed_facts(tr), [])  # already decided -> nothing needed

    def test_needed_facts_only_relevant(self):
        r = {"all": [self.A, {"any": [self.B, {"fact": "c", "op": "==", "value": 1}]}]}
        tr = rules.evaluate(r, {"a": True, "b": False}, PARAMS)
        self.assertEqual(tr["status"], UNKNOWN)
        self.assertEqual(rules.needed_facts(tr), ["c"])
        tr = rules.evaluate(r, {"b": True}, PARAMS)
        self.assertEqual(rules.needed_facts(tr), ["a"])

    def test_status_of_matches_evaluate(self):
        r = {"all": [self.A, {"any": [self.B, {"not": self.A}]}]}
        for p in ({}, {"a": True}, {"a": False}, {"a": True, "b": False}, {"a": True, "b": True}):
            self.assertEqual(rules.status_of(r, p, PARAMS), st(r, p))

    def test_facts_in(self):
        r = {"all": [self.A, {"any": [self.B, self.A]}]}
        self.assertEqual(rules.facts_in(r), ["a", "b"])


class ValidationTests(unittest.TestCase):
    def test_rejects_malformed(self):
        bad = [
            {"all": []},
            {"all": [{"fact": "x", "op": "==", "value": 1}], "any": []},
            {"fact": "x", "op": "~", "value": 1},
            {"fact": "x", "op": "between", "value": [5, 1]},
            {"fact": "x", "op": "in", "value": 3},
            {"fact": "x", "op": "<", "value": "a"},
            {"fact": "x", "op": "<=", "value": {"param": "NOPE"}},
            {"fact": "x", "op": "=="},
            "nope",
        ]
        for r in bad:
            with self.assertRaises(rules.RuleError, msg=str(r)):
                rules.validate(r, None, PARAMS)

    def test_unknown_fact(self):
        with self.assertRaises(rules.RuleError):
            rules.validate({"fact": "zzz", "op": "==", "value": 1}, {"a"}, PARAMS)

    def test_valid_returns_facts(self):
        r = {"all": [{"fact": "a", "op": "==", "value": True, "label": {"en": "A"}},
                     {"not": {"fact": "b", "op": "in", "value": [1, 2]}}]}
        self.assertEqual(rules.validate(r, {"a", "b"}, PARAMS), {"a", "b"})


class ProbabilityTests(unittest.TestCase):
    def test_prob_pass(self):
        priors = {"a": [(True, 0.25), (False, 0.75)], "b": [(True, 0.5), (False, 0.5)]}
        A = {"fact": "a", "op": "==", "value": True}
        B = {"fact": "b", "op": "==", "value": True}
        self.assertAlmostEqual(rules.prob_pass({"all": [A, B]}, {}, priors), 0.125)
        self.assertAlmostEqual(rules.prob_pass({"any": [A, B]}, {}, priors), 1 - 0.75 * 0.5)
        self.assertAlmostEqual(rules.prob_pass({"not": A}, {}, priors), 0.75)
        self.assertEqual(rules.prob_pass({"all": [A, B]}, {"a": False}, priors), 0.0)
        self.assertEqual(rules.prob_pass(A, {"a": True}, priors), 1.0)


if __name__ == "__main__":
    unittest.main()
