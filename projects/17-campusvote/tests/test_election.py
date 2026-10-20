import collections
import random
import unittest

from helpers import Clock, get_token, make_election, small_keys, voter
from campusvote import attacks, audit, config, demo, seal
from campusvote.election import ElectionService
from campusvote.util import Conflict, Forbidden, NotFound, ValidationError, canonical, sha256_hex


class TestVotingFlow(unittest.TestCase):
    def test_end_to_end_tally_is_correct(self):
        svc, codes = make_election(n=30)
        rng = random.Random(31)
        expected = {"president": collections.Counter(), "secretary": collections.Counter()}
        receipts = []
        for reg, code in sorted(codes.items())[:25]:
            dev = get_token(svc, reg, code, rng)
            ch = {"president": rng.choice(["c1", "c2", "NOTA"]), "secretary": rng.choice(["c1", "c2", "c3", "NOTA"])}
            for p, c in ch.items():
                expected[p][c] += 1
            receipts.append((svc.cast(dev.build_ballot(ch))["token_hash"], ch))
        res = svc.close_and_tally()
        self.assertEqual(res["report"]["verdict"], "VERIFIED", [s for s in res["report"]["steps"] if not s["ok"]])
        for post, cnt in expected.items():
            for cand, n in res["tally"]["counts"][post].items():
                self.assertEqual(n, cnt.get(cand, 0), (post, cand))
        self.assertEqual(res["tally"]["counted"], 25)
        # individual verifiability: every receipt is found, opened and matches the voter's choice
        for th, ch in receipts:
            r = svc.receipt(th[:16])
            self.assertEqual(r["status"], "counted")
            self.assertEqual(r["opening"]["choices"], ch)
        # universal verifiability: a fresh auditor with only the board gets the same numbers
        rep = audit.audit(svc.entries)
        self.assertEqual(rep["tally"]["counts"], res["tally"]["counts"])

    def test_results_sealed_until_tally(self):
        svc, codes = make_election(n=4)
        with self.assertRaises(Conflict):
            svc.results()

    def test_phase_guards(self):
        svc, codes = make_election(n=4, phase="registration")
        reg, code = sorted(codes.items())[0]
        dev = get_token(svc, reg, code)               # tokens may be issued during registration
        with self.assertRaises(Conflict):             # ...but not cast until voting opens
            svc.cast(dev.build_ballot({"president": "c1", "secretary": "c1"}))
        svc.open_voting()
        svc.cast(dev.build_ballot({"president": "c1", "secretary": "c1"}))
        svc.close_and_tally()
        with self.assertRaises(Conflict):
            svc.login(*sorted(codes.items())[1])

    def test_window_enforced(self):
        clock = Clock()
        svc, codes = make_election(n=3, clock=clock)
        dev = get_token(svc, *sorted(codes.items())[0])
        clock.t += 7200  # past the closing time
        with self.assertRaises(Conflict):
            svc.cast(dev.build_ballot({"president": "c1", "secretary": "c1"}))


class TestDoubleVoting(unittest.TestCase):
    def setUp(self):
        self.svc, self.codes = make_election(n=6)
        self.reg, self.code = sorted(self.codes.items())[0]

    def test_second_token_refused_but_retry_is_idempotent(self):
        dev = voter(self.svc, random.Random(1))
        blinded = "%x" % dev.prepare_token()
        s1 = self.svc.issue(self.svc.login(self.reg, self.code)["session"], blinded)
        s2 = self.svc.issue(self.svc.login(self.reg, self.code)["session"], blinded)  # network retry
        self.assertEqual(s1["blind_sig"], s2["blind_sig"])
        self.assertTrue(s2["resent"])
        other = voter(self.svc, random.Random(2))
        with self.assertRaises(Conflict):
            self.svc.issue(self.svc.login(self.reg, self.code)["session"], "%x" % other.prepare_token())
        self.assertEqual(len([e for e in self.svc.entries if e["type"] == "issuance"]), 1)

    def test_same_token_twice_rejected_in_pool_and_on_board(self):
        dev = get_token(self.svc, self.reg, self.code)
        b1 = dev.build_ballot({"president": "c1", "secretary": "c2"})
        self.assertEqual(self.svc.cast(b1)["status"], "queued")
        b2 = dev.build_ballot({"president": "c2", "secretary": "c2"})
        with self.assertRaises(Conflict):           # still in the mix pool
            self.svc.cast(b2)
        self.svc.flush_pool(force=True)
        with self.assertRaises(Conflict):           # now on the board: replay
            self.svc.cast(b1)
        self.assertEqual(len(self.svc.ballot_entries()), 1)

    def test_forged_and_malformed_ballots_rejected(self):
        dev = get_token(self.svc, self.reg, self.code)
        good = dev.build_ballot({"president": "c1", "secretary": "c1"})
        bad = dict(good, token="ab" * 32)
        with self.assertRaises(ValidationError):
            self.svc.cast(bad)
        for broken in (dict(good, sig="xyz"), dict(good, commitment="12"), dict(good, sealed={}), "nope"):
            with self.assertRaises(ValidationError):
                self.svc.cast(broken)
        self.assertEqual(self.svc.state["pool"], [])

    def test_session_is_single_use(self):
        sess = self.svc.login(self.reg, self.code)["session"]
        self.svc.issue(sess, "%x" % voter(self.svc).prepare_token())
        with self.assertRaises(Forbidden):
            self.svc.issue(sess, "%x" % voter(self.svc).prepare_token())


