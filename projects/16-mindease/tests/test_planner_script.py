import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import config, planner, resources, talk_script  # noqa: E402

TODAY = dt.date(2026, 10, 23)


def body(**kw):
    b = {"exams": [{"subject": "Maths", "date": "2026-10-28", "confidence": 1},
                   {"subject": "Physics", "date": "2026-10-30", "confidence": 5}],
         "hours_per_day": 3, "start_time": "17:30"}
    b.update(kw)
    return b


class TestPlanner(unittest.TestCase):
    def test_no_subject_after_its_exam(self):
        p = planner.plan(body(), today=TODAY)
        for d in p["days"]:
            for b in d["blocks"]:
                if b["subject"] == "Maths":
                    self.assertLess(d["date"], "2026-10-28")

    def test_less_prepared_gets_more_while_both_open(self):
        p = planner.plan(body(), today=TODAY)
        maths = physics = 0
        for d in p["days"]:
            if d["date"] < "2026-10-27":
                for b in d["blocks"]:
                    maths += b["subject"] == "Maths"
                    physics += b["subject"] == "Physics"
        self.assertGreater(maths, physics)

    def test_pomodoro_structure_and_sleep_cutoff(self):
        p = planner.plan(body(hours_per_day=8, start_time="18:00"), today=TODAY)
        self.assertTrue(p["warnings"])  # cut by the 22:30 bedtime
        for d in p["days"]:
            for b in d["blocks"]:
                self.assertLessEqual(b["end"], config.LATEST_STUDY_END)
            focus = [b for b in d["blocks"] if b["type"] == "focus"]
            for b in focus:
                h1, m1 = map(int, b["start"].split(":"))
                h2, m2 = map(int, b["end"].split(":"))
                self.assertEqual((h2 * 60 + m2) - (h1 * 60 + m1), 25)
            types = [b["type"] for b in d["blocks"]]
            if len(focus) > 4:
                self.assertEqual(types[7], "long_break")

    def test_day_before_exam_is_revision_and_exam_day_lighter(self):
        p = planner.plan(body(), today=TODAY)
        eve = next(d for d in p["days"] if d["date"] == "2026-10-27")
        first = [b for b in eve["blocks"] if b["type"] == "focus"][0]
        self.assertEqual((first["subject"], first["why"]), ("Maths", "revision: exam tomorrow"))
        normal = next(d for d in p["days"] if d["date"] == "2026-10-24")
        exam_day = next(d for d in p["days"] if d["date"] == "2026-10-28")
        self.assertLess(exam_day["focus_min"], normal["focus_min"])
        self.assertEqual(exam_day["exam_today"], ["Maths"])

    def test_hours_capped(self):
        p = planner.plan(body(hours_per_day=12, start_time="08:00"), today=TODAY)
        self.assertTrue(any("capped" in w for w in p["warnings"]))
        self.assertLessEqual(max(d["focus_min"] for d in p["days"]),
                             config.MAX_STUDY_HOURS_PER_DAY * 60)

    def test_validation(self):
        bad = [
            {"exams": []},
            {"exams": [{"subject": "", "date": "2026-10-28"}]},
            {"exams": [{"subject": "X", "date": "28/10/2026"}]},
            {"exams": [{"subject": "X", "date": "2026-10-28", "confidence": 9}]},
            {"exams": [{"subject": "X", "date": "2026-10-20"}]},
            body(hours_per_day=0),
            body(start_time="25:00"),
            body(start_time="22:20"),
            {"exams": [{"subject": "X", "date": "2027-03-01"}]},
        ]
        for b in bad:
            with self.assertRaises(ValueError, msg=str(b)):
                planner.plan(b, today=TODAY)

    def test_deterministic(self):
        self.assertEqual(planner.plan(body(), today=TODAY), planner.plan(body(), today=TODAY))


class TestTalkScript(unittest.TestCase):
    def test_script_contains_choices(self):
        r = talk_script.generate({"audience": "counsellor", "feelings": ["stressed", "lonely"],
                                  "duration": "month", "causes": ["exams"],
                                  "impacts": ["sleep"], "needs": ["listen"],
                                  "note": "I miss home"})
        text = r["full_text"]
        for piece in ("stressed and lonely", "about a month", "exams and marks", "sleep",
                      "just listen", "I miss home."):
            self.assertIn(piece, text)
        self.assertFalse(r["support"]["show"])
        self.assertIn("book a time", r["short_message"])

    def test_harm_thoughts_add_safe_sentence_and_support(self):
        r = talk_script.generate({"audience": "friend", "feelings": ["thoughts_harm"]})
        self.assertTrue(r["support"]["show"])
        self.assertIn("thoughts of hurting myself", r["full_text"])
        self.assertIn("counsellor or doctor", r["full_text"])

    def test_parent_default_greeting_and_name(self):
        r = talk_script.generate({"audience": "parent", "feelings": ["low"]})
        self.assertTrue(r["opening"].startswith("Amma / Appa"))
        r = talk_script.generate({"audience": "friend", "feelings": ["low"], "name": "Divya"})
        self.assertTrue(r["opening"].startswith("Hey Divya"))

    def test_validation(self):
        for b in ({"audience": "boss", "feelings": ["low"]}, {"feelings": []},
                  {"feelings": ["angry"]}, {"feelings": ["low"], "duration": "year"},
                  {"feelings": ["low"], "note": "x" * 301}):
            with self.assertRaises(ValueError):
                talk_script.generate(b)


class TestResources(unittest.TestCase):
    def test_only_known_helplines(self):
        nums = [n for h in resources.all_resources()["helplines"] for n in h["numbers"]]
        self.assertEqual(sorted(nums), sorted(["14416", "1-800-891-4416", "112"]))

    def test_support_screen(self):
        s = resources.support_screen("item9", "urgent")
        self.assertIn("112", s["emergency"])
        self.assertEqual(s["actions"][1]["label"], "Talk to a counsellor now")
        self.assertTrue(resources.support_screen("someone_else")["peer"])


if __name__ == "__main__":
    unittest.main()
