import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civiclens.dedup import (DuplicateDetector, LSHIndex, MinHasher, PairScorer, UnionFind, geo_cell,  # noqa: E402
                             haversine_m, neighbour_cells, stable_hash)
from civiclens.hotspot import dbscan, emerging_test, match_planted, poisson_sf, poisson_z, summarise_clusters  # noqa: E402
from civiclens.text import jaccard, shingles  # noqa: E402


class TestMinHash(unittest.TestCase):
    def test_estimate_tracks_exact_jaccard(self):
        rng = random.Random(1)
        mh = MinHasher(256, seed=4)
        errs = []
        for _ in range(40):
            universe = ["t%d" % i for i in range(60)]
            a = set(rng.sample(universe, 25))
            b = set(rng.sample(universe, 25))
            est = MinHasher.similarity(mh.signature(a), mh.signature(b))
            errs.append(abs(est - jaccard(a, b)))
        self.assertLess(sum(errs) / len(errs), 0.04)
        self.assertLess(max(errs), 0.12)

    def test_identical_and_disjoint(self):
        mh = MinHasher(64)
        a, b = {"x", "y", "z"}, {"p", "q"}
        self.assertEqual(MinHasher.similarity(mh.signature(a), mh.signature(set(a))), 1.0)
        self.assertLess(MinHasher.similarity(mh.signature(a), mh.signature(b)), 0.1)
        self.assertIsNone(mh.signature(set()))

    def test_hash_is_stable_across_runs(self):
        self.assertEqual(stable_hash("garbage"), stable_hash("garbage"))
        self.assertNotEqual(stable_hash("garbage"), stable_hash("garbag"))


class TestLSH(unittest.TestCase):
    def test_banding_collides_identical_and_similar(self):
        mh = MinHasher(64, seed=2)
        idx = LSHIndex(bands=32, rows=2)
        s1 = {"streetlight", "notworking", "murugan", "temple"}
        s2 = {"streetlight", "notworking", "murugan", "temple", "dark"}
        s3 = {"garbage", "dump", "market", "smell", "nehru"}
        idx.add("a", mh.signature(s1))
        idx.add("c", mh.signature(s3))
        self.assertIn("a", idx.query(mh.signature(s1)))
        self.assertIn("a", idx.query(mh.signature(s2)))
        self.assertNotIn("c", idx.query(mh.signature(s2)))

    def test_s_curve(self):
        self.assertAlmostEqual(LSHIndex.probability(1.0, 16, 4), 1.0)
        self.assertAlmostEqual(LSHIndex.probability(0.0, 16, 4), 0.0)
        self.assertAlmostEqual(LSHIndex.probability(0.5, 16, 4), 1 - (1 - 0.5 ** 4) ** 16)
        self.assertLess(LSHIndex.probability(0.2, 16, 4), LSHIndex.probability(0.6, 16, 4))

    def test_geo_tags_separate_far_items(self):
        mh = MinHasher(32)
        sig = mh.signature({"pothole", "road"})
        idx = LSHIndex(8, 4)
        idx.add(1, sig, geo_cell(11.37, 77.88))
        near = neighbour_cells(geo_cell(11.3705, 77.8805))
        far = neighbour_cells(geo_cell(11.39, 77.91))
        self.assertEqual(idx.query(sig, near), {1})
        self.assertEqual(idx.query(sig, far), set())

    def test_candidate_pairs(self):
        idx = LSHIndex(2, 1)
        idx.add(1, (5, 6))
        idx.add(2, (5, 7))
        idx.add(3, (9, 9))
        self.assertEqual(idx.candidate_pairs(), {(1, 2)})


