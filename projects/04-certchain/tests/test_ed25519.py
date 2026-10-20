import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from certchain import ed25519  # noqa: E402

# RFC 8032 section 7.1 test vectors.
VECTORS = [
    ("TEST 1",
     "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("TEST 2",
     "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("TEST 3",
     "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("TEST SHA(abc)",
     "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     hashlib.sha512(b"abc").hexdigest(),
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b58909351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]


class TestRFC8032Vectors(unittest.TestCase):
    def test_public_keys(self):
        for name, sk, pk, _, _ in VECTORS:
            with self.subTest(name):
                self.assertEqual(ed25519.public_key(bytes.fromhex(sk)).hex(), pk)

    def test_signatures(self):
        for name, sk, _, msg, sig in VECTORS:
            with self.subTest(name):
                self.assertEqual(ed25519.sign(bytes.fromhex(sk), bytes.fromhex(msg)).hex(), sig)

    def test_verify(self):
        for name, _, pk, msg, sig in VECTORS:
            with self.subTest(name):
                self.assertTrue(ed25519.verify(bytes.fromhex(pk), bytes.fromhex(msg), bytes.fromhex(sig)))


class TestRejections(unittest.TestCase):
    def setUp(self):
        self.sk = bytes.fromhex(VECTORS[1][1])
        self.pk = bytes.fromhex(VECTORS[1][2])
        self.msg = b"CGPA 8.72"
        self.sig = ed25519.sign(self.sk, self.msg)

    def test_roundtrip(self):
        self.assertTrue(ed25519.verify(self.pk, self.msg, self.sig))

    def test_wrong_message(self):
        self.assertFalse(ed25519.verify(self.pk, b"CGPA 9.72", self.sig))

    def test_wrong_key(self):
        other = ed25519.public_key(bytes.fromhex(VECTORS[0][1]))
        self.assertFalse(ed25519.verify(other, self.msg, self.sig))

    def test_bit_flips_rejected(self):
        for i in (0, 31, 32, 63):
            bad = bytearray(self.sig)
            bad[i] ^= 0x01
            self.assertFalse(ed25519.verify(self.pk, self.msg, bytes(bad)), i)

    def test_non_canonical_s_rejected(self):
        s = int.from_bytes(self.sig[32:], "little") + ed25519.L
        bad = self.sig[:32] + s.to_bytes(32, "little")
        self.assertFalse(ed25519.verify(self.pk, self.msg, bad))

    def test_bad_lengths(self):
        self.assertFalse(ed25519.verify(self.pk[:31], self.msg, self.sig))
        self.assertFalse(ed25519.verify(self.pk, self.msg, self.sig[:63]))

    def test_random_keys(self):
        kp = ed25519.KeyPair(ed25519.generate_secret())
        sig = kp.sign(b"hello")
        self.assertTrue(kp.verify(b"hello", sig))
        self.assertFalse(kp.verify(b"hellp", sig))

    def test_point_roundtrip(self):
        enc = ed25519.point_compress(ed25519.G)
        self.assertTrue(ed25519.point_equal(ed25519.point_decompress(enc), ed25519.G))
        # [L]B is the identity
        self.assertTrue(ed25519.point_equal(ed25519.point_mul(ed25519.L, ed25519.G), ed25519.IDENTITY))


if __name__ == "__main__":
    unittest.main()
