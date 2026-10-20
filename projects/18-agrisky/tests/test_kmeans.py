import random
import unittest

import _path  # noqa: F401
from agrisky import kmeans


class TestKMeans(unittest.TestCase):
    def test_hand_example_1d(self):
        pts = [(0.0,), (1.0,), (10.0,), (11.0,)]
        res = kmeans.lloyd(pts, [(0.0,), (1.0,)])
        cents = sorted(c[0] for c in res["centroids"])
        self.assertEqual(cents, [0.5, 10.5])
        self.assertTrue(res["converged"])
        self.assertAlmostEqual(res["inertia"], 4 * 0.25)

    def test_blobs_converge_and_recover(self):
        rng = random.Random(3)
        centres = [(0, 0, 0, 0), (5, 5, 0, 0), (0, 5, 5, 5)]
        pts, truth = [], []
        for c, (a, b, d, e) in enumerate(centres):
            for _ in range(60):
                pts.append((a + rng.gauss(0, .3), b + rng.gauss(0, .3), d + rng.gauss(0, .3),
                            e + rng.gauss(0, .3)))
                truth.append(c)
        res = kmeans.kmeans(pts, 3, seed=1, n_init=3)
        self.assertTrue(res["converged"])
        self.assertLess(res["iterations"], 30)
        # every true blob maps to exactly one cluster
        mapping = {}
        for t, l in zip(truth, res["labels"]):
            mapping.setdefault(t, set()).add(l)
        self.assertTrue(all(len(v) == 1 for v in mapping.values()))
        self.assertEqual(len({next(iter(v)) for v in mapping.values()}), 3)

    def test_inertia_never_increases(self):
        rng = random.Random(9)
        pts = [(rng.random(), rng.random()) for _ in range(300)]
        res = kmeans.kmeans(pts, 5, seed=2, n_init=1)
        h = res["history"]
        for a, b in zip(h, h[1:]):
            self.assertLessEqual(b, a + 1e-9)

    def test_deterministic(self):
        rng = random.Random(5)
        pts = [(rng.random(), rng.random(), rng.random()) for _ in range(200)]
        a = kmeans.kmeans(pts, 4, seed=7)
        b = kmeans.kmeans(pts, 4, seed=7)
        self.assertEqual(a["labels"], b["labels"])

    def test_assign_fast_path_matches_generic(self):
        rng = random.Random(1)
        pts = [tuple(rng.random() for _ in range(4)) for _ in range(50)]
        cents = pts[:3]
        lab, inertia = kmeans.assign(pts, cents)
        for p, l in zip(pts, lab):
            self.assertEqual(l, kmeans.nearest(p, cents)[0])
        pts5 = [tuple(rng.random() for _ in range(5)) for _ in range(20)]
        lab5, _ = kmeans.assign(pts5, pts5[:2])
        self.assertEqual(lab5[0], 0)

    def test_kmeanspp_distinct(self):
        pts = [(float(i), 0.0) for i in range(10)]
        init = kmeans.kmeans_pp_init(pts, 4, random.Random(0))
        self.assertEqual(len(set(init)), 4)

    def test_standardize(self):
        rows, means, stds = kmeans.standardize([[1, 2, 3, 4], [10, 10, 10, 10]])
        self.assertAlmostEqual(means[0], 2.5)
        self.assertEqual(stds[1], 1.0)          # constant column -> no division by zero
        col = [r[0] for r in rows]
        self.assertAlmostEqual(sum(col), 0.0)
        self.assertAlmostEqual(sum(v * v for v in col) / 4, 1.0)

    def test_bad_k(self):
        with self.assertRaises(ValueError):
            kmeans.kmeans([(0.0,), (1.0,)], 3)


if __name__ == "__main__":
    unittest.main()
