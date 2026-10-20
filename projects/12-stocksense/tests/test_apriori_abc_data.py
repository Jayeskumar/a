import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stocksense import abcxyz, apriori, dataset  # noqa: E402

# Textbook example: Han, Kamber & Pei, "Data Mining: Concepts and Techniques", Table 6.1
HAN_KAMBER = [
    ["I1", "I2", "I5"], ["I2", "I4"], ["I2", "I3"], ["I1", "I2", "I4"], ["I1", "I3"],
    ["I2", "I3"], ["I1", "I3"], ["I1", "I2", "I3", "I5"], ["I1", "I2", "I3"],
]


def fs(*items):
    return frozenset(items)


class TestApriori(unittest.TestCase):
    def setUp(self):
        self.freq, self.n = apriori.frequent_itemsets(HAN_KAMBER, 2)   # min support count = 2

    def test_frequent_itemsets_match_textbook(self):
        expected = {
            fs("I1"): 6, fs("I2"): 7, fs("I3"): 6, fs("I4"): 2, fs("I5"): 2,
            fs("I1", "I2"): 4, fs("I1", "I3"): 4, fs("I1", "I5"): 2, fs("I2", "I3"): 4,
            fs("I2", "I4"): 2, fs("I2", "I5"): 2,
            fs("I1", "I2", "I3"): 2, fs("I1", "I2", "I5"): 2,
        }
        self.assertEqual(self.n, 9)
        self.assertEqual(self.freq, expected)

    def test_apriori_pruning_excludes_candidates_with_infrequent_subsets(self):
        # {I1,I3,I5} would be a join candidate but {I3,I5} is infrequent -> pruned
        self.assertNotIn(fs("I1", "I3", "I5"), self.freq)
        self.assertNotIn(fs("I2", "I3", "I5"), self.freq)

    def test_rules_confidence_and_lift(self):
        rules = apriori.association_rules(self.freq, self.n, min_confidence=0.0)
        by = {(tuple(r["antecedent"]), tuple(r["consequent"])): r for r in rules}
        # textbook confidences for rules from {I1, I2, I5}
        self.assertAlmostEqual(by[(("I1", "I5"), ("I2",))]["confidence"], 1.0)
        self.assertAlmostEqual(by[(("I2", "I5"), ("I1",))]["confidence"], 1.0)
        self.assertAlmostEqual(by[(("I5",), ("I1", "I2"))]["confidence"], 1.0)
        self.assertAlmostEqual(by[(("I1", "I2"), ("I5",))]["confidence"], 0.5)
        self.assertAlmostEqual(by[(("I1",), ("I2", "I5"))]["confidence"], 2 / 6)
        self.assertAlmostEqual(by[(("I2",), ("I1", "I5"))]["confidence"], 2 / 7)
        # lift(I5 -> I1) = conf / P(I1) = 1 / (6/9) = 1.5
        self.assertAlmostEqual(by[(("I5",), ("I1",))]["lift"], 1.5)
        self.assertAlmostEqual(by[(("I1",), ("I2",))]["support"], 4 / 9)
        strong = apriori.association_rules(self.freq, self.n, min_confidence=0.7)
        self.assertTrue(all(r["confidence"] >= 0.7 for r in strong))
        self.assertEqual(len(strong), 6)

    def test_fractional_support(self):
        freq, _ = apriori.frequent_itemsets(HAN_KAMBER, 0.5)   # >= 4.5 bills
        self.assertEqual(set(freq), {fs("I1"), fs("I2"), fs("I3")})

    def test_suggestions(self):
        items = {"I1": {"name": "Tea", "category": "Bev"}, "I2": {"name": "Sugar", "category": "Staples"},
                 "I5": {"name": "Rusk", "category": "Bev"}}
        rules = apriori.association_rules(self.freq, self.n, min_confidence=0.3, min_lift=1.0)
        sug = apriori.placement_suggestions(rules, items)
        self.assertTrue(sug)
        self.assertTrue(all(s["lift"] >= 1.5 for s in sug))


class TestAbcXyz(unittest.TestCase):
    def test_pareto_classes(self):
        rev = {"a": 500, "b": 300, "c": 100, "d": 60, "e": 40}
        cls, rows = abcxyz.classify_abc(rev)
        # cumulative share before each item: 0, .5, .8, .9, .96
        self.assertEqual(cls, {"a": "A", "b": "A", "c": "B", "d": "B", "e": "C"})
        self.assertAlmostEqual(rows[-1]["cum_share"], 1.0)

    def test_xyz_and_matrix(self):
        weekly = {"steady": [100, 102, 98, 101, 99], "wavy": [100, 130, 70, 120, 80],
                  "spiky": [10, 10, 100, 10, 10]}
        cls, cvs = abcxyz.classify_xyz(weekly)
        self.assertEqual(cls, {"steady": "X", "wavy": "Y", "spiky": "Z"})
        m = abcxyz.matrix({"steady": 900, "wavy": 60, "spiky": 40}, weekly)
        self.assertEqual(len(m["cells"]), 9)
        self.assertEqual(sum(c["count"] for c in m["cells"]), 3)
        self.assertEqual(m["per_sku"]["steady"]["class"], "AX")


class TestDataset(unittest.TestCase):
    def _csv(self, days=100, skus=("X1", "X2"), extra=""):
        from datetime import date, timedelta
        lines = ["Date,SKU,Quantity" + extra]
        for i in range(days):
            d = date(2026, 1, 1) + timedelta(days=i)
            for k, s in enumerate(skus):
                lines.append("%s,%s,%d" % (d.isoformat(), s, 5 + (i + k) % 7))
        return "\n".join(lines)

    def test_valid_csv_with_aliases(self):
        ds = dataset.parse_csv(self._csv())
        self.assertEqual(ds.n, 100)
        self.assertEqual(sorted(ds.skus), ["X1", "X2"])
        self.assertTrue(all(v["assumed"] for v in ds.on_hand.values()))
        self.assertTrue(any("default price" in w for w in ds.warnings))

    def test_rejects_bad_input(self):
        cases = ["", "a,b,c\n1,2,3", "date,sku,qty\n", "date,sku,qty\n2026-01-01,A,5\n2026-01-02,A,4"]
        for text in cases:
            with self.assertRaises(dataset.ValidationError):
                dataset.parse_csv(text)
        bad = self._csv().replace(",5\n", ",-5\n").replace(",6\n", ",abc\n")
        with self.assertRaises(dataset.ValidationError):
            dataset.parse_csv(bad)

    def test_tolerates_few_bad_rows_and_other_date_formats(self):
        text = self._csv() + "\nnot-a-date,X1,3\n15/04/2026,X1,4"
        ds = dataset.parse_csv(text)
        self.assertTrue(any("skipped 1 invalid" in w for w in ds.warnings))
        self.assertEqual(ds.dates[-1].isoformat(), "2026-04-15")

    def test_stockout_detection_and_cleaning(self):
        q = [20.0] * 60
        q[40] = q[41] = 0.0
        flags = dataset.detect_stockouts(q)
        self.assertEqual([i for i, f in enumerate(flags) if f], [40, 41])
        clean = dataset.clean_series(q, flags)
        self.assertEqual(clean[40], 20.0)
        slow = [0.0, 1.0, 0.0, 2.0] * 15   # zeros are normal for a slow mover
        self.assertFalse(any(dataset.detect_stockouts(slow)))


if __name__ == "__main__":
    unittest.main()
