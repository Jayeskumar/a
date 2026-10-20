import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phishguard.naive_bayes import MultinomialNB  # noqa: E402
from phishguard import text as text_mod  # noqa: E402


def toy():
    # scam: "free free win", "win cash"     ham: "hi free", "hi lunch"
    docs = [{"free": 2, "win": 1}, {"win": 1, "cash": 1}, {"hi": 1, "free": 1}, {"hi": 1, "lunch": 1}]
    return MultinomialNB(alpha=1.0).fit(docs, [1, 1, 0, 0])


class ToyNaiveBayesTest(unittest.TestCase):
    """Hand-computed example.

    V = {free, win, cash, hi, lunch} -> |V| = 5
    scam token total = 5, ham token total = 4
    P(free|scam) = (2+1)/(5+5) = 0.3    P(free|ham) = (1+1)/(4+5) = 2/9
    P(win|scam)  = (2+1)/10    = 0.3    P(win|ham)  = (0+1)/9     = 1/9
    P(cash|scam) = (1+1)/10    = 0.2    P(hi|ham)   = (2+1)/9     = 3/9
    For d = "free win":  scam joint = 0.5*0.3*0.3 = 0.045,  ham joint = 0.5*(2/9)*(1/9) = 1/81
    """

    def test_counts_and_vocab(self):
        nb = toy()
        self.assertEqual(len(nb.vocab), 5)
        self.assertEqual(nb.class_tokens, [4.0, 5.0])
        self.assertEqual(nb.class_docs, [2, 2])

    def test_likelihoods(self):
        nb = toy()
        self.assertAlmostEqual(math.exp(nb.log_likelihood("free", 1)), 0.3)
        self.assertAlmostEqual(math.exp(nb.log_likelihood("free", 0)), 2 / 9)
        self.assertAlmostEqual(math.exp(nb.log_likelihood("win", 0)), 1 / 9)
        self.assertAlmostEqual(math.exp(nb.log_likelihood("cash", 1)), 0.2)
        self.assertAlmostEqual(math.exp(nb.log_likelihood("hi", 0)), 3 / 9)
        self.assertAlmostEqual(math.exp(nb.log_prior(1)), 0.5)

    def test_posterior_hand_computed(self):
        nb = toy()
        expected = 0.045 / (0.045 + 1 / 81)
        self.assertAlmostEqual(nb.predict_proba({"free": 1, "win": 1}), expected, places=10)
        self.assertEqual(nb.predict({"free": 1, "win": 1}), 1)
        self.assertEqual(nb.predict({"hi": 1, "lunch": 1}), 0)

    def test_llr_and_unknown_tokens(self):
        nb = toy()
        self.assertAlmostEqual(nb.llr("free"), math.log(0.3 / (2 / 9)))
        self.assertGreater(nb.llr("win"), 0)
        self.assertLess(nb.llr("hi"), 0)
        # unseen words are ignored, leaving only the prior (log-odds 0)
        self.assertAlmostEqual(nb.log_odds({"zzz": 3}), 0.0)

    def test_contributions_sum_to_log_odds(self):
        nb = toy()
        doc = {"free": 2, "hi": 1, "cash": 1}
        total = sum(c for _, _, _, c in nb.contributions(doc))
        prior = nb.log_prior(1) - nb.log_prior(0)
        self.assertAlmostEqual(total + prior, nb.log_odds(doc))

    def test_top_features(self):
        top = toy().top_features(k=2, min_count=1)
        self.assertEqual(top["scam"][0][0], "win")
        self.assertEqual(top["ham"][0][0], "hi")

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            MultinomialNB().fit([{"a": 1}], [2])
        with self.assertRaises(ValueError):
            MultinomialNB().fit([], [])
        with self.assertRaises(ValueError):
            MultinomialNB().fit([{"a": 1}], [1, 0])


class TextFeatureTest(unittest.TestCase):
    def test_placeholders(self):
        w = text_mod.words("Pay Rs.1,999 to hr.recruit@ybl or call 9876543210 at bit.ly/abc")
        for p in ("__money__", "__upi__", "__phone__", "__url__"):
            self.assertIn(p, w)
        self.assertNotIn("9876543210", " ".join(w))

    def test_feature_kinds_and_char_weight(self):
        f = text_mod.features("KYC update")
        self.assertEqual(f["w:kyc"], 1.0)
        self.assertEqual(f["b:kyc update"], 1.0)
        char_total = sum(v for k, v in f.items() if k.startswith("c:"))
        self.assertAlmostEqual(char_total, 2.0)  # one unit per word

    def test_char_ngrams(self):
        self.assertEqual(text_mod.char_ngrams("otp", 3, 3), ["#ot", "otp", "tp#"])


if __name__ == "__main__":
    unittest.main()
