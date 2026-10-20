import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from schemesetu import benefits, synth  # noqa: E402
from schemesetu.catalogue import Catalogue, ProfileError, fmt_inr  # noqa: E402
from schemesetu.engine import Engine  # noqa: E402

DATA = os.path.join(HERE, "data")
NOTE = "Rules are simplified for this prototype — verify on the official portal."


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = Catalogue(DATA)

    def test_size_and_categories(self):
        self.assertGreaterEqual(len(self.cat.schemes), 15)
        self.assertLessEqual(len(self.cat.schemes), 25)
        cats = set(s["category"] for s in self.cat.schemes)
        for c in ("agriculture", "insurance", "pension", "housing", "education", "health", "women"):
            self.assertIn(c, cats)
        self.assertTrue(any(s.get("level") == "tamil_nadu" for s in self.cat.schemes))

    def test_every_scheme_carries_verify_note(self):
        for s in self.cat.schemes:
            self.assertEqual(s["verify_note"]["en"], NOTE, s["id"])
            self.assertTrue(s["verify_note"]["ta"])

    def test_bilingual_fields(self):
        for s in self.cat.schemes:
            for k in ("name", "summary", "description", "apply"):
                self.assertTrue(s[k]["en"] and s[k]["ta"], "%s.%s" % (s["id"], k))
        for q in self.cat.questions:
            self.assertTrue(q["text"]["en"] and q["text"]["ta"], q["id"])

    def test_profile_normalisation(self):
        p = self.cat.normalise_profile({"rural": "yes", "land_ha": "1", "ration_card": "PHH",
                                        "annual_income": 120000.0, "has_lpg": None, "woman_head": "ஆம்"})
        self.assertEqual(p, {"rural": True, "land_ha": 1, "ration_card": "PHH", "annual_income": 120000, "woman_head": True})
        for bad in ({"nope": 1}, {"rural": "maybe"}, {"ration_card": "GOLD"}, {"land_ha": "x"}, {"land_ha": -2}):
            with self.assertRaises(ProfileError):
                self.cat.normalise_profile(bad)

    def test_gate_and_inference_closure(self):
        closed, inferred = self.cat.close({"gate_students": False, "woman_head": True})
        self.assertFalse(closed["post_matric_student"])
        self.assertFalse(closed["govt_school_child_8to12"])
        self.assertTrue(closed["adult_woman"])  # woman head => adult woman
        self.assertEqual(inferred["adult_woman"], "woman_head")
        # explicit answers always win over shortcuts
        closed, _ = self.cat.close({"gate_students": False, "post_matric_student": True})
        self.assertTrue(closed["post_matric_student"])
        # gate truth for a complete profile
        g = self.cat.q_by_id["gate_home"]
        self.assertTrue(self.cat.gate_value(g, {"has_toilet": True, "has_lpg": True}))
        self.assertFalse(self.cat.gate_value(g, {"has_toilet": True, "has_lpg": False}))

    def test_condition_text_bilingual(self):
        leaf = {"fact": "annual_income", "op": "<=", "value": 250000}
        txt = self.cat.condition_text(leaf)
        self.assertIn("₹2,50,000", txt["en"])
        self.assertIn("₹2,50,000", txt["ta"])
        self.assertEqual(fmt_inr(12000000), "1,20,00,000")


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(DATA)

    def demo(self, i):
        return synth.DEMO_HOUSEHOLDS[i]["profile"]

    def test_demo_farmer(self):
        ev = self.e.evaluate(self.demo(0))
        st = dict((r["id"], r["status"]) for r in ev["results"])
        self.assertEqual(st["pm_kisan"], "eligible")
        self.assertEqual(st["pmfby"], "eligible")
        self.assertEqual(st["pmay_g"], "not_eligible")
        self.assertEqual(ev["counts"]["possibly"], 0)
        # explanation names the failing condition
        r = [x for x in ev["results"] if x["id"] == "pmay_g"][0]
        self.assertIn("kutcha", r["reason"]["en"])

    def test_widow_pension_counted_once(self):
        ev = self.e.evaluate(self.demo(2))
        st = dict((r["id"], r["status"]) for r in ev["results"])
        self.assertEqual(st["ignwps"], "eligible")
        self.assertEqual(st["ignoaps"], "eligible")
        b = ev["benefits"]
        self.assertEqual(len(b["not_counted"]), 1)
        self.assertEqual(b["annual_total"], 3600 + 12000)  # widow pension + KMUT; old-age not double counted

    def test_empty_profile_all_possibly(self):
        ev = self.e.evaluate({})
        self.assertEqual(ev["counts"]["possibly"], len(self.e.cat.schemes))
        self.assertEqual(ev["benefits"]["annual_total"], 0)

    def test_benefit_tiers(self):
        s = self.e.cat.by_id["ignoaps"]
        self.assertEqual(benefits.scheme_amount(s, {"oldest_age": 69}, self.e.cat.params), 2400)
        self.assertEqual(benefits.scheme_amount(s, {"oldest_age": 85}, self.e.cat.params), 6000)

    def test_estimator_kinds(self):
        ev = self.e.evaluate(self.demo(1))  # landless labourer
        b = ev["benefits"]
        self.assertEqual(b["one_time_total"], 120000 + 12000 + 5000)  # PMAY-G + toilet + PMMVY
        self.assertEqual(b["max_health_cover"], 500000)
        self.assertTrue(any(i["id"] == "mgnrega" for i in b["varies"]))
        self.assertFalse(any(i["id"] == "pm_jay" for i in b["annual"]))  # cover is never cash

    def test_conditional_amount_separate(self):
        ev = self.e.evaluate(self.demo(0))
        self.assertEqual(ev["benefits"]["conditional_total"], 12000)  # NMMS only if selected
        self.assertEqual(ev["benefits"]["annual_total"], 6000 + 12000)  # PM-KISAN + KMUT


if __name__ == "__main__":
    unittest.main()