class TestAuthentication(unittest.TestCase):
    def test_lockout_after_five_wrong_codes(self):
        svc, codes = make_election(n=3)
        reg, code = sorted(codes.items())[0]
        wrong = "%06d" % ((int(code) + 1) % 10 ** 6)
        for _ in range(config.OTP_MAX_ATTEMPTS):
            with self.assertRaises(Forbidden):
                svc.login(reg, wrong)
        with self.assertRaises(Forbidden) as cm:
            svc.login(reg, code)                       # even the right code is refused now
        self.assertIn("locked", str(cm.exception))
        svc.unlock(reg)
        self.assertIn("session", svc.login(reg, code))

    def test_unknown_student_gets_generic_error(self):
        svc, _ = make_election(n=2)
        with self.assertRaises(Forbidden) as cm:
            svc.login("99XYZ999", "123456")
        self.assertIn("unknown register number or wrong code", str(cm.exception))

    def test_codes_stored_only_as_hashes(self):
        svc, codes = make_election(n=5)
        blob = repr(svc.state["roster"])
        for c in codes.values():
            self.assertNotIn("'%s'" % c, blob)

    def test_admin_key(self):
        svc, _ = make_election(n=2)
        svc.check_admin(config.ADMIN_KEY)
        for bad in (None, "", "guess"):
            with self.assertRaises(Forbidden):
                svc.check_admin(bad)


