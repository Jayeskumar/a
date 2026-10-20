import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar import blind, screening  # noqa: E402
from resumeradar.demo import JDS, get_demo  # noqa: E402
from resumeradar.extract import parse_resume  # noqa: E402

RESUME = """Priya Sharma
Backend Developer | Chennai | priya.sharma@mail.example | +91 98765 43210 | linkedin.com/in/priya-s

SUMMARY
Ms. Priya is a backend developer. She has built Django APIs and her team trusts her code.

EXPERIENCE
Developer, Acme - Jan 2024 - Present
- Built Django REST APIs on PostgreSQL for 2,000 users

SKILLS
Python, Django, PostgreSQL, Docker

EDUCATION
B.Tech Computer Science, IIT Madras, 2023 - CGPA 8.1/10

PERSONAL DETAILS
Date of Birth: 01-02-2001
Gender: Female
Marital Status: Single
Father's Name: Raman Sharma
Age: 25
Photo: attached
"""


class MaskTest(unittest.TestCase):
    def setUp(self):
        self.m = blind.mask(RESUME)
        self.t = self.m["text"]

    def test_identity_fields_removed(self):
        for leak in ("Priya", "Sharma", "priya.sharma", "98765", "linkedin.com", "IIT Madras", "Chennai",
                     "Female", "01-02-2001", "Single", "Raman", "Ms.", " She ", " her ", "2023", "attached"):
            self.assertNotIn(leak, self.t, leak)
        for kind in ("name", "contact", "pronoun", "gender", "institution", "location", "age", "marital",
                     "family", "photo", "grad_year"):
            self.assertIn(kind, self.m["counts"], kind)

    def test_job_content_survives(self):
        for keep in ("Django REST APIs", "PostgreSQL", "B.Tech Computer Science", "CGPA 8.1/10", "Jan 2024 - Present",
                     "2,000 users"):
            self.assertIn(keep, self.t, keep)
        p = parse_resume(self.t)
        self.assertEqual(p["education"]["degree"], "B.Tech")
        self.assertTrue({"python", "django", "postgresql", "docker"} <= set(p["skills"]))

    def test_pronouns_become_neutral(self):
        self.assertIn("They has built", self.t)
        self.assertIn("their team trusts their code", self.t)

    def test_counterfactual_swaps_identity(self):
        cf = blind.counterfactual(RESUME)
        self.assertNotIn("Priya", cf)
        self.assertIn(" He has built", cf)
        self.assertIn("Government Arts College", cf)
        self.assertIn("Male", cf)
        self.assertIn("Age: 31", cf)
        self.assertIn("Django REST APIs", cf)

    def test_strip_removes_values(self):
        st = blind.strip(RESUME)
        self.assertNotIn("Priya", st)
        self.assertNotIn("IIT", st)
        self.assertIn("Gender:", st)

    def test_mask_is_stable_on_jd(self):
        jd = blind.mask(JDS[0]["text"])["text"]
        self.assertNotIn("IIT", jd)
        self.assertNotIn("below 28", jd)
        self.assertIn("PostgreSQL", jd)


class BiasInvarianceTest(unittest.TestCase):
    """The headline fairness claim: in blind mode identity cannot move a score."""

    @classmethod
    def setUpClass(cls):
        d = get_demo()
        cls.resumes = d["resumes"]
        cls.report = screening.bias_check(JDS[0]["text"], cls.resumes)

    def test_blind_mode_is_exactly_invariant(self):
        b = self.report["blind"]
        self.assertTrue(b["invariant"])
        for cmp in (b["vs_stripped"], b["vs_swapped"]):
            self.assertEqual(cmp["max_abs_delta"], 0.0)
            self.assertTrue(cmp["identical_ranking"])
            self.assertEqual(cmp["spearman"], 1.0)

    def test_standard_mode_leaks_identity(self):
        # the JD prefers "IIT/NIT" and an age limit, so without masking identity moves scores
        s = self.report["standard"]
        self.assertFalse(s["invariant"])
        self.assertGreater(s["vs_swapped"]["max_abs_delta"], 0.0)

    def test_every_demo_resume_invariant_on_all_jds(self):
        for j in JDS[1:]:
            rep = screening.bias_check(j["text"], self.resumes)
            self.assertTrue(rep["blind"]["invariant"], j["id"])


if __name__ == "__main__":
    unittest.main()
