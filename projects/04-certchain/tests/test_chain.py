import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from certchain import config, demo, merkle  # noqa: E402
from certchain.chain import block_hash, mine  # noqa: E402
from certchain.records import (ValidationError, clean_certificate_input, record_hash,  # noqa: E402
                               verification_code)
from certchain.service import CertChainService, Conflict, NotFound  # noqa: E402

KEYS = demo.build_keys()


def fresh_ledger():
    return demo.build_demo_chain(KEYS)


class TestDemoChain(unittest.TestCase):
    def test_demo_chain_validates(self):
        led = fresh_ledger()
        rep = led.validate()
        self.assertTrue(rep["valid"], rep["errors"])
        self.assertEqual(len(led.blocks), 6)
        self.assertEqual(len(led.cert_index()), 20)
        for b in led.blocks:
            self.assertTrue(b["hash"].startswith("0" * config.POW_DIFFICULTY))

    def test_demo_is_deterministic(self):
        a, b = fresh_ledger(), fresh_ledger()
        self.assertEqual(a.tip["hash"], b.tip["hash"])

    def test_every_certificate_verifies(self):
        led = fresh_ledger()
        rep = led.validate()
        for cid in led.cert_index():
            res = led.verify_bundle(led.certificate_bundle(cid), validation=rep)
            if cid == "KSRCE-26-00004":
                self.assertEqual(res["verdict"], "REVOKED")
            else:
                self.assertTrue(res["valid"], (cid, res["summary"]))


class TestTamperDetection(unittest.TestCase):
    def setUp(self):
        self.led = fresh_ledger()

    def _find(self, cid):
        bi, ri = self.led.cert_index()[cid]
        return bi, self.led.blocks[bi]["records"][ri]

    def test_edit_record_breaks_merkle_root(self):
        bi, rec = self._find(demo.TAMPER_TARGET)
        rec["cgpa"] = "9.91"
        rep = self.led.validate()
        self.assertFalse(rep["valid"])
        self.assertEqual(rep["broken_blocks"], [bi])
        failed = [c["name"] for c in rep["blocks"][bi]["checks"] if not c["ok"]]
        self.assertEqual(failed, ["merkle_root"])
        res = self.led.verify_bundle(self.led.certificate_bundle(demo.TAMPER_TARGET), validation=rep)
        self.assertEqual(res["verdict"], "INVALID")
        self.assertFalse(next(s for s in res["steps"] if s["key"] == "merkle_proof")["ok"])

    def test_rehash_and_remine_breaks_signature_and_next_link(self):
        bi, rec = self._find(demo.TAMPER_TARGET)
        rec["cgpa"] = "9.91"
        b = self.led.blocks[bi]
        b["header"]["merkle_root"] = merkle.merkle_root([record_hash(r) for r in b["records"]])
        nonce, hx, _, _ = mine(b["header"], b["header"]["difficulty"])
        b["header"]["nonce"], b["hash"] = nonce, hx
        rep = self.led.validate()
        self.assertEqual(rep["broken_blocks"], [bi, bi + 1])
        failed = [c["name"] for c in rep["blocks"][bi]["checks"] if not c["ok"]]
        self.assertEqual(failed, ["signature"])
        failed_next = [c["name"] for c in rep["blocks"][bi + 1]["checks"] if not c["ok"]]
        self.assertEqual(failed_next, ["prev_link"])

    def test_header_edit_without_rehash_breaks_hash(self):
        self.led.blocks[2]["header"]["timestamp"] = "2026-06-03T00:00:00Z"
        rep = self.led.validate()
        failed = [c["name"] for c in rep["blocks"][2]["checks"] if not c["ok"]]
        self.assertIn("block_hash", failed)
        self.assertIn("signature", failed)

    def test_weak_pow_rejected(self):
        b = self.led.blocks[3]
        b["header"]["difficulty"] = 1
        rep = self.led.validate()
        self.assertIn("pow", [c["name"] for c in rep["blocks"][3]["checks"] if not c["ok"]])

    def test_removed_block_breaks_link(self):
        del self.led.blocks[2]
        rep = self.led.validate()
        self.assertFalse(rep["valid"])
        self.assertIn(2, rep["broken_blocks"])

    def test_forged_bundle_with_edited_cgpa_fails(self):
        bundle = self.led.certificate_bundle("KSRCE-26-00001")
        forged = copy.deepcopy(bundle)
        forged["record"]["cgpa"] = "9.99"
        forged.pop("record_hash")
        res = self.led.verify_bundle(forged)
        self.assertEqual(res["verdict"], "INVALID")
        self.assertEqual([s["key"] for s in res["steps"] if not s["ok"]], ["merkle_proof"])

    def test_bundle_signed_by_unregistered_key_fails(self):
        from certchain.chain import build_block
        from certchain.ed25519 import KeyPair
        rogue = KeyPair(b"\x07" * 32)
        rec = dict(self.led.certificate_bundle("KSRCE-26-00001")["record"], cert_id="KSRCE-26-99999")
        blk, _ = build_block(6, self.led.tip["hash"], [rec], "ksrce", rogue, "2026-09-01T00:00:00Z")
        bundle = {"record": rec, "merkle_proof": [],
                  "block": {"header": blk["header"], "hash": blk["hash"], "signature": blk["signature"]}}
        res = self.led.verify_bundle(bundle)
        failed = [s["key"] for s in res["steps"] if not s["ok"]]
        self.assertIn("issuer_signature", failed)
        self.assertIn("anchored", failed)

    def test_wrong_printed_code(self):
        bundle = self.led.certificate_bundle("KSRCE-26-00001")
        good = self.led.verify_bundle(bundle, printed_code=bundle["verification_code"])
        self.assertTrue(good["valid"])
        bad = self.led.verify_bundle(bundle, printed_code="AAAA-AAAA")
        self.assertFalse(bad["valid"])

    def test_malformed_bundle(self):
        res = self.led.verify_bundle({"hello": 1})
        self.assertFalse(res["valid"])
        self.assertEqual(res["steps"][0]["key"], "format")


