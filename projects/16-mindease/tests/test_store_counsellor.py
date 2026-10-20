import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mindease import config, counsellor, demo_data  # noqa: E402
from mindease.store import Store  # noqa: E402

TODAY = dt.date(2026, 10, 23)


class TestDemoData(unittest.TestCase):
    def test_deterministic(self):
        a = demo_data.build_state(end_date=demo_data.FIXED_END_DATE)
        b = demo_data.build_state(end_date=demo_data.FIXED_END_DATE)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_cohort_shape_and_exam_spike(self):
        co = demo_data.cohort(TODAY)
        self.assertEqual(len(co["students"]), config.COHORT_SIZE)
        self.assertEqual(len({s["pid"] for s in co["students"]}), config.COHORT_SIZE)
        self.assertEqual([w["week"] for w in co["weeks"]], list(range(1, 9)))
        rows = counsellor.weekly_bands(co["screenings"], co["weeks"], "phq9")
        regular = [r["pct_moderate_plus"] for r in rows if not r["exam"]]
        exam = [r["pct_moderate_plus"] for r in rows if r["exam"]]
        self.assertGreater(min(exam), max(regular))
        for s in co["screenings"]:
            self.assertNotIn("name", s)
            self.assertTrue(s["pid"].startswith("S-"))
        self.assertTrue(any(a["status"] == "new" for a in co["alerts"]))
        self.assertTrue(all(a["item9"] > 0 for a in co["alerts"]))

    def test_ananya_three_weeks(self):
        st = demo_data.build_state(end_date=demo_data.FIXED_END_DATE)
        j = st["student"]["journal"]
        self.assertEqual(len(j), 21)
        self.assertEqual(j[-1]["date"], "2026-10-22")
        self.assertEqual(st["student"]["name"], "Ananya")


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "state.json")
        self.store = Store(self.path, today_fn=lambda: TODAY,
                           now_fn=lambda: "2026-10-23T10:00")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestStore(StoreCase):
    def test_first_run_creates_state_file(self):
        self.assertTrue(os.path.isfile(self.path))
        st = self.store.student()
        self.assertEqual(st["journal"][0]["date"], "2026-10-22")  # ends yesterday
        # reload from disk
        again = Store(self.path, today_fn=lambda: TODAY)
        self.assertEqual(len(again.student()["journal"]), 21)

    def test_corrupt_state_is_regenerated(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        s = Store(self.path, today_fn=lambda: TODAY)
        self.assertEqual(len(s.student()["journal"]), 21)

    def test_add_journal_and_validation(self):
        r = self.store.add_journal({"mood": 4, "sleep": 7, "text": "Had a semma fun day"})
        self.assertEqual(r["entry"]["label"], "positive")
        self.assertIsNone(r["support"])
        for bad in ({"mood": 0}, {"mood": 3, "sleep": 30}, {"mood": "4"},
                    {"mood": 3, "text": "x" * 1001}, {"mood": 3, "date": "2026-12-01"},
                    {"mood": 3, "date": "yesterday"}, {"mood": True}):
            with self.assertRaises(ValueError):
                self.store.add_journal(bad)

    def test_concerning_journal_shows_support_but_shares_nothing(self):
        before = json.dumps(self.store.state["cohort"], sort_keys=True)
        r = self.store.add_journal({"mood": 2, "text": "I feel like nothing will ever get better"})
        self.assertTrue(r["safety"]["flagged"])
        self.assertEqual(r["support"]["reason"], "journal")
        self.assertTrue(r["entry"]["flagged"])
        self.assertEqual(before, json.dumps(self.store.state["cohort"], sort_keys=True))

    def test_delete_journal(self):
        eid = self.store.student()["journal"][0]["id"]
        self.assertTrue(self.store.delete_journal(eid))
        self.assertFalse(self.store.delete_journal(eid))

    def test_shared_screening_goes_to_cohort_and_item9_alerts(self):
        n_alerts = len(self.store.state["cohort"]["alerts"])
        r = self.store.add_screening({"instrument": "phq9", "answers": [0] * 8 + [1]})
        self.assertTrue(r["support"]["show"])
        self.assertTrue(r["alert_created"])
        self.assertIn("headline", r["support"])
        alerts = self.store.state["cohort"]["alerts"]
        self.assertEqual(len(alerts), n_alerts + 1)
        mine = alerts[-1]
        self.assertEqual((mine["pid"], mine["status"], mine["contact_ok"]),
                         (self.store.state["student"]["pid"], "new", False))
        # a second positive check-in updates the same open alert
        self.store.add_screening({"instrument": "phq9", "answers": [1] * 8 + [2]})
        self.assertEqual(len(self.store.state["cohort"]["alerts"]), n_alerts + 1)
        # asking for contact links the alert
        c = self.store.request_contact({"reason": "item9", "preferred": "phone call"})
        self.assertEqual(c["contact"]["priority"], "today")
        self.assertTrue(self.store.state["cohort"]["alerts"][-1]["contact_ok"])
        self.assertIn("14416", c["message"])

    def test_private_screening_not_shared(self):
        n = len(self.store.state["cohort"]["screenings"])
        n_alerts = len(self.store.state["cohort"]["alerts"])
        r = self.store.add_screening({"instrument": "phq9", "answers": [0] * 8 + [3],
                                      "share": False})
        self.assertTrue(r["support"]["show"])     # support always shown ...
        self.assertFalse(r["alert_created"])      # ... but no alert without consent
        self.assertEqual(len(self.store.state["cohort"]["screenings"]), n)
        self.assertEqual(len(self.store.state["cohort"]["alerts"]), n_alerts)

    def test_consent_and_erase(self):
        self.assertEqual(self.store.set_consent({"share_aggregate": False})["share_aggregate"],
                         False)
        with self.assertRaises(ValueError):
            self.store.set_consent({"contact": "yes"})
        self.store.set_consent({"share_aggregate": True})
        self.store.add_screening({"instrument": "gad7", "answers": [1] * 7})
        pid = self.store.state["student"]["pid"]
        self.store.erase_student()
        st = self.store.state
        self.assertEqual(st["student"]["journal"], [])
        self.assertFalse(any(s["pid"] == pid for s in st["cohort"]["screenings"]))
        self.assertFalse(any(s["pid"] == pid for s in st["cohort"]["students"]))

    def test_request_contact_validation(self):
        with self.assertRaises(ValueError):
            self.store.request_contact({"reason": "boredom"})
        with self.assertRaises(ValueError):
            self.store.request_contact({"preferred": "whatsapp"})


class TestCounsellor(StoreCase):
    def test_login(self):
        with self.assertRaises(PermissionError):
            self.store.login({"pin": "0000"})
        with self.assertRaises(PermissionError):
            self.store.login({})
        tok = self.store.login({"pin": config.DEMO_COUNSELLOR_PIN})["token"]
        self.assertEqual(self.store.session(tok)["role"], "counsellor")
        self.store.logout(tok)
        self.assertIsNone(self.store.session(tok))

    def test_dashboard_is_aggregate_only(self):
        d = self.store.dashboard()
        self.assertEqual(len(d["phq9"]), 8)
        self.assertEqual(set(d["phq9"][0]["counts"]),
                         {"minimal", "mild", "moderate", "moderately_severe", "severe"})
        blob = json.dumps(d)
        self.assertNotIn("Ananya", blob)
        self.assertNotIn("journal", blob.lower().replace("journal text", ""))
        for row in d["by_year"]["rows"]:
            if not row["suppressed"]:
                self.assertTrue(row["moderate_plus"] == 0 or
                                row["moderate_plus"] >= config.SMALL_CELL_MIN)
        self.assertTrue(d["narrative"])
        self.assertEqual(len(d["privacy"]), 6)

    def test_small_cell_suppression(self):
        students = [{"pid": "S-1", "year": 1}, {"pid": "S-2", "year": 1},
                    {"pid": "S-3", "year": 2}, {"pid": "S-4", "year": 2},
                    {"pid": "S-5", "year": 2}, {"pid": "S-6", "year": 2}]
        sc = [{"pid": p, "week": 1, "instrument": "phq9", "total": t}
              for p, t in (("S-1", 12), ("S-2", 3), ("S-3", 11), ("S-4", 2), ("S-5", 1),
                           ("S-6", 0))]
        rows = {r["year"]: r for r in counsellor.by_year(sc, students, 1)}
        self.assertEqual(rows[1]["moderate_plus"], "suppressed")   # only 2 students
        self.assertEqual(rows[1]["n"], "<3")
        self.assertEqual(rows[2]["n"], 4)
        self.assertEqual(rows[2]["moderate_plus"], "<3")            # 1 of 4 hidden
        self.assertEqual(rows[3]["n"], 0)

    def test_alert_workflow(self):
        new = next(a for a in self.store.dashboard()["alerts"] if a["status"] == "new")
        a = self.store.acknowledge(new["id"], "Ms K", "Calling today")
        self.assertEqual(a["status"], "acknowledged")
        self.assertEqual(a["history"][-1]["note"], "Calling today")
        with self.assertRaises(ValueError):
            self.store.acknowledge(new["id"], "Ms K", "")
        a = self.store.follow_up(new["id"], "Ms K", "Met in person")
        self.assertEqual(a["status"], "followed_up")
        with self.assertRaises(ValueError):
            self.store.follow_up(new["id"], "Ms K", "")
        with self.assertRaises(KeyError):
            self.store.acknowledge("A999", "x", "")
        # follow-up straight from new also records an acknowledgement
        other = next(a for a in self.store.dashboard()["alerts"] if a["status"] == "new")
        a = self.store.follow_up(other["id"], "Ms K", "")
        self.assertEqual([h["action"] for h in a["history"]], ["acknowledged", "followed_up"])

    def test_contacts(self):
        pending = next(c for c in self.store.dashboard()["contacts"] if c["status"] == "pending")
        c = self.store.mark_contacted(pending["id"], "Ms K")
        self.assertEqual(c["status"], "contacted")
        with self.assertRaises(ValueError):
            self.store.mark_contacted(pending["id"], "Ms K")
        with self.assertRaises(KeyError):
            self.store.mark_contacted("C999", "Ms K")

    def test_dashboard_does_not_mutate_state(self):
        before = json.dumps(self.store.state, sort_keys=True)
        self.store.dashboard()
        self.assertEqual(before, json.dumps(self.store.state, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
