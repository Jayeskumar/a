import hashlib
import random
import unittest

from helpers import get_token, make_election, small_keys, voter
from campusvote import blind, rsa
from campusvote.numtheory import gcd


class TestRSA(unittest.TestCase):
    def setUp(self):
        self.k = small_keys()["issuer"]

    def test_keypair_structure(self):
        k = self.k
        self.assertEqual(k.p * k.q, k.n)
        self.assertEqual(k.n.bit_length(), 1024)
        lam = (k.p - 1) * (k.q - 1) // gcd(k.p - 1, k.q - 1)
        self.assertEqual(k.e * k.d % lam, 1)
        self.assertGreater(abs(k.p - k.q), 1 << 400)

    def test_crt_sign_equals_plain_pow(self):
        rng = random.Random(7)
        for _ in range(20):
            m = rng.randrange(2, self.k.n)
            self.assertEqual(self.k.raw_sign(m), pow(m, self.k.d, self.k.n))

    def test_2048_bit_keygen(self):
        k = rsa.generate_keypair(2048, random.Random(11))
        self.assertEqual(k.n.bit_length(), 2048)
        s = rsa.sign_message(k, b"hello")
        self.assertTrue(rsa.verify_message(k.public(), b"hello", s))

    def test_sign_verify(self):
        s = rsa.sign_message(self.k, "checkpoint 7")
        pub = self.k.public()
        self.assertTrue(rsa.verify_message(pub, "checkpoint 7", s))
        self.assertFalse(rsa.verify_message(pub, "checkpoint 8", s))
        self.assertFalse(rsa.verify_message(pub, "checkpoint 7", s + 1))
        self.assertFalse(rsa.verify_message(pub, "checkpoint 7", s + self.k.n))  # out of range

    def test_fdh_known_answer_and_range(self):
        n = self.k.n
        msg = b"CV1-token|E|abc"
        outbits = n.bit_length() - 1
        k = (outbits + 7) // 8
        buf = b"".join(hashlib.sha256(b"CV1-FDH" + i.to_bytes(4, "big") + msg).digest() for i in range(4))
        expected = int.from_bytes(buf[:k], "big") >> (8 * k - outbits)
        self.assertEqual(rsa.fdh(msg, n), expected)
        self.assertLess(rsa.fdh(msg, n), n)
        self.assertNotEqual(rsa.fdh(msg, n), rsa.fdh(msg + b"x", n))


class TestBlindSignatures(unittest.TestCase):
    def setUp(self):
        self.priv = small_keys()["issuer"]
        self.pub = self.priv.public()

    def test_blind_sign_unblind_verify_roundtrip(self):
        rng = random.Random(8)
        for _ in range(25):
            token = blind.new_token(rng)
            msg = blind.token_message("E1", token)
            blinded, r = blind.blind(self.pub, msg, rng)
            s_blind = blind.sign_blinded(self.priv, blinded)
            sig = blind.unblind(self.pub, s_blind, r)
            self.assertTrue(blind.verify_token(self.pub, "E1", token, sig))
            # the authority saw neither the message hash nor the final signature
            self.assertNotEqual(blinded, rsa.fdh(msg, self.pub.n))
            self.assertNotEqual(s_blind, sig)
            self.assertEqual(sig, pow(rsa.fdh(msg, self.pub.n), self.priv.d, self.pub.n))

    def test_sign_blinded_rejects_out_of_range(self):
        for bad in (0, 1, self.pub.n - 1, self.pub.n, self.pub.n + 5):
            with self.assertRaises(ValueError):
                blind.sign_blinded(self.priv, bad)

    def test_unlinkability_every_pairing_is_consistent(self):
        """Perfect blindness: each issuance record fits EVERY ballot equally well."""
        rng = random.Random(9)
        issued, ballots = [], []
        for _ in range(6):
            dev = voter_like(self.pub, rng)
            m_b, r = blind.blind(self.pub, blind.token_message("E1", dev), rng)
            s_b = blind.sign_blinded(self.priv, m_b)
            issued.append((m_b, s_b))
            ballots.append((dev, blind.unblind(self.pub, s_b, r)))
        rng.shuffle(ballots)
        for m_b, s_b in issued:
            for token, sig in ballots:
                r, ok = blind.linking_factor(self.pub, m_b, s_b, "E1", token, sig)
                self.assertTrue(ok)
                self.assertTrue(1 < r < self.pub.n)

    def test_authority_view_never_contains_token(self):
        svc, codes = make_election(n=6)
        devs = [get_token(svc, reg, code, random.Random(i)) for i, (reg, code) in enumerate(sorted(codes.items()))]
        view = repr(svc.state["issued"]) + repr([e for e in svc.entries if e["type"] == "issuance"])
        for d in devs:
            self.assertNotIn(d.token, view)
            self.assertNotIn("%x" % d.sig, view)
            self.assertNotIn("%x" % rsa.fdh(blind.token_message(svc.eid, d.token), svc.keys["issuer"].n), view)
            self.assertIsNone(d.r)  # device forgot the blinding factor

    def test_multiplicative_forgery_fails_under_fdh(self):
        rng = random.Random(10)
        t1, t2 = blind.new_token(rng), blind.new_token(rng)
        m1, m2 = (rsa.fdh(blind.token_message("E1", t), self.pub.n) for t in (t1, t2))
        s1, s2 = self.priv.raw_sign(m1), self.priv.raw_sign(m2)
        s = s1 * s2 % self.pub.n
        self.assertTrue(self.pub.raw_verify(m1 * m2 % self.pub.n, s))  # textbook RSA is malleable...
        for _ in range(50):                                             # ...but no token hashes to m1*m2
            self.assertFalse(blind.verify_token(self.pub, "E1", blind.new_token(rng), s))

    def test_cross_election_replay_fails(self):
        dev = voter_like(self.pub, random.Random(12))
        m_b, r = blind.blind(self.pub, blind.token_message("OLD-2025", dev), random.Random(13))
        sig = blind.unblind(self.pub, blind.sign_blinded(self.priv, m_b), r)
        self.assertTrue(blind.verify_token(self.pub, "OLD-2025", dev, sig))
        self.assertFalse(blind.verify_token(self.pub, "NEW-2026", dev, sig))

    def test_device_rejects_bad_blind_signature(self):
        svc, _ = make_election(n=2)
        dev = voter(svc, random.Random(14))
        dev.prepare_token()
        with self.assertRaises(ValueError):
            dev.finish_token(12345)


def voter_like(pub, rng):
    return blind.new_token(rng)


if __name__ == "__main__":
    unittest.main()
