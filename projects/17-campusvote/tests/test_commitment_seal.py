import random
import unittest

from helpers import small_keys
from campusvote import commitment, seal
from campusvote.util import ValidationError, canonical


class TestCommitment(unittest.TestCase):
    def test_open_verify(self):
        n = commitment.new_nonce(random.Random(1))
        ch = {"president": "c1", "secretary": "NOTA"}
        c = commitment.commit("E", "ab" * 32, ch, n)
        self.assertTrue(commitment.verify_opening("E", "ab" * 32, ch, n, c))
        self.assertTrue(commitment.verify_opening("E", "ab" * 32, {"secretary": "NOTA", "president": "c1"}, n, c))

    def test_binding(self):
        n = commitment.new_nonce(random.Random(2))
        c = commitment.commit("E", "ab" * 32, {"president": "c1"}, n)
        self.assertFalse(commitment.verify_opening("E", "ab" * 32, {"president": "c2"}, n, c))
        self.assertFalse(commitment.verify_opening("E", "ab" * 32, {"president": "c1"}, "00" * 32, c))
        self.assertFalse(commitment.verify_opening("E", "cd" * 32, {"president": "c1"}, n, c))
        self.assertFalse(commitment.verify_opening("F", "ab" * 32, {"president": "c1"}, n, c))
        self.assertFalse(commitment.verify_opening("E", "ab" * 32, None, n, c))

    def test_hiding_same_vote_looks_different(self):
        rng = random.Random(3)
        cs = {commitment.commit("E", "ab" * 32, {"president": "c1"}, commitment.new_nonce(rng)) for _ in range(50)}
        self.assertEqual(len(cs), 50)


class TestSeal(unittest.TestCase):
    def setUp(self):
        self.priv = small_keys()["trustee"]
        self.pub = self.priv.public()
        self.pt = canonical({"choices": {"president": "c2"}, "nonce": "11" * 32})

    def test_roundtrip(self):
        s = seal.seal(self.pub, self.pt, "tok", random.Random(4))
        self.assertEqual(seal.open_sealed(self.priv, s, "tok"), self.pt)
        self.assertNotIn(b"president".hex(), s["ct"])
        self.assertEqual(seal.validate_sealed(s, self.pub)["tag"], s["tag"])

    def test_wrong_ballot_or_tampering_detected(self):
        s = seal.seal(self.pub, self.pt, "tok", random.Random(5))
        with self.assertRaises(seal.SealError):
            seal.open_sealed(self.priv, s, "other-token")          # swapped between ballots
        bad = dict(s, ct=("%02x" % (int(s["ct"][:2], 16) ^ 1)) + s["ct"][2:])
        with self.assertRaises(seal.SealError):
            seal.open_sealed(self.priv, bad, "tok")                # bit flip
        with self.assertRaises(seal.SealError):
            seal.open_sealed(self.priv, dict(s, tag="0" * 64), "tok")
        with self.assertRaises(seal.SealError):
            seal.open_sealed(small_keys()["board"], s, "tok")       # wrong key

    def test_validate_rejects_malformed(self):
        s = seal.seal(self.pub, self.pt, "tok", random.Random(6))
        for bad in (None, "x", dict(s, c0="zz"), dict(s, ct="abc"), dict(s, tag="12"), dict(s, c0="f" * len(s["c0"]))):
            with self.assertRaises(ValidationError):
                seal.validate_sealed(bad, self.pub)


if __name__ == "__main__":
    unittest.main()