class TestGeoAndDetector(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(haversine_m(11.0, 77.0, 12.0, 77.0) / 1000, 111.2, delta=0.3)
        self.assertEqual(haversine_m(11.37, 77.88, 11.37, 77.88), 0.0)

    def test_union_find_keeps_earliest_root(self):
        uf = UnionFind(5)
        uf.union(3, 4)
        uf.union(1, 4)
        self.assertEqual(uf.find(4), 1)
        self.assertEqual(uf.find(3), 1)
        self.assertEqual(uf.find(2), 2)

    def test_stream_merges_duplicates_only(self):
        base = {"lat": 11.3700, "lon": 77.8800, "dept": "STREETLIGHT", "closed_t": None}
        items = [
            dict(base, t=0.0, shingles=shingles("street light not working near Murugan temple")),
            dict(base, t=0.3, lat=11.3702, shingles=shingles("முருகன் கோவில் அருகில் தெரு விளக்கு எரியவில்லை")),
            dict(base, t=0.5, lat=11.3900, shingles=shingles("street light not working near Murugan temple")),   # 2 km away
            dict(base, t=9.0, shingles=shingles("street light not working near Murugan temple")),               # 9 days later
            dict(base, t=0.6, dept="SANITATION", shingles=shingles("garbage dump near Murugan temple")),
        ]
        det = DuplicateDetector(threshold=0.5)
        got = [det.add(it)[0] for it in items]
        self.assertEqual(got, [None, 0, None, None, None])
        self.assertEqual(det.root(1), 0)

    def test_resolved_incident_is_not_a_duplicate_target(self):
        a = {"t": 0.0, "lat": 11.37, "lon": 77.88, "dept": "ROADS", "closed_t": 0.5, "shingles": shingles("big pothole near school")}
        b = dict(a, t=1.0, closed_t=None)
        det = DuplicateDetector(threshold=0.3)
        det.add(a)
        best, _, _ = det.add(b)
        self.assertIsNone(best)

    def test_pair_scorer_learns_sensible_weights(self):
        rng = random.Random(0)
        rows, y = [], []
        for _ in range(400):
            dup = rng.random() < 0.5
            jac = rng.uniform(0.4, 1.0) if dup else rng.uniform(0.1, 0.6)
            dist = rng.uniform(0, 80) if dup else rng.uniform(50, 300)
            gap = rng.uniform(0, 1) if dup else rng.uniform(0, 5)
            rows.append((jac, dist, gap))
            y.append(1 if dup else 0)
        ps = PairScorer(epochs=60).fit(rows, y)
        self.assertGreater(ps.prob(0.9, 10, 0.1), 0.8)
        self.assertLess(ps.prob(0.2, 280, 4.5), 0.2)


class TestDBSCAN(unittest.TestCase):
    def blobs(self):
        rng = random.Random(7)
        pts = []
        for (la, lo) in ((11.370, 77.880), (11.385, 77.905)):
            for _ in range(15):
                pts.append((la + rng.gauss(0, 0.0002), lo + rng.gauss(0, 0.0002)))
        for _ in range(10):                                        # sparse background
            pts.append((11.36 + rng.random() * 0.04, 77.87 + rng.random() * 0.05))
        return pts

    def test_finds_two_clusters_and_noise(self):
        pts = self.blobs()
        labels = dbscan(pts, eps_m=100, min_pts=5)
        self.assertEqual(len({l for l in labels if l >= 0}), 2)
        self.assertEqual(len(set(labels[:15])), 1)
        self.assertEqual(len(set(labels[15:30])), 1)
        self.assertNotEqual(labels[0], labels[15])
        self.assertGreaterEqual(sum(1 for l in labels[30:] if l == -1), 8)
        s = summarise_clusters(pts, labels)
        self.assertEqual(sorted(c["n"] for c in s)[-1] >= 15, True)
        self.assertLess(haversine_m(s[0]["center"][0], s[0]["center"][1], 11.370, 77.880), 60)

    def test_min_pts_too_high_gives_all_noise(self):
        labels = dbscan(self.blobs(), eps_m=100, min_pts=40)
        self.assertTrue(all(l == -1 for l in labels))
        self.assertEqual(dbscan([], 100, 3), [])

    def test_border_point_joins_cluster(self):
        core = [(11.37, 77.88 + k * 0.0001) for k in range(5)]       # ~11 m apart
        border = (11.37, 77.88 + 0.0004 + 0.0008)                    # ~87 m beyond the last core point
        labels = dbscan(core + [border], eps_m=95, min_pts=4)
        self.assertEqual(labels[-1], labels[0])

    def test_match_planted(self):
        det = [{"dept": "ROADS", "center": [11.37, 77.88]}, {"dept": "WATER", "center": [11.37, 77.88]}]
        planted = [{"dept": "ROADS", "center": [11.3705, 77.8801]}]
        self.assertEqual(list(match_planted(det, planted).keys()), [0])


class TestPoisson(unittest.TestCase):
    def test_z_and_tail(self):
        self.assertAlmostEqual(poisson_z(9, 4), 2.5)
        self.assertAlmostEqual(poisson_z(3, 0.1), (3 - 0.5) / 0.5 ** 0.5)       # lambda floor
        self.assertAlmostEqual(poisson_sf(3, 1.0), 1 - 2.5 * 2.718281828459045 ** -1, places=9)
        self.assertEqual(poisson_sf(0, 2.0), 1.0)

    def test_emerging_flag(self):
        series = [1, 2, 1, 2, 1, 2, 9, 1]
        r = emerging_test(series, 7, baseline=4, z_thr=3.0, min_count=5)
        self.assertTrue(r["flag"])
        self.assertAlmostEqual(r["lambda"], 1.5)
        self.assertFalse(emerging_test(series, 8, baseline=4)["flag"])
        self.assertIsNone(emerging_test(series, 3, baseline=4))
        self.assertFalse(emerging_test([0, 0, 0, 0, 3], 5, min_count=5)["flag"])   # too few to matter


if __name__ == "__main__":
    unittest.main()
