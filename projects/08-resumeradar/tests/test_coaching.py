"""Bullet rewrites, ATS checker, interview prep, demo data and evaluation helpers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar import ats, interview, screening  # noqa: E402
from resumeradar.demo import JDS, LABELS, build_demo, synthetic_batch  # noqa: E402
from resumeradar.evaluate import extraction_eval, keyword_ats_scores, ndcg_at_k  # noqa: E402
from resumeradar.extract import parse_resume  # noqa: E402
from resumeradar.gaps import analyze_bullet, suggest_rewrite  # noqa: E402


class BulletTest(unittest.TestCase):
    def test_weak_bullet_is_flagged_and_rewritten(self):
        a = analyze_bullet("Responsible for developing APIs using Flask")
        self.assertFalse(a["action_verb"])
        self.assertFalse(a["quantified"])
        self.assertTrue(any("Weak phrase" in i for i in a["issues"]))
        self.assertTrue(a["rewrite"].startswith("Developed APIs using Flask"))
        self.assertIn("[add impact", a["rewrite"])

    def test_strong_bullet_passes(self):
        a = analyze_bullet("Reduced API latency by 40% by adding Redis caching for 2M daily requests")
        self.assertEqual(a["issues"], [])
        self.assertEqual(a["score"], 100)
        self.assertIsNone(a["rewrite"])

    def test_rewrite_templates(self):
        self.assertEqual(suggest_rewrite("Helped the team in deployment").split(" - ")[0], "Deployed [what] with the team")
        self.assertTrue(suggest_rewrite("Involved in testing and bug fixing").startswith("Tested [feature/module] and fixed [N] bugs"))
        self.assertTrue(suggest_rewrite("Worked on MySQL database").startswith("Designed MySQL database"))

    def test_first_person_and_passive(self):
        a = analyze_bullet("I was tasked with the migration which was completed by me")
        joined = " ".join(a["issues"])
        self.assertIn("first-person", joined)
        self.assertIn("Passive", joined)


class AtsTest(unittest.TestCase):
    def test_good_resume_scores_higher_than_bare_one(self):
        d = build_demo()
        good = next(r for r in d["resumes"] if r["id"] == "R01")["text"]
        bare = next(r for r in d["resumes"] if r["id"] == "R13")["text"]
        a, b = ats.check(parse_resume(good)), ats.check(parse_resume(bare))
        self.assertGreater(a["score"], b["score"])
        self.assertGreaterEqual(a["score"], 80)
        ids = {c["id"]: c for c in b["checks"]}
        self.assertEqual(ids["personal"]["status"], "warn")   # age / marital status present
        self.assertEqual(ids["bullets"]["status"], "fail")

    def test_literal_keyword_check_reports_synonyms(self):
        r = screening.analyze("SKILLS\nJS, TS, ReactJS, HTML5, CSS3\nEXPERIENCE\nDev, X - Jan 2024 - Present\n- Built ReactJS apps",
                              JDS[2]["text"], blind_mode=True)
        kw = {c["id"]: c for c in r["ats"]["checks"]}["keywords"]
        self.assertIn("only as synonyms", kw["message"])


class InterviewTest(unittest.TestCase):
    def test_questions_cover_claims_gaps_and_projects(self):
        d = build_demo()
        text = next(r for r in d["resumes"] if r["id"] == "R04")["text"]
        r = screening.analyze(text, JDS[0]["text"])
        types = {q["type"] for q in r["interview"]}
        self.assertTrue({"deep-dive", "gap", "project", "behavioural"} <= types)
        gap_skills = {q["skill"] for q in r["interview"] if q["type"] == "gap"}
        self.assertIn("PyTest", gap_skills)
        self.assertLessEqual(len(r["interview"]), 12)

    def test_bank_size(self):
        st = interview.bank_stats()
        self.assertGreaterEqual(st["questions"], 100)


class DemoAndEvalTest(unittest.TestCase):
    def test_demo_is_deterministic(self):
        a, b = build_demo(), build_demo()
        self.assertEqual(a, b)
        self.assertEqual(len(a["jds"]), 3)
        self.assertEqual(len(a["resumes"]), 20)
        self.assertEqual(set(LABELS), {r["id"] for r in a["resumes"]})
        for jd_id, labels in a["labels"].items():
            self.assertEqual(sum(1 for v in labels.values() if v >= 2), 5, jd_id)

    def test_synthetic_batch(self):
        batch = synthetic_batch(30)
        self.assertEqual(len(batch), 30)
        self.assertEqual(batch, synthetic_batch(30))

    def test_spearman_and_ndcg(self):
        self.assertAlmostEqual(screening.spearman([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertAlmostEqual(screening.spearman([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertAlmostEqual(screening.spearman([1, 2, 2, 3], [1, 2, 2, 3]), 1.0)
        gains = {"a": 3, "b": 0, "c": 2}
        self.assertAlmostEqual(ndcg_at_k(["a", "c", "b"], gains, 3), 1.0)
        self.assertLess(ndcg_at_k(["b", "c", "a"], gains, 3), 1.0)

    def test_extraction_beats_keyword_baseline(self):
        ev = extraction_eval()
        self.assertGreater(ev["resumeradar"]["recall"], ev["keyword_baseline"]["recall"])
        self.assertGreaterEqual(ev["resumeradar"]["f1"], 0.9)

    def test_keyword_baseline_misses_synonyms(self):
        d = build_demo()
        r15 = [r for r in d["resumes"] if r["id"] in ("R14", "R15")]
        kw = keyword_ats_scores(JDS[2]["text"], r15)
        self.assertGreater(kw["R14"], kw["R15"] + 30)   # same strength, different wording
        ours = screening.scores_only(JDS[2]["text"], r15)
        self.assertLess(ours["R14"] - ours["R15"], 20)


if __name__ == "__main__":
    unittest.main()
