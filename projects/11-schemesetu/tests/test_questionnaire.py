import os
import statistics
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from schemesetu import config, questionnaire, synth  # noqa: E402
from schemesetu.engine import Engine  # noqa: E402


class _FakeCat(object):
    """Minimal catalogue: 3 schemes over 3 facts, to test selection in isolation."""
    params = {}
    gates = []
    inferences = []

    def __init__(self):
        A = {"fact": "a", "op": "==", "value": True}
        B = {"fact": "b", "op": "==", "value": True}
        C = {"fact": "c", "op": "==", "value": True}
        self.schemes = [
            {"id": "s1", "rule": {"all": [A, B]}},
            {"id": "s2", "rule": {"all": [A, C]}},
            {"id": "s3", "rule": {"all": [A]}},
        ]
        self.questions = [{"id": "c", "type": "bool"}, {"id": "b", "type": "bool"}, {"id": "a", "type": "bool"}]
        self.q_by_id = dict((q["id"], q) for q in self.questions)
        self.by_id = dict((s["id"], s) for s in self.schemes)

    def close(self, profile):
        return dict(profile), {}

    def truth_answer(self, qid, truth):
        return truth.get(qid)


PRIORS = {"a": [(True, 0.5), (False, 0.5)], "b": [(True, 0.5), (False, 0.5)], "c": [(True, 0.5), (False, 0.5)]}


class SelectionUnitTests(unittest.TestCase):
    def setUp(self):
        self.sel = questionnaire.Selector(_FakeCat(), PRIORS)

    def test_entropy(self):
        self.assertAlmostEqual(questionnaire.entropy(0.5), 1.0)
        self.assertEqual(questionnaire.entropy(0.0), 0.0)
        self.assertEqual(questionnaire.entropy(1.0), 0.0)

    def test_picks_question_touching_most_schemes(self):
        # 'a' appears in all three schemes, 'b'/'c' in one each -> 'a' carries most information
        for strat in ("ig", "resolve"):
            nq = self.sel.next_question({}, strategy=strat)
            self.assertEqual(nq["id"], "a", strat)
            self.assertEqual(sorted(nq["affects"]), ["s1", "s2", "s3"])

    def test_static_uses_bank_order(self):
        self.assertEqual(self.sel.next_question({}, strategy="static")["id"], "c")

    def test_no_answer_is_never_reasked_and_stops(self):
        self.assertIsNone(self.sel.next_question({"a": False}))  # a=False decides every scheme
        nq = self.sel.next_question({"a": True})
        self.assertIn(nq["id"], ("b", "c"))
        self.assertIsNone(self.sel.next_question({"a": True, "b": True, "c": False}))

    def test_skipped_questions_excluded(self):
        nq = self.sel.next_question({"a": True}, skipped=["b"])
        self.assertEqual(nq["id"], "c")
        self.assertIsNone(self.sel.next_question({"a": True}, skipped=["b", "c"]))

    def test_simulate_minimal(self):
        sim = self.sel.simulate({"a": False, "b": True, "c": True})
        self.assertEqual([s["id"] for s in sim["steps"]], ["a"])  # one answer settles everything

    def test_unknown_strategy(self):
        with self.assertRaises(ValueError):
            self.sel.next_question({}, strategy="random")


class SelectionOnCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(os.path.join(HERE, "data"))
        cls.pop = synth.population(40, config.EVAL_SEED)

    def test_priors_are_distributions(self):
        for qid, dist in self.e.priors.items():
            self.assertAlmostEqual(sum(p for _, p in dist), 1.0, places=6, msg=qid)
            self.assertTrue(all(p > 0 for _, p in dist), qid)

    def test_first_question_has_positive_gain(self):
        nq = self.e.next_question({})
        self.assertGreater(nq["info_gain_bits"], 0)
        self.assertEqual(nq["open_schemes"], len(self.e.cat.schemes))
        self.assertTrue(nq["why"]["en"] and nq["why"]["ta"])

    def test_simulation_reaches_same_decisions_as_full_form(self):
        for p in self.pop:
            sim = self.e.selector.simulate(p)
            self.assertEqual(self.e.statuses(sim["profile"]), self.e.statuses(p))
            self.assertLessEqual(len(sim["steps"]), len(self.e.cat.questions))
            ids = [s["id"] for s in sim["steps"]]
            self.assertEqual(len(ids), len(set(ids)))  # never asks twice

    def test_adaptive_beats_fixed_order_and_full_form(self):
        ig = statistics.mean(len(self.e.selector.simulate(p, "ig")["steps"]) for p in self.pop)
        static = statistics.mean(len(self.e.selector.simulate(p, "static")["steps"]) for p in self.pop)
        self.assertLess(ig, static)
        self.assertLess(ig, len(self.e.cat.atomic))

    def test_skipping_leaves_possibly(self):
        nq = self.e.next_question({})
        ev = self.e.evaluate({})
        self.assertEqual(ev["counts"]["possibly"], len(self.e.cat.schemes))
        # skip every question: the selector must terminate with schemes still "possibly"
        skipped, prof = [], {}
        for _ in range(60):
            nq = self.e.next_question(prof, skipped)
            if nq is None:
                break
            skipped.append(nq["id"])
        self.assertIsNone(self.e.next_question(prof, skipped))
        self.assertEqual(self.e.evaluate(prof)["counts"]["possibly"], len(self.e.cat.schemes))


if __name__ == "__main__":
    unittest.main()
