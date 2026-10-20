import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from schemesetu import search  # noqa: E402
from schemesetu.catalogue import Catalogue  # noqa: E402


class TokenizerTests(unittest.TestCase):
    def test_tamil_words_stay_whole(self):
        self.assertEqual(search.tokenize("பயிர் காப்பீட்டுத் திட்டம்!"), ["பயிர்", "காப்பீட்டுத்", "திட்டம்"])

    def test_mixed_and_case(self):
        self.assertEqual(search.tokenize("PM-KISAN: ₹6,000 / year"), ["pm", "kisan", "6", "000", "year"])

    def test_tamil_stemmer_normalises_case_forms(self):
        self.assertEqual(search.stem("காப்பீடு"), search.stem("காப்பீட்டுத்"))
        self.assertEqual(search.stem("வீடு"), search.stem("வீட்டை"))
        self.assertEqual(search.stem("ஓய்வூதியம்"), search.stem("ஓய்வூதியத்தை"))
        self.assertEqual(search.stem("பயிர்கள்"), "பயிர்")

    def test_english_stemmer(self):
        self.assertEqual(search.stem("pensions"), "pension")
        self.assertEqual(search.stem("widowed"), "widow")
        self.assertEqual(search.stem("scholarships"), "scholarship")


class TfidfTests(unittest.TestCase):
    def test_toy_index_ranks_and_idf(self):
        cmap = search.ConceptMap({"crop": ["crop", "பயிர்"], "insurance": ["insurance", "காப்பீடு"]})
        idx = search.TfidfIndex([("a", "crop insurance for farmers"), ("b", "old age pension"),
                                 ("c", "farmers loan")], cmap)
        res = idx.search("பயிர் காப்பீடு")  # Tamil query, English documents
        self.assertEqual(res["results"][0]["id"], "a")
        self.assertEqual([c["concept"] for c in res["concepts"]], ["crop", "insurance"])
        # a word in every document has the minimum idf
        self.assertLess(idx.idf["farmer"], idx.idf["pension"])
        self.assertEqual(idx.search("zzzz")["results"], [])

    def test_vectors_are_unit_length(self):
        cmap = search.ConceptMap({})
        idx = search.TfidfIndex([("a", "one two two three"), ("b", "two four")], cmap)
        for v in idx.vectors:
            self.assertAlmostEqual(sum(w * w for w in v.values()), 1.0, places=6)


class CatalogueSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = os.path.join(HERE, "data")
        cls.idx = search.build_index(Catalogue(data), data)

    def top(self, q):
        return self.idx.search(q, 3)["results"][0]["id"]

    def test_required_examples(self):
        self.assertEqual(self.top("பயிர் காப்பீடு"), "pmfby")
        self.assertEqual(self.top("pension for widow"), "ignwps")
        self.assertEqual(self.top("house"), "pmay_g")

    def test_more_bilingual_queries(self):
        self.assertEqual(self.top("கழிப்பறை"), "sbm_g")
        self.assertEqual(self.top("crop loan"), "kcc")
        self.assertEqual(self.top("முதியோர் ஓய்வூதியம்"), "ignoaps")
        self.assertEqual(self.top("கைம்பெண் ஓய்வூதியம்"), "ignwps")

    def test_empty_query(self):
        self.assertEqual(self.idx.search("the of and")["results"], [])


if __name__ == "__main__":
    unittest.main()