class TestMixAndSpoiling(unittest.TestCase):
    def test_batches_post_together_with_one_timestamp(self):
        clock = Clock()
        svc, codes = make_election(n=12, clock=clock)
        for i, (reg, code) in enumerate(sorted(codes.items())[:config.MIX_BATCH * 2]):
            clock.t += 1
            svc.cast(get_token(svc, reg, code).build_ballot({"president": "c1", "secretary": "c1"}))
            on_board = len(svc.ballot_entries())
            self.assertEqual(on_board, ((i + 1) // config.MIX_BATCH) * config.MIX_BATCH)
        times = collections.Counter(e["time"] for e in svc.ballot_entries())
        self.assertEqual(sorted(times.values()), [config.MIX_BATCH, config.MIX_BATCH])

    def test_timeout_flush(self):
        clock = Clock()
        svc, codes = make_election(n=3, clock=clock)
        svc.cast(get_token(svc, *sorted(codes.items())[0]).build_ballot({"president": "c1", "secretary": "c1"}))
        self.assertEqual(len(svc.ballot_entries()), 0)
        clock.t += config.MIX_MAX_WAIT_S
        svc.stats()
        self.assertEqual(len(svc.ballot_entries()), 1)

    def test_bad_sealed_opening_is_spoiled_not_counted(self):
        svc, codes = make_election(n=4)
        devs = [get_token(svc, r, c) for r, c in sorted(codes.items())[:3]]
        for d in devs[:2]:
            svc.cast(d.build_ballot({"president": "c1", "secretary": "c2"}))
        b = devs[2].build_ballot({"president": "c2", "secretary": "c2"})
        b["sealed"] = seal.seal(svc.keys["trustee"].public(),  # opening that does not match the commitment
                                canonical({"choices": {"president": "c1", "secretary": "c1"}, "nonce": "00" * 32}),
                                b["token"])
        svc.cast(b)
        res = svc.close_and_tally()
        self.assertEqual(res["tally"]["counted"], 2)
        self.assertEqual(res["tally"]["spoiled"], 1)
        self.assertEqual(res["tally"]["counts"]["president"]["c1"], 2)
        self.assertEqual(res["report"]["verdict"], "VERIFIED")
        self.assertEqual(svc.receipt(sha256_hex(b["token"])[:16])["status"], "spoiled")

    def test_trustee_publishing_false_opening_is_caught(self):
        svc, codes = make_election(n=4)
        for r, c in sorted(codes.items())[:3]:
            svc.cast(get_token(svc, r, c).build_ballot({"president": "c1", "secretary": "c2"}))
        svc.close_and_tally()
        import copy
        from campusvote import board
        entries = copy.deepcopy(svc.entries)
        op = next(e for e in entries if e["type"] == "opening")
        op["data"]["choices"]["president"] = "c2"
        for e in entries[op["seq"]:]:  # even with a perfectly re-hashed chain
            e["prev"] = entries[e["seq"] - 1]["hash"]
            e["hash"] = board.entry_hash(e)
        f = {s["id"] for s in audit.audit(entries)["steps"] if not s["ok"]}
        self.assertIn("openings", f)
        self.assertIn("recount", f)


class TestUnlinkabilityAndAttacks(unittest.TestCase):
    def test_linkability_report_on_service(self):
        svc, codes = make_election(n=8)
        for r, c in sorted(codes.items()):
            svc.cast(get_token(svc, r, c).build_ballot({"president": "c2", "secretary": "c3"}))
        svc.flush_pool(force=True)
        rep = svc.linkability()
        self.assertEqual(rep["ballots"], 8)
        self.assertEqual(rep["consistent"], 8)

    def test_every_attack_is_stopped(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="cv-atk-")
        try:
            svc, codes = make_election(n=10, data_dir=d)
            regs = sorted(codes.items())
            for r, c in regs[:7]:
                svc.cast(get_token(svc, r, c).build_ballot({"president": "c1", "secretary": "c2"}))
            get_token(svc, *regs[7])  # a token-holder who has not voted yet
            svc.flush_pool(force=True)
            for name in sorted(attacks.ATTACKS):
                res = attacks.run(svc, name)
                self.assertTrue(res["blocked"], (name, res["message"]))
                if name.startswith("tamper"):
                    svc.restore()
            self.assertEqual(svc.verify()["verdict"], "VERIFIED")
            self.assertEqual(len(svc.ballot_entries()), 7)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_unknown_attack(self):
        svc, _ = make_election(n=2)
        with self.assertRaises(ValidationError):
            attacks.run(svc, "nope")


class TestDemoData(unittest.TestCase):
    def build(self):
        svc = ElectionService(None, keys=small_keys(), otp_iters=1, clock=Clock(1_800_000_000))
        return svc, demo.build_demo(svc, base_time=1_800_000_000, n_students=30, n_tokens=24, n_ballots=20)

    def test_demo_is_deterministic_and_verifies(self):
        (a, ia), (b, ib) = self.build(), self.build()
        self.assertEqual(ia["head"], ib["head"])
        self.assertEqual(a.verify()["verdict"], "VERIFIED")
        self.assertEqual(len(a.ballot_entries()), 20)
        self.assertEqual(a.phase, "voting")
        v = a.demo_voter()
        self.assertNotIn(v["reg_no"], a.state["issued"])
        res = a.close_and_tally()
        self.assertEqual(res["tally"]["counted"], 20)

    def test_simulate_runs_full_protocol(self):
        svc, _ = self.build()
        r = svc.simulate(3)
        self.assertEqual(r["cast"], 3)
        svc.flush_pool(force=True)
        self.assertEqual(len(svc.ballot_entries()), 23)
        self.assertEqual(svc.verify()["verdict"], "VERIFIED")

    def test_demo_voter_missing_for_custom_election(self):
        svc, _ = make_election(n=2)
        with self.assertRaises(NotFound):
            svc.demo_voter()


class TestElectionSetup(unittest.TestCase):
    def test_validation(self):
        svc = ElectionService(None, keys=small_keys(), otp_iters=1)
        with self.assertRaises(ValidationError):
            svc.create_election("x" * 100, [{"title": "P", "candidates": ["A"]}])
        with self.assertRaises(ValidationError):
            svc.create_election("Ok title", [])
        with self.assertRaises(ValidationError):
            svc.create_election("Ok title", [{"title": "P", "candidates": ["<script>"]}])
        m = svc.create_election("Ok title", [{"title": "P", "candidates": ["A", "B"]}])
        self.assertEqual([c["id"] for c in m["posts"][0]["candidates"]], ["c1", "c2", "NOTA"])
        with self.assertRaises(ValidationError):
            svc.upload_roster("name\nA")
        with self.assertRaises(ValidationError):
            svc.upload_roster("reg_no,name\nAB1,x\nAB1,y")
        self.assertEqual(svc.upload_roster("Register No,Student Name,Department\n24cse1,A,cse\n")["count"], 1)
        with self.assertRaises(Conflict):
            svc.cast({})  # still in the setup phase

    def test_cannot_replace_running_election(self):
        svc, _ = make_election(n=2)
        with self.assertRaises(Conflict):
            svc.create_election("Another", [{"title": "P", "candidates": ["A"]}])


if __name__ == "__main__":
    unittest.main()
