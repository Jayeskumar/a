import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import eval_sets, safety  # noqa: E402


def flagged(text):
    return safety.detect(text)["flagged"]


class TestConcerningPhrases(unittest.TestCase):
    def test_self_harm_language_is_urgent(self):
        for text in ["I want to die", "thinking about killing myself", "I cut myself",
                     "I don't want to live anymore", "better off dead",
                     "I'm going to end it all", "kms", "suicidal thoughts again"]:
            r = safety.detect(text)
            self.assertTrue(r["flagged"], text)
            self.assertEqual((r["level"], r["category"]), ("urgent", "self_harm"), text)

    def test_hopelessness_is_concern(self):
        for text in ["Nothing will ever get better", "I feel hopeless", "I'm such a burden",
                     "I can't take it anymore", "there's no way out", "what's the point"]:
            r = safety.detect(text)
            self.assertTrue(r["flagged"], text)
            self.assertEqual(r["level"], "concern", text)
            self.assertEqual(r["category"], "hopelessness", text)

    def test_tanglish(self):
        self.assertTrue(flagged("Saaganum pola iruku"))
        self.assertTrue(flagged("vaazha pidikkala da"))
        self.assertTrue(flagged("Ellam mudinjiduchu"))

    def test_figurative_language_does_not_trigger(self):
        for text in ["This exam is killing me", "I'm dead tired", "I'd kill for a coffee",
                     "totally killed it", "my phone died", "I'm dying to see the results",
                     "the movie was to die for", "I hurt my knee", "bored to death",
                     "I died laughing at the show", "My laptop battery is dying",
                     "I could sleep forever after this exam week",
                     "There's no point in studying chapter 5"]:
            self.assertFalse(flagged(text), text)

    def test_negation(self):
        self.assertFalse(flagged("I'm not hopeless, just tired"))
        self.assertFalse(flagged("I feel hopeless at chess but it's fun"))
        r = safety.detect("I would never kill myself")
        self.assertTrue(r["flagged"])           # still a gentle check-in ...
        self.assertEqual(r["level"], "concern")  # ... at the softer level
        self.assertTrue(r["matches"][0]["negated"])

    def test_someone_else(self):
        r = safety.detect("My roommate said she wants to kill herself")
        self.assertTrue(r["flagged"])
        self.assertEqual(r["category"], "someone_else")
        r = safety.detect("My friend told me he wants to die")
        self.assertEqual(r["category"], "someone_else")

    def test_cooccurrence_layer(self):
        self.assertTrue(flagged("I'm tired of being alive"))
        self.assertTrue(flagged("Sometimes I want to sleep forever"))
        self.assertFalse(safety.detect("I'm tired of being alive", cooccurrence=False)["flagged"])
        r = safety.detect("I keep thinking everyone's life would be easier if I wasn't around")
        self.assertEqual(r["matches"][0]["rule"], "cooccurrence")
        self.assertFalse(flagged("I want to disappear into a good book this weekend"))

    def test_match_offsets(self):
        text = "Exams are killing me and nothing will ever get better."
        r = safety.detect(text)
        m = r["matches"][0]
        self.assertEqual(text[m["start"]:m["end"]], m["phrase"])
        self.assertEqual(m["phrase"].lower(), "nothing will ever get better")

    def test_empty(self):
        self.assertEqual(safety.detect("")["flagged"], False)
        self.assertEqual(safety.detect(None)["matches"], [])


class TestSafetySetsRegression(unittest.TestCase):
    def _run(self, ds):
        tp = sum(1 for t, g in ds if g and flagged(t))
        fp = sum(1 for t, g in ds if not g and flagged(t))
        return tp, sum(1 for _, g in ds if g), fp

    def test_heldout_direct_phrases(self):
        tp, pos, fp = self._run(eval_sets.SAFETY_HELDOUT)
        self.assertEqual((tp, fp), (pos, 0))

    def test_check3_at_least_first_run(self):
        tp, pos, fp = self._run(eval_sets.SAFETY_CHECK3)
        self.assertGreaterEqual(tp, 8)
        self.assertEqual(fp, 0)


if __name__ == "__main__":
    unittest.main()
