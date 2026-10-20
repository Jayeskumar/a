import copy
import json
import os
import random
import shutil
import tempfile
import unittest

from helpers import get_token, make_election
from campusvote import audit, board
from campusvote.util import Conflict


def cast_some(svc, codes, k, choose=None):
    rng = random.Random(21)
    out = []
    for i, (reg, code) in enumerate(sorted(codes.items())[:k]):
        dev = get_token(svc, reg, code, rng)
        ch = choose(i) if choose else {"president": "c%d" % (1 + i % 2), "secretary": "c%d" % (1 + i % 3)}
        svc.cast(dev.build_ballot(ch))
        out.append((dev, ch))
    svc.flush_pool(force=True)
    return out


def failed(rep):
    return {s["id"] for s in rep["steps"] if not s["ok"]}


class TestChain(unittest.TestCase):
    def setUp(self):
        self.svc, codes = make_election(n=10)
        cast_some(self.svc, codes, 8)
        self.entries = copy.deepcopy(self.svc.entries)

    def test_clean_board_verifies(self):
        self.assertTrue(board.verify_chain(self.entries)["ok"])
        rep = audit.audit(self.entries)
        self.assertEqual(rep["verdict"], "VERIFIED", failed(rep))
        self.assertEqual(rep["summary"]["ballots"], 8)

    def test_edit_breaks_chain_at_that_entry(self):
        k = next(e["seq"] for e in self.entries if e["type"] == "ballot")
        self.entries[k]["data"]["commitment"] = "0" * 64
        chain = board.verify_chain(self.entries)
        self.assertFalse(chain["ok"])
        self.assertEqual(chain["first_break"], k)
        self.assertEqual(chain["breaks"][0]["kind"], "content")
        self.assertIn("chain", failed(audit.audit(self.entries)))

    def test_rehash_is_caught_by_signed_checkpoints(self):
        k = [e["seq"] for e in self.entries if e["type"] == "ballot"][2]
        self.entries[k]["data"]["commitment"] = "0" * 64
        prev = self.entries[k - 1]["hash"]
        for e in self.entries[k:]:
            e["prev"] = prev
            if e["type"] == "checkpoint" and e["data"]["upto"] >= k:
                e["data"]["head"] = self.entries[e["data"]["upto"]]["hash"]
            e["hash"] = board.entry_hash(e)
            prev = e["hash"]
        self.assertTrue(board.verify_chain(self.entries)["ok"])      # chain alone is fooled...
        self.assertIn("checkpoints", failed(audit.audit(self.entries)))  # ...signatures are not

    def test_delete_and_insert_detected(self):
        k = [e["seq"] for e in self.entries if e["type"] == "ballot"][1]
        gone = copy.deepcopy(self.entries)
        del gone[k]
        chain = board.verify_chain(gone)
        self.assertEqual(chain["first_break"], k)
        self.assertIn(chain["breaks"][0]["kind"], ("sequence", "link"))
        extra = copy.deepcopy(self.entries)
        extra.insert(k, copy.deepcopy(extra[k]))
        self.assertEqual(board.verify_chain(extra)["first_break"], k + 1)

    def test_duplicate_and_forged_ballots_fail_audit(self):
        bal = next(e for e in self.entries if e["type"] == "ballot")
        dup = copy.deepcopy(self.entries)
        dup.append(board.make_entry(dup, "ballot", copy.deepcopy(bal["data"]), 0))
        self.assertIn("duplicates", failed(audit.audit(dup)))
        forged = copy.deepcopy(self.entries)
        d = copy.deepcopy(bal["data"])
        d["token"] = "ab" * 32
        forged.append(board.make_entry(forged, "ballot", d, 0))
        self.assertIn("signatures", failed(audit.audit(forged)))

    def test_checkpoint_signature_verifies(self):
        cps = [e for e in self.entries if e["type"] == "checkpoint"]
        self.assertGreater(len(cps), 2)
        d = cps[-1]["data"]
        self.assertEqual(self.entries[d["upto"]]["hash"], d["head"])


class TestStoredBoardTamper(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cv-test-")
        self.svc, self.codes = make_election(n=10, data_dir=self.dir)
        self.cast = cast_some(self.svc, self.codes, 6)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_three_tamper_modes_detected_then_restored(self):
        for mode, expect in (("edit", "chain"), ("rehash", "checkpoints"), ("delete", "chain")):
            res = self.svc.tamper(mode)
            self.assertEqual(res["report"]["verdict"], "FAILED", mode)
            self.assertIn(expect, failed(res["report"]), mode)
            self.assertIsNotNone(self.svc.halted)
            self.assertEqual(self.svc.verify()["verdict"], "FAILED")
            with self.assertRaises(Conflict):     # system refuses to extend a broken board
                self.svc.cast({"token": "x"})
            self.assertTrue(self.svc.restore()["restored"])
            self.assertEqual(self.svc.verify()["verdict"], "VERIFIED", mode)
            self.assertIsNone(self.svc.halted)

    def test_vote_flip_after_tally_detected(self):
        self.svc.close_and_tally()
        res = self.svc.tamper("edit")
        f = failed(res["report"])
        self.assertTrue({"chain", "openings", "recount"} <= f, f)
        self.svc.restore()
        res = self.svc.tamper("rehash")
        f = failed(res["report"])
        self.assertTrue({"checkpoints", "openings", "recount"} <= f, f)
        self.assertNotIn("chain", f)
        self.svc.restore()

    def test_external_edit_with_text_editor_halts_appends(self):
        path = os.path.join(self.dir, "board.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        doc["entries"][3]["time"] += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        rep = self.svc.verify()
        self.assertEqual(rep["verdict"], "FAILED")
        self.assertEqual(rep["first_break"], 3)
        self.assertIsNotNone(self.svc.halted)
        with self.assertRaises(Conflict):  # any further mutation is refused
            self.svc.simulate(1)

    def test_reload_from_disk_round_trip(self):
        from campusvote.election import ElectionService
        from helpers import small_keys
        again = ElectionService(self.dir, keys=small_keys(), otp_iters=1)
        self.assertEqual(again.entries[-1]["hash"], self.svc.entries[-1]["hash"])
        self.assertEqual(again.verify()["verdict"], "VERIFIED")
        self.assertIsNone(again.halted)


if __name__ == "__main__":
    unittest.main()
