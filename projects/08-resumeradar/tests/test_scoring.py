import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar import config, screening  # noqa: E402
from resumeradar.demo import JDS  # noqa: E402
from resumeradar.jd import bias_lint, parse_jd  # noqa: E402
from resumeradar.scoring import implied_map, recommendation, skill_credit  # noqa: E402

JD = """Python Developer
Requirements
- 2+ years of experience
- Strong Python and Django or Flask
- PostgreSQL and Docker
Nice to have
- AWS, Redis
Education
- B.E./B.Tech in Computer Science or related field
"""

GOOD = """EXPERIENCE
Backend Engineer, Acme - Jan 2023 - Present
- Built Django REST APIs on PostgreSQL, deployed with Docker on AWS
SKILLS
Python, Django, PostgreSQL, Docker, AWS, Redis
EDUCATION
B.Tech Computer Science, Some College, 2022
"""


def score(resume, jd=JD, blind=True):
    return screening.analyze(resume, jd, blind_mode=blind)


class JdParserTest(unittest.TestCase):
    def test_must_nice_groups_and_weights(self):
        jd = parse_jd(JD)
        must = {r["label"]: r for r in jd["must"]}
        nice = {r["label"] for r in jd["nice"]}
        self.assertIn("Django / Flask", must)                  # either-or group
        self.assertEqual(must["Python"]["weight"], config.TITLE_SKILL_WEIGHT)  # in the title
        self.assertEqual(must["Django / Flask"]["weight"], config.STRONG_CUE_WEIGHT)
        self.assertTrue({"PostgreSQL", "Docker"} <= set(must))
        self.assertEqual(nice, {"AWS", "Redis"})
        self.assertEqual(jd["min_years"], 2.0)
        self.assertEqual(jd["education"]["level"], 2)
        self.assertTrue(jd["education"]["related_ok"])

    def test_demo_jds_parse(self):
        for j in JDS:
            jd = parse_jd(j["text"])
            self.assertGreaterEqual(len(jd["must"]), 5, j["id"])
        fe = parse_jd(JDS[2]["text"])
        self.assertEqual(fe["min_years"], 1.0)
        self.assertEqual(fe["education"]["level"], 0)          # "or equivalent practical experience"

    def test_soft_skills_are_reported_not_scored(self):
        jd = parse_jd("Analyst\nRequirements\n- SQL and Excel\n- Excellent communication skills")
        self.assertIn("Communication", jd["soft_names"])
        self.assertNotIn("communication", jd["skill_ids"])

    def test_bias_lint(self):
        cats = {f["category"] for f in bias_lint("IIT/NIT graduates only. Age below 25. He must be a rockstar.")}
        self.assertEqual(cats, {"College prestige", "Age limit", "Gendered wording"})
        self.assertEqual(bias_lint("We value skills and kindness."), [])


class CreditTest(unittest.TestCase):
    def setUp(self):
        self.cand = {"django": {"surfaces": ["Django"], "evidence": True},
                     "javascript": {"surfaces": ["JS"], "evidence": False}}
        self.implied = implied_map(set(self.cand))
        self.families = {"py-web": "django"}

    def test_kinds(self):
        self.assertEqual(skill_credit("django", self.cand, self.implied, self.families)[:2], (1.0, "direct"))
        self.assertEqual(skill_credit("javascript", self.cand, self.implied, self.families)[:2], (1.0, "alias"))
        c, kind, via = skill_credit("python", self.cand, self.implied, self.families)
        self.assertEqual((c, kind, via), (config.IMPLIED_CREDIT_DIRECT, "implied", "Django"))
        only_django = {"django": self.cand["django"]}
        c, kind, _ = skill_credit("programming-basics", only_django, implied_map({"django"}), self.families)
        self.assertEqual((c, kind), (config.IMPLIED_CREDIT_INDIRECT, "implied"))   # Django -> Python -> basics
        self.assertEqual(skill_credit("flask", self.cand, self.implied, self.families)[:2],
                         (config.RELATED_CREDIT, "related"))
        self.assertEqual(skill_credit("kotlin", self.cand, self.implied, self.families)[:2], (0.0, "missing"))


