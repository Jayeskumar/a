import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar import ontology  # noqa: E402
from resumeradar.extract import find_date_ranges, parse_resume, segment  # noqa: E402
from resumeradar.text import clean  # noqa: E402


def names(text):
    return {v["name"] for v in parse_resume(text)["skills"].values()}


class SkillExtractorTest(unittest.TestCase):
    def test_aliases_map_to_canonical_skills(self):
        got = names("Skills: JS, TS, ReactJS, Postgres, k8s, DRF, ML")
        for want in ("JavaScript", "TypeScript", "React", "PostgreSQL", "Kubernetes",
                     "Django REST Framework", "Machine Learning"):
            self.assertIn(want, got)

    def test_case_sensitive_short_names(self):
        self.assertEqual(names("Wrote services in Go and Python"), {"Go", "Python"})
        self.assertNotIn("Go", names("I go to the office every day and get things done"))
        self.assertIn("R", names("Analysed survey data using R and SQL"))
        self.assertNotIn("R", names("Worked in r and d labs"))

    def test_ambiguous_words_need_context(self):
        # lower-case "react"/"express" in prose are verbs; in a Skills section they are skills
        self.assertEqual(names("I react quickly and express ideas clearly"), set())
        got = names("SKILLS\nreact, express, node")
        self.assertTrue({"React", "Express.js", "Node.js"} <= got)

    def test_longest_match_wins(self):
        got = names("Wrote tests with React Testing Library")
        self.assertIn("React Testing Library", got)
        self.assertNotIn("React", got)
        self.assertIn("Django REST Framework", names("APIs in Django REST Framework"))

    def test_multi_skill_phrase(self):
        got = names("Strong in Data Structures and Algorithms")
        self.assertTrue({"Data Structures", "Algorithms"} <= got)
        self.assertTrue({"MongoDB", "Express.js", "React", "Node.js"} <= names("Built apps on the MERN stack"))

    def test_symbols_and_versions(self):
        got = names("Skills: C++, C#, .NET, Node.js, ES6+, HTML5/CSS3, CI/CD, A/B testing")
        for want in ("C++", "C#", ".NET", "Node.js", "JavaScript", "HTML", "CSS", "CI/CD", "A/B Testing"):
            self.assertIn(want, got)

    def test_urls_and_emails_are_ignored(self):
        got = names("Contact: dev@python.org | https://github.com/someone/react-app | www.java.com")
        self.assertEqual(got, set())

    def test_rest_word_is_not_rest_api(self):
        self.assertNotIn("REST APIs", names("Handled the rest of the migration"))
        self.assertIn("REST APIs", names("Designed REST endpoints and RESTful services"))

    def test_evidence_section_tracking(self):
        p = parse_resume("EXPERIENCE\n- Built Django services\n\nSKILLS\nDjango, Kafka")
        self.assertTrue(p["skills"]["django"]["evidence"])
        self.assertFalse(p["skills"]["apache-kafka"]["evidence"])

    def test_ontology_size_and_integrity(self):
        self.assertGreaterEqual(len(ontology.SKILLS), 200)
        for s in ontology.SKILLS.values():
            for p in s.prereqs:
                self.assertIn(p, ontology.SKILLS)

    def test_bad_ontology_rows_are_rejected(self):
        with self.assertRaises(ontology.OntologyError):
            ontology.build("A | Cat | | Missing | | 1", {})
        with self.assertRaises(ontology.OntologyError):
            ontology.build("A | Cat | foo | | | 1\nB | Cat | foo | | | 1", {})


class SectionsAndFactsTest(unittest.TestCase):
    def test_sections_and_inline_headers(self):
        seg = segment(clean("Jane\nWORK EXPERIENCE\nDev at X\nSkills: Python, SQL\nEducation\nB.Tech"))
        secs = [s for s, c, h in seg if c]
        self.assertEqual(secs, ["header", "experience", "skills", "education"])

    def test_date_ranges(self):
        r = find_date_ranges("Engineer, Acme - Jan 2024 - Dec 2024")
        self.assertEqual(r[0][2], 12)
        self.assertEqual(find_date_ranges("Dev | 06/2025 to 08/2025")[0][2], 3)
        self.assertEqual(len(find_date_ranges("Scored 2019 marks in 2020")), 0)

    def test_experience_years_with_internship_and_overlap(self):
        text = ("EXPERIENCE\nEngineer, A - Jan 2024 - Dec 2024\n- Built APIs\n"
                "Consultant, B - Jun 2024 - Dec 2024\n- Overlapping role\n"
                "Intern, C - Jan 2023 - Jun 2023\n- Wrote tests\n")
        exp = parse_resume(text)["experience"]
        self.assertEqual(exp["fulltime_months"], 12)      # overlap merged, not 19
        self.assertEqual(exp["intern_months"], 6)
        self.assertAlmostEqual(exp["years"], (12 + 0.5 * 6) / 12.0, places=2)

    def test_present_uses_fixed_reference_month(self):
        exp = parse_resume("EXPERIENCE\nDev, X - Jan 2026 - Present\n- Built things")["experience"]
        self.assertEqual(exp["fulltime_months"], 10)   # Jan..Oct 2026 (AS_OF = 2026-10)

    def test_stated_years_when_no_dates(self):
        exp = parse_resume("SUMMARY\nDeveloper with 3+ years of experience in Java.")["experience"]
        self.assertEqual(exp["years"], 3.0)

    def test_education(self):
        e = parse_resume("EDUCATION\nB.Tech Computer Science and Engineering, Some College, 2024 - CGPA 8.4/10")["education"]
        self.assertEqual((e["level"], e["degree"], e["field"]), (2, "B.Tech", "Computer Science"))
        self.assertEqual(e["entries"][0]["score"], "CGPA 8.4/10")
        e2 = parse_resume("EDUCATION\nM.Sc Data Science, X University, 2024\nB.Sc Statistics, Y College, 2022")["education"]
        self.assertEqual(e2["level"], 3)

    def test_projects_and_certifications(self):
        p = parse_resume("PROJECTS\nShopKart - Django, PostgreSQL\n- Built a store\n\nCERTIFICATIONS\nAWS Certified Developer")
        self.assertEqual(p["projects"][0]["title"], "ShopKart")
        self.assertIn("django", p["projects"][0]["skills"])
        self.assertEqual(p["certifications"], ["AWS Certified Developer"])


if __name__ == "__main__":
    unittest.main()
