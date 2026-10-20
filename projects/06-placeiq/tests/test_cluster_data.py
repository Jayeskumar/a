import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placeiq import cluster, config as C, data  # noqa: E402


class TestKMeans(unittest.TestCase):
    def blobs(self):
        rng = random.Random(4)
        centres = [(0, 0), (10, 10), (-10, 8)]
        X, truth = [], []
        for c, (cx, cy) in enumerate(centres):
            for _ in range(40):
                X.append([cx + rng.gauss(0, 0.8), cy + rng.gauss(0, 0.8)])
                truth.append(c)
        return X, truth

    def test_recovers_separated_blobs(self):
        X, truth = self.blobs()
        res = cluster.kmeans(X, 3, seed=1)
        # every true blob maps to exactly one cluster label (purity 100 %)
        mapping = {}
        for t, l in zip(truth, res["labels"]):
            mapping.setdefault(t, set()).add(l)
        self.assertTrue(all(len(v) == 1 for v in mapping.values()))
        self.assertEqual(len({next(iter(v)) for v in mapping.values()}), 3)

    def test_deterministic_and_inertia_drops_with_k(self):
        X, _ = self.blobs()
        a, b = cluster.kmeans(X, 3, seed=9), cluster.kmeans(X, 3, seed=9)
        self.assertEqual(a["labels"], b["labels"])
        self.assertLess(cluster.kmeans(X, 3)["inertia"], cluster.kmeans(X, 2)["inertia"])

    def test_kmeans_pp_picks_distinct_far_centres(self):
        X, _ = self.blobs()
        cents = cluster.kmeans_pp_init(X, 3, random.Random(0))
        d = [sum((p - q) ** 2 for p, q in zip(cents[i], cents[j])) for i in range(3) for j in range(i + 1, 3)]
        self.assertGreater(min(d), 25)  # one seed per blob, never two in the same blob

    def test_bad_k(self):
        with self.assertRaises(ValueError):
            cluster.kmeans([[0.0], [1.0]], 3)

    def test_persona_names_unique_and_sensible(self):
        feats = C.CLUSTER_FEATURES
        star = {f: 0.0 for f in feats}
        star.update(coding_problems=1.8, projects=1.4, hackathons=1.2, _placed=1.0)
        risk = {f: -0.4 for f in feats}
        risk.update(backlogs=2.2, cgpa=-1.5, _placed=-1.6)
        topper = {f: -0.1 for f in feats}
        topper.update(cgpa=0.9, aptitude_score=0.6, projects=-0.4, coding_problems=-0.3, _placed=0.3)
        names = cluster.name_clusters([star, risk, topper])
        self.assertEqual(names[0][0], "Coding stars")
        self.assertEqual(names[1][0], "At risk")
        self.assertEqual(names[2][0], "Academic toppers lacking projects")
        self.assertEqual(len({n for n, _ in names}), 3)


class TestDataset(unittest.TestCase):
    def test_generation_is_deterministic_and_valid(self):
        a, b = data.generate(), data.generate()
        self.assertEqual(a, b)
        self.assertEqual(len(a), 600)
        self.assertEqual({r["dept"] for r in a}, set(C.DEPARTMENTS))
        rate = sum(r["placed"] for r in a) / len(a)
        self.assertTrue(0.45 < rate < 0.75)
        for r in a:
            for f in C.FEATURE_NAMES:
                lo, hi = C.FEATURE_RANGES[f]
                self.assertTrue(lo <= r[f] <= hi, (f, r[f]))
            self.assertEqual(r["package_lpa"] > 0, r["placed"] == 1)

    def test_csv_roundtrip_is_clean(self):
        rows = data.generate(n=60)
        valid, rep = data.validate_csv(data.to_csv(rows))
        self.assertEqual(rep["invalid_rows"], 0)
        self.assertEqual(len(valid), 60)
        self.assertEqual(valid[0]["cgpa"], rows[0]["cgpa"])

    def test_bad_rows_are_reported_with_line_numbers(self):
        rows = data.generate(n=10)
        rows[2]["cgpa"] = 12
        rows[4]["dept"] = "CIVIL"
        rows[5]["placed"] = "maybe"
        rows[6]["backlogs"] = 1.5
        rows[7]["coding_problems"] = "lots"
        rows[8]["student_id"] = rows[0]["student_id"]
        valid, rep = data.validate_csv(data.to_csv(rows))
        self.assertEqual(rep["valid_rows"], 4)
        self.assertEqual(rep["invalid_rows"], 6)
        lines = {e["line"]: " ".join(e["problems"]) for e in rep["errors"]}
        self.assertIn("cgpa", lines[4])           # header is line 1, row index 2 -> line 4
        self.assertIn("CIVIL", lines[6])
        self.assertIn("placed", lines[7])
        self.assertIn("whole number", lines[8])
        self.assertIn("not a number", lines[9])
        self.assertIn("duplicate", lines[10])

    def test_missing_columns_aliases_and_pending(self):
        _, rep = data.validate_csv("dept,cgpa\nCSE,8\n")
        self.assertIn("placed", rep["missing_columns"])
        header = "Department,CGPA,10th,12th,backlogs,internships,projects,certifications,coding,hackathons,aptitude,communication,mock_interview,placed,extra\n"
        text = header + "aids,8.1,90,88,0,1,2,1,150,1,70,65,60,yes,x\nMechanical,6.5,70,65,2,0,1,0,40,0,50,55,45,,y\n"
        valid, rep = data.validate_csv(text)
        self.assertEqual(rep["invalid_rows"], 0, rep["errors"])
        self.assertEqual([v["dept"] for v in valid], ["AI&DS", "MECH"])
        self.assertEqual(valid[0]["placed"], 1)
        self.assertIsNone(valid[1]["placed"])          # blank -> pending outcome
        self.assertEqual(rep["ignored_columns"], ["extra"])

    def test_garbage_never_raises(self):
        for text in ["", "   ", "\x00\x01", "a\n\"unterminated", None, "dept\n" + "x\n" * 5]:
            valid, rep = data.validate_csv(text)
            self.assertEqual(valid, [])
            self.assertIsInstance(rep, dict)


if __name__ == "__main__":
    unittest.main()
