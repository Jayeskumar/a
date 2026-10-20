import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar.extract import parse_resume  # noqa: E402
from resumeradar.text import content_terms, stem  # noqa: E402
from resumeradar.tfidf import TfidfModel, cosine, doc_terms, top_contributions  # noqa: E402


class TfidfTest(unittest.TestCase):
    def setUp(self):
        self.docs = [["python", "django", "api"], ["python", "pandas", "sql"], ["react", "css", "html"]]
        self.m = TfidfModel().fit(self.docs)

    def test_idf_formula(self):
        # df(python)=2, N=3 -> ln(4/3)+1 ; unseen term -> ln(4/1)+1
        self.assertAlmostEqual(self.m.idf("python"), math.log(4 / 3.0) + 1)
        self.assertAlmostEqual(self.m.idf("kotlin"), math.log(4.0) + 1)
        self.assertGreater(self.m.idf("react"), self.m.idf("python"))

    def test_vectors_are_unit_length_and_sublinear(self):
        v = self.m.vector(["python", "python", "python", "django"])
        self.assertAlmostEqual(sum(x * x for x in v.values()), 1.0)
        raw_ratio = v["python"] / v["django"]
        idf_ratio = self.m.idf("python") / self.m.idf("django")
        self.assertAlmostEqual(raw_ratio, (1 + math.log(3)) * idf_ratio)

    def test_cosine_properties(self):
        a = self.m.vector(self.docs[0])
        b = self.m.vector(self.docs[1])
        c = self.m.vector(self.docs[2])
        self.assertAlmostEqual(cosine(a, a), 1.0)
        self.assertAlmostEqual(cosine(a, c), 0.0)
        self.assertAlmostEqual(cosine(a, b), cosine(b, a))
        self.assertTrue(0 < cosine(a, b) < 1)
        self.assertEqual(self.m.vector([]), {})

    def test_hand_computed_cosine(self):
        m = TfidfModel().fit([["a", "b"], ["a", "c"]])
        va, vb = m.vector(["a", "b"]), m.vector(["a", "c"])
        ia, ib = m.idf("a"), m.idf("b")
        expected = ia * ia / (ia * ia + ib * ib)
        self.assertAlmostEqual(cosine(va, vb), expected)

    def test_top_contributions_sum_to_cosine(self):
        a, b = self.m.vector(self.docs[0]), self.m.vector(self.docs[1])
        contrib = top_contributions(a, b, k=50)
        self.assertAlmostEqual(sum(c for _, c in contrib), cosine(a, b))
        self.assertEqual(contrib[0][0], "python")

    def test_skill_aware_terms_bridge_synonyms(self):
        r1, r2 = "Built UIs in JS and TS", "Built UIs in JavaScript and TypeScript"
        t1 = doc_terms(r1, parse_resume(r1)["skills"])
        t2 = doc_terms(r2, parse_resume(r2)["skills"])
        m = TfidfModel().fit([t1, t2, ["unrelated", "doc"]])
        plain = TfidfModel().fit([content_terms(r1), content_terms(r2), ["unrelated", "doc"]])
        self.assertGreater(cosine(m.vector(t1), m.vector(t2)),
                           cosine(plain.vector(content_terms(r1)), plain.vector(content_terms(r2))))

    def test_stemmer(self):
        self.assertEqual(stem("developing"), stem("developed"))
        self.assertEqual(stem("services"), stem("service"))
        self.assertEqual(stem("optimization"), stem("optimize"))
        self.assertEqual(stem("sql"), "sql")

    def test_content_terms_drop_noise(self):
        terms = content_terms("[CANDIDATE] built 25 APIs at https://x.com for the team me@x.com")
        self.assertNotIn("candidate", terms)
        self.assertNotIn("25", terms)
        self.assertNotIn("the", terms)
        self.assertIn("api", terms)


if __name__ == "__main__":
    unittest.main()
