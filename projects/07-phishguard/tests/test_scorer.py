import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phishguard import config, corpus, samples  # noqa: E402
from phishguard.scorer import PhishGuard, build_segments, calibrate, combine, verdict, looks_like_single_url  # noqa: E402

ENGINE = PhishGuard()


class CombineTest(unittest.TestCase):
    def test_noisy_or(self):
        self.assertAlmostEqual(combine([0.5, 0.5]), 0.75)
        self.assertAlmostEqual(combine([0.0, 0.0]), 0.0)
        self.assertAlmostEqual(combine([1.0, 0.2]), 1.0)
        self.assertAlmostEqual(combine([0.3]), 0.3)
        self.assertAlmostEqual(combine([1.7, -2]), 1.0)  # clamped

    def test_verdict_thresholds(self):
        self.assertEqual(verdict(config.SAFE_BELOW - 1), "Safe")
        self.assertEqual(verdict(config.SAFE_BELOW), "Suspicious")
        self.assertEqual(verdict(config.DANGEROUS_FROM - 1), "Suspicious")
        self.assertEqual(verdict(config.DANGEROUS_FROM), "Dangerous")

    def test_calibration_prior(self):
        self.assertAlmostEqual(calibrate(0.0), config.NB_DEPLOY_PRIOR)
        self.assertGreater(calibrate(60), 0.95)
        self.assertLess(calibrate(-30), 0.01)

    def test_segments_cover_text_without_overlap(self):
        text = "Pay fee to x@ybl now"
        spans = [(1, 0, 7, "rule", "fee"), (0, 4, 7, "rule", "strong"), (2, 11, 16, "upi", "upi")]
        segs = build_segments(text, spans)
        self.assertEqual("".join(s["text"] for s in segs), text)
        kinds = [(s["text"], s.get("label")) for s in segs]
        self.assertIn(("fee", "strong"), kinds)  # lower priority number wins the overlap
        self.assertIn(("Pay ", "fee"), kinds)

    def test_single_url_detection(self):
        self.assertTrue(looks_like_single_url("bit.ly/abc"))
        self.assertTrue(looks_like_single_url("  https://www.irctc.co.in/nget  "))
        self.assertFalse(looks_like_single_url("click bit.ly/abc"))
        self.assertFalse(looks_like_single_url("hello"))


class EngineTest(unittest.TestCase):
    def test_scam_message_is_dangerous_with_explanation(self):
        r = ENGINE.analyse(samples.DEMO_SAMPLES[0]["text"])
        self.assertEqual(r["verdict"], "Dangerous")
        self.assertEqual(r["mode"], "message")
        ids = {x["id"] for x in r["rules"]}
        self.assertIn("kyc_update", ids)
        self.assertTrue(r["nb"]["scam_tokens"])
        self.assertEqual(len(r["entities"]["urls"]), 1)
        self.assertGreater(r["entities"]["urls"][0]["risk"], 80)
        self.assertTrue(any(s.get("kind") == "rule" for s in r["segments"]))
        self.assertTrue(any("1930" in a for a in r["advice"]))
        self.assertEqual("".join(s["text"] for s in r["segments"]), samples.DEMO_SAMPLES[0]["text"])

    def test_safe_messages(self):
        for sid in ("otp", "friend", "official"):
            text = [s for s in samples.DEMO_SAMPLES if s["id"] == sid][0]["text"]
            self.assertEqual(ENGINE.analyse(text)["verdict"], "Safe", text)

    def test_url_mode(self):
        r = ENGINE.analyse("http://www.onlinesbi.sbi@185.22.14.7/retail/login.php")
        self.assertEqual(r["mode"], "url")
        self.assertEqual(r["verdict"], "Dangerous")
        feats = {x["feature"] for x in r["entities"]["urls"][0]["reasons"]}
        self.assertTrue({"has_at", "ip_host"} & feats)
        self.assertEqual(ENGINE.analyse("https://www.irctc.co.in/nget/train-search")["verdict"], "Safe")

    def test_quiz_answers_match_model(self):
        for q in samples.QUIZ:
            v = ENGINE.analyse(q["text"])["verdict"]
            self.assertEqual(v != "Safe", q["answer"] == "scam", q["text"])

    def test_components_reproduce_risk(self):
        r = ENGINE.analyse(samples.DEMO_SAMPLES[1]["text"])
        self.assertAlmostEqual(combine([c["value"] for c in r["components"]]) * 100, r["risk"], delta=0.6)

    def test_bulk(self):
        out = ENGINE.bulk(samples.BULK_DEMO + ["", "   "])
        self.assertEqual(out["count"], len(samples.BULK_DEMO))
        self.assertEqual(sum(out["summary"].values()), out["count"])
        self.assertTrue(all(r["reason"] for r in out["rows"]))

    def test_stats_are_sane(self):
        s = ENGINE.stats()
        self.assertGreaterEqual(s["message_combined"]["accuracy"], 0.9)
        self.assertGreaterEqual(s["url_lr"]["accuracy"], 0.85)
        self.assertGreaterEqual(s["heldout_templates"]["combined"]["accuracy"], 0.85)
        c = s["message_nb"]["confusion"]
        self.assertEqual(sum(c.values()), s["dataset"]["messages_test"])


class CorpusTest(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(corpus.generate_messages()[:50], corpus.generate_messages()[:50])
        self.assertEqual(corpus.generate_urls(), corpus.generate_urls())

    def test_size_balance_and_dedup(self):
        m = corpus.generate_messages()
        self.assertGreaterEqual(len(m), 600)
        self.assertEqual(len({x["text"] for x in m}), len(m))
        self.assertEqual(sum(x["label"] for x in m), len(m) // 2)
        u = corpus.generate_urls()
        self.assertGreaterEqual(len(u), 300)
        self.assertEqual(len({x["url"] for x in u}), len(u))

    def test_splits_are_clean(self):
        m = corpus.generate_messages()
        train, test = corpus.split(m)
        self.assertEqual(len(train) + len(test), len(m))
        self.assertFalse({x["text"] for x in train} & {x["text"] for x in test})
        self.assertAlmostEqual(sum(x["label"] for x in test) / len(test), 0.5, delta=0.02)
        tr, te = corpus.template_split(m)
        self.assertFalse({x["template"] for x in tr} & {x["template"] for x in te})
        self.assertEqual({x["label"] for x in te}, {0, 1})


if __name__ == "__main__":
    unittest.main()
