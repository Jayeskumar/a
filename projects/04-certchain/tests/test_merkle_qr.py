import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from certchain import merkle, qr  # noqa: E402


def leaves(n):
    return [hashlib.sha256(("rec%d" % i).encode()).hexdigest() for i in range(n)]


class TestMerkle(unittest.TestCase):
    def test_single_leaf(self):
        hs = leaves(1)
        root = merkle.merkle_root(hs)
        self.assertEqual(root, merkle.leaf_hash(hs[0]).hex())
        self.assertEqual(merkle.merkle_proof(hs, 0), [])
        self.assertTrue(merkle.verify_proof(hs[0], [], root))

    def test_two_leaves_manual(self):
        hs = leaves(2)
        expect = merkle.node_hash(merkle.leaf_hash(hs[0]), merkle.leaf_hash(hs[1])).hex()
        self.assertEqual(merkle.merkle_root(hs), expect)

    def test_three_leaves_promotes_odd_node(self):
        hs = leaves(3)
        l0, l1, l2 = (merkle.leaf_hash(h) for h in hs)
        expect = merkle.node_hash(merkle.node_hash(l0, l1), l2).hex()
        self.assertEqual(merkle.merkle_root(hs), expect)
        self.assertEqual(len(merkle.merkle_proof(hs, 2)), 1)

    def test_all_proofs_verify_for_many_sizes_including_odd(self):
        for n in list(range(1, 18)) + [31, 33, 100]:
            hs = leaves(n)
            root = merkle.merkle_root(hs)
            for i in range(n):
                proof = merkle.merkle_proof(hs, i)
                self.assertTrue(merkle.verify_proof(hs[i], proof, root), (n, i))
                self.assertLessEqual(len(proof), max(1, (n - 1).bit_length()))

    def test_wrong_leaf_or_tampered_proof_fails(self):
        hs = leaves(7)
        root = merkle.merkle_root(hs)
        proof = merkle.merkle_proof(hs, 4)
        self.assertFalse(merkle.verify_proof(hs[3], proof, root))
        bad = [dict(s) for s in proof]
        bad[0]["side"] = "L" if bad[0]["side"] == "R" else "R"
        self.assertFalse(merkle.verify_proof(hs[4], bad, root))
        bad = [dict(s) for s in proof]
        bad[-1]["hash"] = "00" * 32
        self.assertFalse(merkle.verify_proof(hs[4], bad, root))
        self.assertFalse(merkle.verify_proof(hs[4], [{"side": "X", "hash": "00"}], root))
        self.assertFalse(merkle.verify_proof("zz", proof, root))

    def test_no_duplicate_last_leaf_collision(self):
        # Bitcoin-style duplication makes [a,b,c] and [a,b,c,c] share a root.
        hs = leaves(3)
        self.assertNotEqual(merkle.merkle_root(hs), merkle.merkle_root(hs + [hs[-1]]))

    def test_order_matters_and_empty(self):
        hs = leaves(4)
        self.assertNotEqual(merkle.merkle_root(hs), merkle.merkle_root(list(reversed(hs))))
        self.assertEqual(merkle.merkle_root([]), merkle.EMPTY_ROOT)
        with self.assertRaises(IndexError):
            merkle.merkle_proof(hs, 4)


class TestQR(unittest.TestCase):
    """Structural checks. (Decodability of every version 1-10 and every
    mask was additionally checked with an external decoder during
    development - see REPORT.md.)"""

    def test_sizes_and_versions(self):
        self.assertEqual(len(qr.encode("hi")), 21)                 # version 1
        url = "http://192.168.1.10:8004/#verify=KSRCE-26-00012"
        m = qr.encode(url)
        self.assertEqual(len(m), 33)                                # 47 bytes -> v4-M
        self.assertTrue(all(len(r) == len(m) for r in m))
        with self.assertRaises(ValueError):
            qr.encode("x" * 300)

    def test_finder_patterns_present(self):
        m = qr.encode("CertChain")
        s = len(m)
        for ox, oy in ((0, 0), (s - 7, 0), (0, s - 7)):
            for i in range(7):
                self.assertTrue(m[oy][ox + i] and m[oy + 6][ox + i])   # top/bottom edges
                self.assertTrue(m[oy + i][ox] and m[oy + i][ox + 6])   # left/right edges
            self.assertTrue(m[oy + 3][ox + 3])                         # centre
        self.assertTrue(m[s - 8][8])                                   # dark module

    def test_reed_solomon_known_value(self):
        # Generator polynomial for degree 2 is x^2 + 3x + 2 (roots 1 and 2 in GF(256)).
        self.assertEqual(qr._rs_divisor(2), [3, 2])
        self.assertEqual(qr._gf_mul(0x80, 2), 0x1D)

    def test_svg(self):
        svg = qr.to_svg("abc")
        self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"))


if __name__ == "__main__":
    unittest.main()