class TestRecords(unittest.TestCase):
    def test_clean_input(self):
        c = clean_certificate_input({"student_name": "  Lakshmi   R. ", "register_no": "ksr22cs141",
                                     "programme": "B.E. CSE", "cgpa": "8.9", "issue_date": "2026-10-20",
                                     "cert_type": "Degree Certificate"})
        self.assertEqual(c["student_name"], "Lakshmi R.")
        self.assertEqual(c["register_no"], "KSR22CS141")
        self.assertEqual(c["cgpa"], "8.90")

    def test_bad_inputs(self):
        base = {"student_name": "Ravi K.", "register_no": "KSR22CS1", "programme": "B.E. CSE",
                "cgpa": "8", "issue_date": "2026-10-20", "cert_type": "Degree Certificate"}
        for k, v in [("cgpa", "11"), ("cgpa", "abc"), ("cgpa", ""), ("issue_date", "20-10-2026"),
                     ("student_name", "<script>"), ("register_no", "1"), ("cert_type", "Fake")]:
            with self.subTest(k=k, v=v):
                with self.assertRaises(ValidationError):
                    clean_certificate_input(dict(base, **{k: v}))
        ok = clean_certificate_input(dict(base, cgpa="", cert_type="Internship Certificate"))
        self.assertEqual(ok["cgpa"], "N/A")

    def test_verification_code_format(self):
        code = verification_code("ab" * 32)
        self.assertRegex(code, r"^[A-Z2-7]{4}-[A-Z2-7]{4}$")


