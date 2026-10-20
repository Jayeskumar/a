import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civiclens import config as C  # noqa: E402
from civiclens import datagen as G  # noqa: E402
from civiclens.engine import Engine  # noqa: E402


class TestDatagen(unittest.TestCase):
    def test_deterministic_and_plausible(self):
        a, b = G.generate(), G.generate()
        self.assertEqual([c["text"] for c in a["complaints"]], [c["text"] for c in b["complaints"]])
        cs = a["complaints"]
        self.assertTrue(2700 <= len(cs) <= 3300, len(cs))
        self.assertEqual({c["dept"] for c in cs}, set(C.DEPT_CODES))
        self.assertEqual({c["lang"] for c in cs}, {"en", "ta", "tg"})
        self.assertEqual({c["urgency"] for c in cs}, {1, 2, 3, 4})
        self.assertLess(len({c["incident"] for c in cs}), len(cs))          # duplicates exist
        self.assertEqual(sorted(t for t in (c["t"] for c in cs)), [c["t"] for c in cs])
        self.assertTrue(all(c["t"] < a["now_t"] for c in cs))
        self.assertEqual(len(a["planted"]), 9)
        self.assertNotEqual(G.generate(seed=99)["complaints"][0]["text"], cs[0]["text"])

    def test_geometry_round_trip(self):
        for i in (1, 7, 20):
            x0, y0, x1, y1 = G.ward_bounds_m(i)
            self.assertEqual(G.ward_of_xy((x0 + x1) / 2, (y0 + y1) / 2), i)
        la, lo = G.to_latlon(1234.0, 2345.0)
        x, y = G.to_xy(la, lo)
        self.assertAlmostEqual(x, 1234.0, delta=1.0)
        self.assertAlmostEqual(y, 2345.0, delta=1.0)


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.E = Engine(data_dir=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_measured_quality_floors(self):
        m = self.E.models()
        self.assertGreater(m["routing"]["models"]["lr"]["accuracy"], 0.88)
        self.assertGreater(m["routing"]["models"]["nb"]["accuracy"], 0.85)
        self.assertGreater(m["urgency"]["variants"]["combined"]["p1_recall"], 0.7)
        self.assertGreater(m["duplicates"]["pairwise"]["f1"], 0.7)
        self.assertGreater(m["duplicates"]["pairwise"]["f1"], m["duplicates"]["text_only_baseline"]["f1"])
        self.assertGreaterEqual(m["hotspots"]["persistent_recall"], 0.8)
        self.assertGreaterEqual(len(m["emerging"]["surges_detected"]), 2)
        self.assertGreater(m["breach"]["auc"], 0.65)

    def test_live_wire_is_p1_and_routed(self):
        r = self.E.analyze("Live wire hanging near Murugan temple, very dangerous", 11.375, 77.89)
        self.assertEqual(r["routing"]["dept"], "STREETLIGHT")
        self.assertEqual(r["urgency"]["priority"], 1)
        self.assertIn("forces P1", r["urgency"]["reason"])
        self.assertEqual(len(r["urgency"]["probs"]), 4)
        self.assertTrue(r["routing"]["tokens"])

    def test_tamil_routing(self):
        r = self.E.analyze("காந்தி தெருவில் குப்பை அள்ளவில்லை, துர்நாற்றம்", 11.38, 77.885)
        self.assertEqual(r["routing"]["dept"], "SANITATION")
        self.assertEqual(r["lang"], "ta")

    def test_demo_duplicate_sample_is_detected(self):
        s = next(x for x in self.E.demo_samples() if x.get("expect_dup_of"))
        r = self.E.analyze(s["text"], s["lat"], s["lon"], s["channel"])
        self.assertTrue(r["duplicate"]["is_duplicate"])
        self.assertEqual(r["duplicate"]["root"], self.E.get(s["expect_dup_of"])["root"])

    def test_filing_then_reset(self):
        E = self.E
        n_live = len(E.live)
        a = E.analyze("Open manhole near Valluvar school, very dangerous", 11.37, 77.90, record=True)
        b = E.analyze("Manhole cover missing near Valluvar school", 11.3701, 77.9001, record=True)
        self.assertEqual(len(E.live), n_live + 2)
        self.assertEqual(b["duplicate"]["of"], a["id"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "filed_complaints.json")))
        self.assertEqual(E.queue(limit=1)[0]["id"], b["id"])
        E.reset_live()
        self.assertEqual(E.live, [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "filed_complaints.json")))

    def test_views(self):
        E = self.E
        self.assertEqual(len(E.sla()["departments"]), len(C.DEPT_CODES))
        self.assertEqual(len(E.wards_ranking()), 20)
        hg = E.heatgrid("DRAINAGE")
        self.assertEqual(len(hg["rows"]), 20)
        self.assertEqual(len(hg["rows"][0]["counts"]), C.N_WEEKS)
        t = E.topics()
        self.assertTrue(t["clusters"])
        self.assertGreater(t["purity"], 0.7)
        ar = E.at_risk(5)
        self.assertLessEqual(len(ar["at_risk"]), 5)
        if len(ar["at_risk"]) > 1:
            self.assertGreaterEqual(ar["at_risk"][0]["breach_risk"], ar["at_risk"][1]["breach_risk"])


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        app.Handler.log_message = lambda *a: None          # keep test output quiet
        cls.tmp = tempfile.mkdtemp()
        app.ENGINE = TestEngine.E if hasattr(TestEngine, "E") else Engine(data_dir=cls.tmp)
        cls.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, path, body=None, method=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_get_endpoints(self):
        for p in ("/api/health", "/api/summary", "/api/town", "/api/queue?limit=3", "/api/map?dept=ROADS",
                  "/api/hotspots", "/api/heatgrid", "/api/emerging?week=11", "/api/sla", "/api/at-risk",
                  "/api/wards", "/api/models", "/api/topics?k=5", "/api/demo/samples", "/api/complaint/C-10001"):
            code, _ = self.call(p)
            self.assertEqual(code, 200, p)
        code, raw = self.call("/api/complaints.csv")
        self.assertEqual(code, 200)
        self.assertIn(b"id,ts,text", raw[:20])
        code, html = self.call("/")
        self.assertEqual(code, 200)

    def test_analyze_and_errors(self):
        code, r = self.call("/api/analyze", {"text": "drainage overflow ah iruku near bus stand", "ward": "W07"})
        self.assertEqual(code, 200)
        self.assertEqual(r["routing"]["dept"], "DRAINAGE")
        self.assertEqual(self.call("/api/analyze", {"text": ""})[0], 400)
        self.assertEqual(self.call("/api/analyze", {"text": "x", "lat": "a", "lon": 1})[0], 400)
        self.assertEqual(self.call("/api/analyze", {"text": "x", "lat": 13.0, "lon": 80.2})[0], 400)
        self.assertEqual(self.call("/api/analyze", {"text": "x" * 2000})[0], 400)
        self.assertEqual(self.call("/api/analyze", {"text": "pothole", "channel": "Fax"})[0], 400)
        self.assertEqual(self.call("/api/queue?dept=MOON")[0], 400)
        self.assertEqual(self.call("/api/hotspots?eps=1")[0], 400)
        self.assertEqual(self.call("/api/complaint/C-00000")[0], 404)
        self.assertEqual(self.call("/api/nope")[0], 404)
        self.assertEqual(self.call("/api/demo/reset")[0], 405)
        self.assertEqual(self.call("/../app.py")[0], 404)
        req = urllib.request.Request("http://127.0.0.1:%d/api/analyze" % self.port, data=b"{not json", method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
