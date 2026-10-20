import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from schemesetu import checklist, synth  # noqa: E402
from schemesetu.engine import Engine  # noqa: E402
from schemesetu.store import NotFound, Store, StoreError  # noqa: E402


class ChecklistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(os.path.join(HERE, "data"))

    def test_union_is_deduplicated(self):
        ids = ["pm_kisan", "pmfby", "kcc"]
        c = self.e.checklist(ids)
        doc_ids = [d["id"] for d in c["items"]]
        self.assertEqual(len(doc_ids), len(set(doc_ids)))
        expected = set()
        for sid in ids:
            expected |= set(self.e.cat.by_id[sid]["documents"])
        self.assertEqual(set(doc_ids), expected)
        self.assertEqual(c["mentions"], sum(len(self.e.cat.by_id[s]["documents"]) for s in ids))
        self.assertEqual(c["duplicates_removed"], c["mentions"] - c["count"])
        aadhaar = [d for d in c["items"] if d["id"] == "aadhaar"][0]
        self.assertEqual(aadhaar["schemes"], ids)
        self.assertEqual(c["items"][0]["id"], "aadhaar")  # most-shared document first

    def test_alias_spellings_merge(self):
        docs = self.e.cat.documents
        for name in ("aadhaar", "Aadhaar card", "AADHAR", "aadhar card", " Aadhaar  Card. "):
            self.assertEqual(checklist.canonical_doc(name, docs), "aadhaar", name)
        self.assertEqual(checklist.canonical_doc("Patta", docs), "land_records")
        c = self.e.checklist(["pm_kisan"], extra={"pm_kisan": ["Aadhaar Card", "patta", "Village map"]})
        ids = [d["id"] for d in c["items"]]
        self.assertEqual(ids.count("aadhaar"), 1)
        self.assertEqual(ids.count("land_records"), 1)
        self.assertIn("village_map", ids)  # unknown document kept as its own line

    def test_unknown_scheme_reported(self):
        c = self.e.checklist(["pm_kisan", "nope"])
        self.assertEqual(c["unknown_schemes"], ["nope"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "state.json")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_created_on_first_run_and_persists(self):
        s = Store(self.path)
        self.assertTrue(os.path.exists(self.path))
        h = s.create("Murugan", "Pudhur", {"rural": True})
        s.set_application(h["id"], "pm_kisan", "applied")
        s.set_application(h["id"], "pm_kisan", "received")
        s2 = Store(self.path)
        h2 = s2.get(h["id"])
        self.assertEqual(h2["applications"]["pm_kisan"]["status"], "received")
        with open(self.path, encoding="utf-8") as f:
            self.assertIn(h["id"], json.load(f)["households"])
        s2.set_application(h["id"], "pm_kisan", "not_applied")
        self.assertNotIn("pm_kisan", s2.get(h["id"])["applications"])

    def test_validation(self):
        s = Store(self.path)
        with self.assertRaises(StoreError):
            s.create("", "x", {})
        with self.assertRaises(StoreError):
            s.create("a" * 200, "x", {})
        h = s.create("A", "", {})
        self.assertEqual(h["village"], "Unassigned")
        with self.assertRaises(StoreError):
            s.set_application(h["id"], "pm_kisan", "granted")
        with self.assertRaises(NotFound):
            s.get("missing")

    def test_corrupt_file_recovers(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        s = Store(self.path)
        self.assertEqual(s.list(), [])


class VillageTests(unittest.TestCase):
    def test_dashboard_counts_unclaimed(self):
        e = Engine(os.path.join(HERE, "data"))
        prof = synth.DEMO_HOUSEHOLDS[1]["profile"]
        hs = [{"id": "a", "name": "A", "village": "V", "profile": prof, "applications": {}},
              {"id": "b", "name": "B", "village": "V", "profile": prof,
               "applications": {"mgnrega": {"status": "received"}, "pmay_g": {"status": "applied"}}}]
        d = e.village_dashboard(hs, "V")
        rows = dict((r["id"], r) for r in d["schemes"])
        self.assertEqual(rows["mgnrega"]["eligible"], 2)
        self.assertEqual(rows["mgnrega"]["unclaimed"], 1)
        self.assertEqual(rows["mgnrega"]["received"], 1)
        self.assertEqual(rows["pmay_g"]["unclaimed"], 1)
        self.assertEqual(rows["pmay_g"]["unclaimed_one_time"], 120000)
        n_elig = sum(1 for v in e.statuses(prof).values() if v == "eligible")
        self.assertEqual(d["totals"]["eligible_pairs"], 2 * n_elig)
        self.assertEqual(d["totals"]["unclaimed_pairs"], 2 * n_elig - 2)
        self.assertEqual(d["households"][0]["id"], "a")  # most unclaimed first

    def test_demo_village_is_deterministic(self):
        e = Engine(os.path.join(HERE, "data"))
        a, b = e.demo_village_households(), e.demo_village_households()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertTrue(all(h["profile"]["rural"] for h in a))


if __name__ == "__main__":
    unittest.main()
