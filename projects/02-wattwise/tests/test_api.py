import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import app  # noqa: E402
from wattwise.engine import Campus  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.CAMPUS = Campus(app.DATA_DIR)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data,
                                   headers={"Content-Type": "application/json"},
                                   method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get_json(self, path, body=None, raw=None):
        status, data = self.req(path, body, raw)
        return status, json.loads(data.decode())

    def test_static(self):
        s, d = self.req("/")
        self.assertEqual(s, 200)
        self.assertIn(b"WattWise", d)
        self.assertEqual(self.req("/app.js")[0], 200)
        self.assertEqual(self.req("/../app.py")[0], 404)

    def test_get_endpoints(self):
        for p in ["/api/health", "/api/overview", "/api/buildings", "/api/series?building=cse_lab",
                  "/api/forecast?building=admin", "/api/heatmap?building=library",
                  "/api/anomalies", "/api/anomalies?building=canteen", "/api/leaderboard",
                  "/api/evaluation"]:
            s, j = self.get_json(p)
            self.assertEqual(s, 200, p)
            self.assertIsInstance(j, dict)
        s, j = self.get_json("/api/series?building=cse_lab&days=7")
        self.assertEqual(len(j["actual"]["kwh"]), 168)
        self.assertEqual(len(j["forecast"]["kwh"]), 168)

    def test_errors(self):
        self.assertEqual(self.get_json("/api/series")[0], 400)
        self.assertEqual(self.get_json("/api/series?building=zzz")[0], 404)
        self.assertEqual(self.get_json("/api/series?building=admin&days=0")[0], 400)
        self.assertEqual(self.get_json("/api/nope")[0], 404)
        self.assertEqual(self.get_json("/api/solar")[0], 405)
        self.assertEqual(self.get_json("/api/solar", raw=b"{bad")[0], 400)
        self.assertEqual(self.get_json("/api/solar", raw=b"[1]")[0], 400)
        self.assertEqual(self.get_json("/api/solar", {"roof_area_m2": -3, "monthly_kwh": 9})[0], 400)
        self.assertEqual(self.get_json("/api/whatif", {"led_pct": 500})[0], 400)
        self.assertEqual(self.get_json("/api/solar", {"building": "nope"})[0], 404)

    def test_post_endpoints(self):
        s, j = self.get_json("/api/solar", {"roof_area_m2": 500, "monthly_bill_inr": 100000})
        self.assertEqual(s, 200)
        self.assertGreater(j["kwp"], 0)
        s, j = self.get_json("/api/solar", {"building": "campus"})
        self.assertEqual(s, 200)
        s, j = self.get_json("/api/whatif", {"ac_setpoint_delta": 1, "auto_off": True, "led_pct": 50})
        self.assertEqual(s, 200)
        self.assertGreater(j["monthly_saving_kwh"], 0)
        s, j = self.get_json("/api/demo/reset", {})
        self.assertEqual(s, 200)
        self.assertEqual(j["status"], "ok")


if __name__ == "__main__":
    unittest.main()
