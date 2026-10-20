import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logsentinel import generator, evaluation
from logsentinel.parsers import parse_text
from logsentinel.engine import Analysis


class TestEndToEnd(unittest.TestCase):
    def test_generator_deterministic(self):
        a = generator.generate().text()
        b = generator.generate().text()
        self.assertEqual(a, b)

    def test_only_reserved_ips(self):
        import re
        gt = generator.generate().ground_truth()
        for ip in gt["attacker_ips"]:
            self.assertTrue(ip.startswith(("203.0.113.", "198.51.100.", "192.0.2.", "10.")),
                            ip)

    def test_full_pipeline_detects_each_attack(self):
        result = evaluation.evaluate()
        # every labelled attack type is detected
        for atype, d in result["per_type"].items():
            self.assertEqual(d["detected"], d["labels"],
                             "missed %s (%d/%d)" % (atype, d["detected"], d["labels"]))
        self.assertGreaterEqual(result["recall"], 0.99)

    def test_no_benign_false_positives(self):
        result = evaluation.evaluate()
        self.assertEqual(result["benign_false_positives"], 0, result["benign_fp_detail"])

    def test_precision_high(self):
        result = evaluation.evaluate()
        self.assertEqual(result["false_positive_alerts"], 0)

    def test_incidents_built(self):
        g = generator.generate()
        events, stats = parse_text(g.text())
        an = Analysis(events, stats)
        self.assertGreater(len(an.incidents), 0)
        # the credential-stuffing IP should become one multi-phase incident
        stuff = [i for i in an.incidents if i["src"] == "192.0.2.77"][0]
        self.assertGreaterEqual(len(stuff["phases"]), 2)
        self.assertGreaterEqual(stuff["alert_count"], 2)

    def test_blocklist_only_attackers(self):
        g = generator.generate()
        events, stats = parse_text(g.text())
        an = Analysis(events, stats)
        block_ips = {r["ip"] for r in an.blocklist()}
        gt = g.ground_truth()
        self.assertTrue(block_ips.issubset(set(gt["attacker_ips"])))


if __name__ == "__main__":
    unittest.main()