class ScoreTest(unittest.TestCase):
    def test_breakdown_adds_up(self):
        r = score(GOOD)
        m = r["match"]
        self.assertAlmostEqual(sum(b["points"] for b in m["breakdown"]), r["score"], delta=0.1)
        self.assertAlmostEqual(sum(b["weight"] for b in m["breakdown"]), 1.0, places=3)
        self.assertGreaterEqual(r["score"], config.SHORTLIST_AT)
        self.assertEqual(m["recommendation"]["level"], "strong")

    def test_adding_a_missing_must_have_raises_score(self):
        weak = GOOD.replace("Docker", "").replace("deployed with  on AWS", "on AWS")
        self.assertLess(score(weak)["score"], score(GOOD)["score"])
        missing = [r["label"] for r in score(weak)["match"]["must"] if r["credit"] == 0]
        self.assertIn("Docker", missing)

    def test_synonyms_score_like_canonical_names(self):
        canon = "SKILLS\nJavaScript, TypeScript, React, HTML, CSS, Git\nEXPERIENCE\nDev, X - Jan 2024 - Present\n- Built React apps"
        alias = "SKILLS\nJS, TS, ReactJS, HTML5, CSS3, git\nEXPERIENCE\nDev, X - Jan 2024 - Present\n- Built ReactJS apps"
        jd = JDS[2]["text"]
        a, b = score(canon, jd)["match"], score(alias, jd)["match"]
        self.assertEqual([r["credit"] for r in a["must"]], [r["credit"] for r in b["must"]])
        self.assertTrue(any(f["type"] == "alias" for f in b["flags"]))

    def test_experience_component(self):
        junior = GOOD.replace("Jan 2023", "Jan 2026")       # 10 months vs 2 years required
        exp = {b["key"]: b for b in score(junior)["match"]["breakdown"]}["experience"]
        self.assertAlmostEqual(exp["score"], (10 / 12.0) / 2.0, places=2)

    def test_no_minimum_experience_is_not_scored(self):
        r = score(GOOD, JDS[1]["text"])     # analyst JD: 0-2 years
        keys = [b["key"] for b in r["match"]["breakdown"]]
        self.assertNotIn("experience", keys)
        self.assertIn("experience", [n["key"] for n in r["match"]["not_scored"]])

    def test_keyword_stuffing_flag(self):
        stuffed = "SKILLS\n" + ", ".join(["Python", "Java", "C++", "Go", "Rust", "Kotlin", "Swift", "PHP", "Ruby",
                                          "Scala", "Django", "Flask", "React", "Angular", "Vue.js", "PostgreSQL",
                                          "MySQL", "MongoDB", "Redis", "AWS", "Azure", "GCP", "Docker",
                                          "Kubernetes", "Terraform", "Kafka", "Spark"])
        r = score(stuffed)
        self.assertTrue(any(f["type"] == "stuffing" for f in r["match"]["flags"]))
        ev = {b["key"]: b for b in r["match"]["breakdown"]}["evidence"]
        self.assertEqual(ev["score"], 0.0)

    def test_recommendation_bands(self):
        self.assertEqual(recommendation(80)["level"], "strong")
        self.assertEqual(recommendation(60)["level"], "review")
        self.assertEqual(recommendation(20)["level"], "low")

    def test_jd_without_known_skills_is_flagged(self):
        r = score("A friendly person who loves people and coffee and teamwork.",
                  "We want someone friendly who loves people and coffee.")
        self.assertEqual(r["match"]["recommendation"]["level"], "review")
        self.assertTrue(any(f["type"] == "jd" for f in r["match"]["flags"]))

    def test_ranking_orders_by_score(self):
        res = screening.screen(JD, [{"id": "a", "text": GOOD}, {"id": "b", "text": "SKILLS\nExcel, Tally, typing"}])
        self.assertEqual([r["id"] for r in res["ranking"]], ["a", "b"])
        self.assertEqual([r["rank"] for r in res["ranking"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
