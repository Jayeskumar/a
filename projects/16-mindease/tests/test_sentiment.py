import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import eval_sets, sentiment as S  # noqa: E402


def label(text):
    return S.analyse(text)["label"]


class TestNegation(unittest.TestCase):
    def test_not_happy_is_negative(self):
        r = S.analyse("I am not happy")
        self.assertEqual(r["label"], "negative")
        self.assertTrue(r["tokens"][0]["negated"])
        self.assertIn("negated by 'not'", r["tokens"][0]["rules"])

    def test_not_bad_is_positive(self):
        self.assertEqual(label("not bad"), "positive")
        self.assertEqual(label("The test was not bad at all"), "positive")

    def test_contractions_and_spelling_variants(self):
        self.assertEqual(label("I don't feel stressed"), "positive")
        self.assertEqual(label("I dont feel stressed"), "positive")
        self.assertEqual(label("I wasn't anxious at all"), "positive")
        self.assertEqual(label("I never enjoyed the class"), "negative")

    def test_negation_window_and_clause_boundary(self):
        # "not" is 4 tokens before "happy": outside the 3-token window
        self.assertEqual(label("not that it made me very really happy"), "positive")
        # a comma stops negation: "not" does not flip "happy" in the next clause
        self.assertEqual(label("Not really, happy now"), "positive")

    def test_negated_phrase(self):
        self.assertEqual(label("I am not stressed out"), "positive")
        self.assertEqual(label("No worries today"), "positive")

    def test_tamil_post_negation(self):
        r = S.analyse("Nalla illa")
        self.assertEqual(r["label"], "negative")
        self.assertIn("Tamil", r["tokens"][0]["rules"][0])
        self.assertEqual(label("Nalla iruku"), "positive")


class TestModifiers(unittest.TestCase):
    def test_intensifier_increases_magnitude(self):
        plain = S.analyse("I am tired")["compound"]
        very = S.analyse("I am very tired")["compound"]
        romba = S.analyse("romba tired")["compound"]
        self.assertLess(very, plain)
        self.assertLess(romba, plain)

    def test_diminisher_reduces_magnitude(self):
        self.assertGreater(S.analyse("konjam stressed")["compound"],
                           S.analyse("stressed")["compound"])

    def test_semma_is_dual(self):
        alone = S.analyse("semma")
        self.assertEqual(alone["label"], "positive")
        r = S.analyse("semma tension")
        self.assertEqual(r["label"], "negative")
        self.assertIn("intensified by 'semma'", r["tokens"][0]["rules"])

    def test_but_contrast(self):
        r = S.analyse("I was nervous but it went really well")
        self.assertEqual(r["label"], "positive")
        self.assertTrue(any("after 'but'" in x for t in r["tokens"] for x in t["rules"]))
        self.assertEqual(label("It was fun but now I'm so tired and upset"), "negative")

    def test_caps_and_exclamation(self):
        self.assertGreater(S.analyse("I am HAPPY")["compound"], S.analyse("I am happy")["compound"])
        self.assertGreater(S.analyse("I am happy!!")["compound"], S.analyse("I am happy")["compound"])

    def test_phrases(self):
        self.assertEqual(label("couldn't sleep at all"), "negative")
        self.assertEqual(label("slept well"), "positive")
        self.assertEqual(label("vera level day"), "positive")
        self.assertEqual(label("Thookam varala"), "negative")
        self.assertEqual(label("totally killed it in the viva"), "positive")


class TestEmojiEmotionAndOutput(unittest.TestCase):
    def test_emoji_and_emoticons(self):
        self.assertEqual(label("\U0001F622"), "negative")
        self.assertEqual(label("exam over \U0001F389"), "positive")
        self.assertEqual(label("ok :("), "negative")
        self.assertEqual(label("Feeling grateful ❤️"), "positive")

    def test_offsets_match_original_text(self):
        text = "So happy ❤️ and \U0001F44D\U0001F3FD but tired"
        for t in S.analyse(text)["tokens"]:
            self.assertEqual(text[t["start"]:t["end"]], t["text"])

    def test_emotions(self):
        r = S.analyse("So much tension and worry, also really tired")
        emos = [e["emotion"] for e in r["emotions"]]
        self.assertEqual(emos[0], "anxiety")
        self.assertIn("tiredness", emos)
        self.assertAlmostEqual(sum(e["share"] for e in r["emotions"]), 1.0, places=2)
        # negated emotion words do not count as that emotion
        self.assertEqual(S.analyse("not anxious")["emotions"], [])

    def test_neutral_and_empty(self):
        self.assertEqual(label("I have a viva on Monday."), "neutral")
        r = S.analyse("")
        self.assertEqual((r["compound"], r["label"], r["tokens"]), (0.0, "neutral", []))
        self.assertTrue(S.analyse("ok")["label"] == "neutral")  # mild word stays neutral

    def test_summary_is_gentle(self):
        s = S.analyse("I feel awful and drained")["summary"]
        self.assertIn("heavy", s)
        self.assertNotIn("depress", s.lower())

    def test_compound_range(self):
        for text, _ in eval_sets.SENTIMENT_DEV + eval_sets.SENTIMENT_HELDOUT:
            c = S.analyse(text)["compound"]
            self.assertTrue(-1.0 <= c <= 1.0)


class TestAccuracyRegression(unittest.TestCase):
    """Guards against silently breaking the analyser; numbers are reported in REPORT.md."""

    def _acc(self, ds):
        m = {"pos": "positive", "neg": "negative", "neu": "neutral"}
        return sum(label(t) == m[g] for t, g in ds) / len(ds)

    def test_dev_and_heldout(self):
        self.assertGreaterEqual(self._acc(eval_sets.SENTIMENT_DEV), 0.9)
        self.assertGreaterEqual(self._acc(eval_sets.SENTIMENT_HELDOUT), 0.85)

    def test_rules_beat_plain_word_counting(self):
        ds = eval_sets.SENTIMENT_HELDOUT + eval_sets.SENTIMENT_FRESH
        m = {"pos": "positive", "neg": "negative", "neu": "neutral"}
        rules = sum(label(t) == m[g] for t, g in ds)
        base = sum(S.baseline_label(t) == m[g] for t, g in ds)
        self.assertGreater(rules, base)


if __name__ == "__main__":
    unittest.main()
