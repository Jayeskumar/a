import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import app  # noqa: E402
from pulseguard import evaluation  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def req(self, path, method="GET", body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None
                                            else None)
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                text = resp.read().decode()
                return resp.status, resp.headers.get("Content-Type"), text
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read().decode()

    def jreq(self, *a, **kw):
        status, _, text = self.req(*a, **kw)
        return status, json.loads(text)

    def test_health_and_ward(self):
        s, d = self.jreq("/api/health")
        self.assertEqual((s, d["status"]), (200, "ok"))
        s, d = self.jreq("/api/ward")
        self.assertEqual(s, 200)
        self.assertEqual(len(d["patients"]), 12)

    def test_news2_calculator(self):
        s, d = self.jreq("/api/news2", "POST", {"rr": 23, "spo2": 95, "sbp": 104, "hr": 112,
                                                "temp": 38.6, "acvpu": "A", "scale": 1})
        self.assertEqual(s, 200)
        self.assertEqual((d["total"], d["band"]), (7, "high"))
        s, d = self.jreq("/api/news2", "POST", {"rr": 500})
        self.assertEqual(s, 400)
        self.assertIn("rr", d["details"])
        s, d = self.jreq("/api/news2", "POST", raw=b"{not json")
        self.assertEqual(s, 400)
        s, d = self.jreq("/api/news2", "POST", raw=b"[1,2]")
        self.assertEqual(s, 400)

    def test_sim_controls_and_errors(self):
        s, d = self.jreq("/api/sim", "POST", {"action": "skip", "hours": 1})
        self.assertEqual(s, 200)
        s, d = self.jreq("/api/sim", "POST", {"action": "warp"})
        self.assertEqual(s, 400)
        s, d = self.jreq("/api/sim", "POST", {"action": "reset"})
        self.assertEqual(d["clock"]["step"], 8)

    def test_patient_endpoints(self):
        s, d = self.jreq("/api/patients/P01")
        self.assertEqual(s, 200)
        self.assertIn("breakdown", d)
        s, _ = self.jreq("/api/patients/ZZZ")
        self.assertEqual(s, 404)
        s, d = self.jreq("/api/patients/P10/observations", "POST",
                         {"rr": 18, "spo2": 97, "sbp": 130, "hr": 80, "temp": 37.0})
        self.assertEqual(s, 201)
        self.assertEqual(d["reading"]["source"], "manual")
        s, d = self.jreq("/api/patients/P10/observations", "POST", {"rr": 18})
        self.assertEqual(s, 400)

    def test_alerts_and_ack(self):
        s, d = self.jreq("/api/alerts")
        self.assertEqual(s, 200)
        aid = d["alerts"][0]["id"]
        s, d = self.jreq("/api/alerts/%d/ack" % aid, "POST", {"by": "Tester"})
        self.assertEqual(s, 200)
        self.assertTrue(d["alert"]["acknowledged"])
        s, _ = self.jreq("/api/alerts/424242/ack", "POST", {})
        self.assertEqual(s, 404)

    def test_handover_reference(self):
        s, d = self.jreq("/api/handover")
        self.assertEqual(s, 200)
        self.assertEqual(len(d["patients"]), 12)
        s, ctype, text = self.req("/api/handover?format=text")
        self.assertTrue(ctype.startswith("text/plain"))
        self.assertIn("Bed 1 -", text)
        s, d = self.jreq("/api/news2/reference")
        self.assertEqual(len(d["bands"]), 4)

    def test_static_and_errors(self):
        s, ctype, text = self.req("/")
        self.assertEqual(s, 200)
        self.assertIn("PulseGuard", text)
        self.assertTrue(ctype.startswith("text/html"))
        s, ctype, _ = self.req("/app.js")
        self.assertTrue(ctype.startswith("application/javascript"))
        self.assertEqual(self.req("/nope.html")[0], 404)
        self.assertEqual(self.req("/api/nope")[0], 404)
        self.assertEqual(self.req("/api/ward", "POST", {})[0], 405)
        self.assertEqual(self.req("/%2e%2e/app.py")[0], 404)


class TestEvaluation(unittest.TestCase):
    def test_small_evaluation(self):
        res = evaluation.evaluate(seeds=[1, 2, 3])
        self.assertEqual(res["deteriorating_episodes"], 9)
        self.assertGreaterEqual(res["lead_vs_threshold_h"]["min"], 0)
        self.assertGreater(res["lead_vs_manual_h"]["median"], 0)
        self.assertEqual(res["copd_scale2_red_readings"], 0)
        self.assertGreater(res["copd_scale1_red_readings"], 0)
        self.assertEqual(res["stable_only_threshold_medium_plus_alerts"], 0)
        self.assertLess(res["latency"]["news2_score_us"], 1000)
        demo = [r for r in res["demo_ward"] if r["kind"] == "deteriorating"]
        self.assertEqual(len(demo), 3)
        self.assertTrue(all(r["trend_fired_before_threshold"] for r in demo))


if __name__ == "__main__":
    unittest.main()
