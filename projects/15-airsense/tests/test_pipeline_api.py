"""End-to-end: deterministic data, measured model quality, and the HTTP API."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import app  # noqa: E402
from airsense import config as C  # noqa: E402
from airsense import simulate  # noqa: E402
from airsense.engine import Network  # noqa: E402
from airsense.mathx import dist  # noqa: E402

NET = None


def net():
    global NET
    if NET is None:
        NET = Network(app.DATA_DIR)
    return NET


class Determinism(unittest.TestCase):
    def test_generator_reproduces_committed_data(self):
        tmp = tempfile.mkdtemp(prefix="airsense-")
        try:
            simulate.write(tmp)
            for fname, _ in list(simulate.FILES.values()) + [("meta.json", None)]:
                with open(os.path.join(tmp, fname), "rb") as a, open(os.path.join(app.DATA_DIR, fname), "rb") as b:
                    self.assertEqual(a.read(), b.read(), fname)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PipelineQuality(unittest.TestCase):
    """Guards the numbers quoted in REPORT.md from silently regressing."""

    def test_shapes(self):
        n = net()
        self.assertEqual(n.n, C.FIELD_DAYS * 24)
        self.assertEqual(len(n.sensors), 25)
        self.assertEqual(len(n.refs), 2)
        self.assertEqual(n.nw, n.n + 24)

    def test_calibration_reduces_error(self):
        c = net().calibration_summary()
        self.assertGreater(c["pm25"]["rmse_reduction_pct"], 80)
        self.assertGreater(c["pm10"]["rmse_reduction_pct"], 70)
        self.assertLess(c["pm25"]["mean"]["hybrid"]["rmse"], c["pm25"]["mean"]["mlr"]["rmse"])
        self.assertLess(c["field_vs_truth_pm25"]["cal_mae"], 0.2 * c["field_vs_truth_pm25"]["raw_mae"])

    def test_fault_detection(self):
        ev = net().fault_eval
        self.assertEqual(ev["stuck"]["event_recall"], 1.0)
        self.assertGreaterEqual(ev["spike"]["event_recall"], 0.9)
        self.assertGreaterEqual(ev["drift"]["event_recall"], 2 / 3)
        self.assertGreaterEqual(ev["overall"]["event_precision"], 0.85)

    def test_forecast_beats_persistence(self):
        fe = net().fc_eval
        self.assertLess(fe["mae"]["model"], 0.8 * fe["mae"]["persistence"])
        self.assertLess(fe["mae"]["model"], fe["mae"]["seasonal"])
        self.assertTrue(60 <= fe["interval_coverage_80"] <= 95)

    def test_interpolation_beats_single_station(self):
        ip = net().interp_eval
        self.assertLess(ip["idw2"]["mae"], ip["nearest_ref"]["mae"])
        self.assertLess(ip["kriging"]["mae"], ip["nearest_ref"]["mae"])

    def test_industrial_cluster_located(self):
        hs = net().hotspots
        d = min(dist(h["x"], h["y"], C.INDUSTRY[0], C.INDUSTRY[1]) for h in hs)
        self.assertLess(d, 0.6)

    def test_festival_night_is_severe_in_centre(self):
        n = net()
        t = C.FESTIVAL_DAY * 24 + 22
        self.assertGreaterEqual(n.aqi1["S02"][t], 301)

    def test_estimate_and_forecast_views(self):
        n = net()
        e = n.estimate(5.0, 4.0, 100)
        self.assertLessEqual(e["aqi_lo"], e["aqi"])
        self.assertGreaterEqual(e["aqi_hi"], e["aqi"])
        fc = n.forecast_view(sid="S13", profile="asthma")
        self.assertEqual(len(fc["aqi"]), 24)
        self.assertIsNotNone(fc["best_run"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.NET = net()
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
        r = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"},
                                   method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get_json(self, path, body=None, raw=None):
        s, d = self.req(path, body, raw)
        return s, json.loads(d.decode())

    def test_static(self):
        s, d = self.req("/")
        self.assertEqual(s, 200)
        self.assertIn(b"AirSense", d)
        self.assertEqual(self.req("/app.js")[0], 200)
        self.assertEqual(self.req("/style.css")[0], 200)
        self.assertEqual(self.req("/../app.py")[0], 404)
        self.assertEqual(self.req("/nope.html")[0], 404)

    def test_get_endpoints(self):
        for p in ["/api/health", "/api/meta", "/api/frames", "/api/summary", "/api/summary?hour=5",
                  "/api/sensor?id=S07", "/api/estimate?x=5&y=4&hour=300", "/api/grid?hour=10&method=idw&nx=8&ny=6",
                  "/api/grid?hour=10&method=kriging&field=pm10&nx=8&ny=6", "/api/forecast?id=S13",
                  "/api/forecast?x=4&y=5&profile=children", "/api/faults", "/api/sources", "/api/evaluation",
                  "/api/advice?aqi=150&profile=asthma"]:
            s, j = self.get_json(p)
            self.assertEqual(s, 200, p)
            self.assertIsInstance(j, dict, p)
        s, j = self.get_json("/api/frames")
        self.assertEqual(len(j["pm25"]), C.FIELD_DAYS * 24)
        self.assertEqual(len(j["pm25"][0]), 25)
        s, j = self.get_json("/api/grid?hour=10&method=kriging&nx=8&ny=6")
        self.assertEqual(len(j["values"]), 6)
        self.assertEqual(len(j["sd"][0]), 8)

    def test_aqi_post(self):
        s, j = self.get_json("/api/aqi", {"pm25": 84, "pm10": 160, "no2": 92})
        self.assertEqual(s, 200)
        self.assertEqual(j["aqi"], 180)
        self.assertTrue(j["valid"])
        s, j = self.get_json("/api/aqi", {"pm25": [40] * 15 + [None] * 9, "pm10": 50, "no2": 20})
        self.assertEqual(s, 200)
        self.assertIn("pm25", j["insufficient"])
        self.assertFalse(j["valid"])          # PM2.5 had < 16 h, so only 2 pollutants remain
        s, j = self.get_json("/api/aqi", {"co": [1.0] * 10 + [5.0] * 8 + [1.0] * 6, "pm10": 80, "so2": 20})
        self.assertAlmostEqual(j["averaging"]["co"]["average"], 5.0)

    def test_z_demo_reset(self):
        s, j = self.get_json("/api/demo/reset", {})
        self.assertEqual(s, 200)
        self.assertEqual(j["status"], "ok")
        s, j = self.get_json("/api/health")
        self.assertEqual(j["hours"], C.FIELD_DAYS * 24)

    def test_errors(self):
        cases = [("/api/sensor", 400), ("/api/sensor?id=S99", 404), ("/api/estimate?x=5", 400),
                 ("/api/estimate?x=50&y=4", 400), ("/api/estimate?x=a&y=4", 400),
                 ("/api/summary?hour=99999", 400), ("/api/grid?method=magic", 400),
                 ("/api/forecast", 400), ("/api/forecast?id=S01&profile=astronaut", 400),
                 ("/api/advice", 400), ("/api/advice?aqi=900", 400), ("/api/nope", 404), ("/api/aqi", 405)]
        for path, code in cases:
            self.assertEqual(self.get_json(path)[0], code, path)
        self.assertEqual(self.get_json("/api/aqi", raw=b"{bad")[0], 400)
        self.assertEqual(self.get_json("/api/aqi", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.get_json("/api/aqi", {"pm25": -5})[0], 400)
        self.assertEqual(self.get_json("/api/aqi", {"lead": 1})[0], 400)
        self.assertEqual(self.get_json("/api/aqi", {"pm25": "abc"})[0], 400)
        self.assertEqual(self.get_json("/api/aqi", {"pm25": True})[0], 400)
        self.assertEqual(self.get_json("/api/aqi", {"pm25": [1] * 100})[0], 400)
        self.assertEqual(self.get_json("/api/demo/reset")[0], 405)
        self.assertEqual(self.get_json("/api/health", {"x": 1})[0], 405)
        self.assertEqual(self.get_json("/api/aqi", raw=b"x" * (app.MAX_BODY + 10))[0], 413)


if __name__ == "__main__":
    unittest.main()
