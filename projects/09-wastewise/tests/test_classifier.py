import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wastewise import classifier as K  # noqa: E402


class ClassifierTest(unittest.TestCase):
    def test_known_items(self):
        cases = {
            "banana peel": "wet", "plastic bottle": "recyclable", "தேங்காய் ஓடு": "wet",
            "battery": "hazardous", "chips packet": "dry", "பால் பாக்கெட்": "recyclable",
            "sanitary napkin": "dry", "tube light": "hazardous", "newspaper": "recyclable",
            "மீன் கழிவு": "wet", "thengai odu": "wet",
        }
        for item, want in cases.items():
            r = K.classify(item)
            self.assertEqual(r["label"], want, item)
            self.assertEqual(r["method"], "exact-match")

    def test_unseen_variants_generalise(self):
        cases = {
            "Banana Peels!": "wet", "bundle of old newspaper": "recyclable", "plastic water bottles": "recyclable",
            "rotten tomato": "wet", "used diapers": "dry", "mobile charger": "hazardous",
            "தேங்காய் ஓட்டை": "wet", "broken glass bottle": "recyclable", "expired tablets": "hazardous",
        }
        for item, want in cases.items():
            r = K.classify(item)
            self.assertEqual(r["label"], want, item)
            self.assertEqual(r["method"], "naive-bayes")
            self.assertTrue(r["evidence"], item)

    def test_probabilities_are_a_distribution(self):
        r = K.classify("egg shells and tea powder")
        self.assertAlmostEqual(sum(r["probabilities"].values()), 1.0, places=2)
        self.assertEqual(set(r["probabilities"]), set(K.LABELS))
        self.assertGreaterEqual(r["confidence"], max(r["probabilities"].values()) - 1e-9)

    def test_gibberish_is_flagged_unsure(self):
        r = K.classify("qwzx plmk")
        self.assertTrue(r["unsure"])

    def test_tamil_tokenisation_keeps_words_whole(self):
        self.assertEqual(K.words("வாழைப்பழத் தோல்"), ["வாழைப்பழத்", "தோல்"])
        self.assertEqual(K.normalise("  Plastic-Bottle, (big) "), "plastic bottle big")

    def test_holdout_accuracy(self):
        ev = K.evaluate()
        self.assertGreaterEqual(ev["accuracy"], 0.70)
        train, test = K.holdout_split()
        self.assertFalse(set(t for t, _ in test) & set(t for t, _ in train))

    def test_dataset_labels_valid(self):
        for t, y in K.DATA + K.LEXICON:
            self.assertIn(y, K.LABELS, t)


if __name__ == "__main__":
    unittest.main()
