import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civiclens.features import TfidfVectorizer, doc_terms  # noqa: E402
from civiclens.text import (char_ngrams, concepts, edit_distance_le1, graphemes, jaccard, script_of,  # noqa: E402
                            shingles, tokenize)


class TestTokenize(unittest.TestCase):
    def test_tamil_words_stay_whole(self):
        # Python's \w treats Tamil vowel signs / virama as non-word characters and splits the word.
        self.assertNotEqual(re.findall(r"\w+", "குப்பை")[0], "குப்பை")
        self.assertEqual(tokenize("குப்பை அள்ளவில்லை!"), ["குப்பை", "அள்ளவில்லை"])

    def test_mixed_script_and_punctuation(self):
        self.assertEqual(tokenize("Street-light NOT working, காந்தி தெருவில்."),
                         ["street", "light", "not", "working", "காந்தி", "தெருவில்"])

    def test_latin_lowercase_and_repeat_collapse(self):
        self.assertEqual(tokenize("Plsss HELP!!!"), ["plss", "help"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])

    def test_zero_width_joiner_kept_inside(self):
        toks = tokenize("க்‍ஷ test")
        self.assertEqual(len(toks), 2)


class TestGraphemes(unittest.TestCase):
    def test_tamil_graphemes(self):
        self.assertEqual(graphemes("குப்பை"), ["கு", "ப்", "பை"])

    def test_latin_graphemes(self):
        self.assertEqual(graphemes("road"), ["r", "o", "a", "d"])

    def test_char_ngrams_have_boundaries_and_whole_letters(self):
        g = char_ngrams("road", (3,))
        self.assertEqual(g, ["<ro", "roa", "oad", "ad>"])
        # Tamil n-grams never split a letter from its vowel sign
        for gram in char_ngrams("குப்பை", (3,)):
            self.assertFalse(gram[0] in "்ைு")


class TestConcepts(unittest.TestCase):
    def test_three_languages_share_concepts(self):
        en = set(concepts("Garbage not collected near Murugan temple"))
        ta = set(concepts("முருகன் கோவில் அருகில் குப்பை அள்ளவில்லை"))
        tg = set(concepts("Murugan kovil kitta kuppai edukala"))
        for s in (en, ta, tg):
            self.assertTrue({"garbage", "murugan", "temple"} <= s, s)

    def test_tamil_suffix_stripping_by_grapheme_prefix(self):
        self.assertEqual(concepts("தெருவில்"), ["street"])          # street + locative suffix
        self.assertEqual(concepts("சாலையில்"), ["road"])

    def test_grapheme_prefix_does_not_confuse_similar_words(self):
        # பள்ளி (school) and பள்ளம் (pit) share code points, not letters
        self.assertEqual(concepts("பள்ளி"), ["school"])
        self.assertEqual(concepts("பள்ளம்"), ["pit"])

    def test_phrase_merging(self):
        self.assertIn("streetlight", concepts("street light not working"))
        self.assertIn("notworking", concepts("street light not working"))
        self.assertIn("drinkingwater", concepts("sewage in drinking water"))

    def test_fillers_dropped(self):
        self.assertEqual(concepts("Sir please kindly take action"), [])

    def test_typo_tolerance(self):
        self.assertIn("accident", concepts("acciednt yesterday"))
        self.assertIn("manhole", concepts("open manhloe"))
        self.assertTrue(edit_distance_le1("pothole", "pothle"))
        self.assertTrue(edit_distance_le1("drainage", "drianage"))
        self.assertFalse(edit_distance_le1("garbage", "baggage"))

    def test_script_detection(self):
        self.assertEqual(script_of("குப்பை அள்ளவில்லை"), "ta")
        self.assertEqual(script_of("drainage overflow ah iruku"), "tg")
        self.assertEqual(script_of("street light not working near bus stand"), "en")

    def test_shingles_and_jaccard(self):
        a = shingles("street light not working near bus stand")
        b = shingles("bus stand kitta street light eriyala")
        self.assertEqual(a, b)                       # word order and language do not matter
        self.assertAlmostEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(jaccard(set(), set()), 1.0)


class TestTfidf(unittest.TestCase):
    def test_blocks_are_normalised_and_weighted(self):
        docs = [doc_terms(t) for t in ["pothole on road", "garbage on road", "pothole near school", "garbage bin full"]]
        v = TfidfVectorizer(min_df=1, block_weights={"w": 1.0, "c": 0.5, "k": 1.0}).fit(docs)
        idx, val = v.transform_one(docs[0])
        norms = {}
        for j, x in zip(idx, val):
            norms[v.names[j][0]] = norms.get(v.names[j][0], 0.0) + x * x
        self.assertAlmostEqual(norms["w"] ** 0.5, 1.0, places=6)
        self.assertAlmostEqual(norms["c"] ** 0.5, 0.5, places=6)
        self.assertEqual(list(idx), sorted(idx))

    def test_unknown_terms_ignored_and_min_df(self):
        docs = [doc_terms(t) for t in ["pothole road", "pothole lane"]]
        v = TfidfVectorizer(min_df=2, blocks=("w",)).fit(docs)
        self.assertEqual(v.names, ["w:pothole"])
        self.assertEqual(v.transform_one(doc_terms("zebra crossing")), ((), ()))


if __name__ == "__main__":
    unittest.main()