class TestServiceFlows(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="certchain-test-")
        self.svc = CertChainService(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_issue_and_verify(self):
        out = self.svc.issue("ksrce", {"student_name": "Lakshmi R.", "register_no": "KSR22CS141",
                                       "programme": "B.E. Computer Science and Engineering",
                                       "cgpa": "8.91", "issue_date": "2026-10-20",
                                       "cert_type": "Degree Certificate"})
        self.assertEqual(out["cert_id"], "KSRCE-26-00014")
        self.assertEqual(out["block_index"], 6)
        res = self.svc.verify(cert_id=out["cert_id"])
        self.assertTrue(res["valid"], res["summary"])
        # the downloadable bundle verifies on its own too
        res2 = self.svc.verify(bundle=json.loads(json.dumps(out["bundle"])))
        self.assertTrue(res2["valid"])

    def test_bulk_issue_and_errors(self):
        out = self.svc.bulk_issue("cvct", demo.SAMPLE_CSV)
        self.assertEqual(out["issued"], 5)
        self.assertTrue(self.svc.validate()["valid"])
        for cid in out["cert_ids"]:
            self.assertTrue(self.svc.verify(cert_id=cid)["valid"])
        with self.assertRaises(ValidationError):
            self.svc.bulk_issue("cvct", "student_name,register_no\nA,B\n")
        bad = demo.SAMPLE_CSV + "X,1,B.E.,12,2026-01-01,Degree Certificate\n"
        with self.assertRaises(ValidationError):
            self.svc.bulk_issue("cvct", bad)
        with self.assertRaises(NotFound):
            self.svc.bulk_issue("nobody", demo.SAMPLE_CSV)

    def test_revocation_flow(self):
        cid = "CVCT-26-00002"
        self.assertTrue(self.svc.verify(cert_id=cid)["valid"])
        with self.assertRaises(Conflict):           # not the issuer
            self.svc.revoke("ksrce", cid, "attempted cross-revocation")
        out = self.svc.revoke("cvct", cid, "Academic misconduct finding")
        self.assertEqual(out["block_index"], 6)
        res = self.svc.verify(cert_id=cid)
        self.assertEqual(res["verdict"], "REVOKED")
        self.assertTrue(self.svc.validate()["valid"])
        with self.assertRaises(Conflict):           # twice
            self.svc.revoke("cvct", cid, "again")

    def test_forged_revocation_signature_detected(self):
        from certchain.ed25519 import KeyPair
        from certchain.records import make_revocation
        led = self.svc.ledger()
        _, real = self.svc._keypair("cvct")
        rogue = KeyPair(b"\x09" * 32)
        # revocation body signed by a rogue key, but placed in a block that is
        # properly mined and signed by the real issuer
        rev = make_revocation("CVCT-26-00001", "cvct", "forged", "2026-09-01T00:00:00Z", rogue)
        led.append([rev], "cvct", real, "2026-09-01T00:00:00Z")
        rep = led.validate()
        self.assertEqual(rep["broken_blocks"], [6])
        failed = [c for c in rep["blocks"][6]["checks"] if not c["ok"]]
        self.assertEqual([c["name"] for c in failed], ["records"])
        self.assertIn("bad signature on revocation", failed[0]["detail"])

    def test_tamper_and_restore(self):
        t = self.svc.tamper("edit")
        self.assertEqual(t["new_cgpa"], "9.91")
        self.assertFalse(t["validation"]["valid"])
        self.assertEqual(t["verification"]["verdict"], "INVALID")
        self.assertTrue(self.svc.stats()["tampered"])
        with self.assertRaises(Conflict):           # refuses to extend a tampered chain
            self.svc.issue("ksrce", {"student_name": "Ravi K.", "register_no": "KSR22CS001",
                                     "programme": "B.E. CSE", "cgpa": "8", "issue_date": "2026-10-20",
                                     "cert_type": "Degree Certificate"})
        t2 = self.svc.tamper("rehash")
        self.assertEqual(t2["validation"]["broken_blocks"], [1, 2])
        r = self.svc.restore()
        self.assertTrue(r["restored"])
        self.assertTrue(r["validation"]["valid"])
        self.assertTrue(self.svc.verify(cert_id=demo.TAMPER_TARGET)["valid"])
        self.assertFalse(self.svc.restore()["restored"])

    def test_unknown_certificate(self):
        res = self.svc.verify(cert_id="KSRCE-26-77777")
        self.assertEqual(res["verdict"], "NOT FOUND")
        with self.assertRaises(NotFound):
            self.svc.certificate("NOPE-1", "http://x")

    def test_certificate_page_data(self):
        c = self.svc.certificate("KSRCE-26-00001", "http://127.0.0.1:8004")
        self.assertIn("#verify=KSRCE-26-00001", c["verify_url"])
        self.assertTrue(c["qr_svg"].startswith("<svg"))
        self.assertEqual(c["status"]["verdict"], "VALID")


if __name__ == "__main__":
    unittest.main()
