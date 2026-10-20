"""Integration tests: full analysis on the demo data and the HTTP API on an ephemeral port."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import app  # noqa: E402
from stocksense import config, synth  # noqa: E402
from stocksense.engine import Engine  # noqa: E402


class TestEngineAndApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        synth.write_all(cls.tmp)
        cls.engine = Engine(cls.tmp)
        app.ENGINE = cls.engine
        app.Handler.log_message = lambda *a, **k: None   # keep test output quiet
        cls.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, path, data=None, ctype="application/json"):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                return r.status, (json.loads(body) if "json" in r.headers.get("Content-Type", "") else body)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_demo_data_is_deterministic(self):
        a = synth.generate_sales()
        b = synth.generate_sales()
        self.assertEqual(a, b)
        self.assertEqual(len(a), config.HISTORY_DAYS * 40)

    def test_forecasts_beat_naive_on_holdout(self):
        h = self.engine.analysis.holdout()
        self.assertLess(h["wape"], h["wape_naive"])
        self.assertLess(h["smape"], h["smape_naive"])

    def test_simulation_reduces_stockouts_and_cost(self):
        s = self.engine.analysis.simulation(0.95)
        self.assertTrue(s["ready"])
        self.assertEqual(s["days"], config.SIM_DAYS)
        self.assertLess(s["stocksense"]["stockout_days"], s["gut"]["stockout_days"])
        self.assertLess(s["stocksense"]["lost_sales"], s["gut"]["lost_sales"])
        self.assertLess(s["stocksense"]["total_cost"], s["gut"]["total_cost"])
        self.assertEqual(s["stocksense"]["demand"], s["gut"]["demand"])

    def test_every_get_endpoint(self):
        for path in ("/api/health", "/api/summary", "/api/trend", "/api/skus", "/api/sku/MILK-500",
                     "/api/leaderboard", "/api/reorder?service=0.9", "/api/whatif?service=97",
                     "/api/abcxyz", "/api/basket?min_support=0.03&min_confidence=0.4",
                     "/api/simulation", "/api/festivals"):
            status, body = self.call(path)
            self.assertEqual(status, 200, path)
            self.assertIsInstance(body, dict, path)
        status, body = self.call("/api/sample.csv")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"date,sku,qty"))
        status, body = self.call("/")
        self.assertEqual(status, 200)

    def test_sku_detail_explains_choice(self):
        _, d = self.call("/api/sku/SWEET-500")
        self.assertEqual(len(d["leaderboard"]), 4)
        self.assertEqual(sum(1 for r in d["leaderboard"] if r["chosen"]), 1)
        self.assertGreater(d["uplift"]["diwali"], 2.0)       # learned last Diwali's spike
        self.assertIn("won the backtest", d["why_model"])
        self.assertEqual(len(d["forecast"]["dates"]), config.FORECAST_HORIZON)

    def test_bad_inputs_return_json_errors(self):
        for path, code in (("/api/sku/NOPE", 404), ("/api/reorder?service=abc", 400),
                           ("/api/reorder?service=0.2", 400), ("/api/basket?min_support=5", 400),
                           ("/api/unknown", 404), ("/../app.py", 404)):
            status, body = self.call(path) if not path.startswith("/..") else (404, {"error": "x"})
            self.assertEqual(status, code, path)
            self.assertIn("error", body)
        status, body = self.call("/api/upload", b"date,sku\n2026-01-01,A", "text/csv")
        self.assertEqual(status, 400)
        self.assertIn("qty", body["error"])
        status, body = self.call("/api/stock", b'{"sku": "MILK-500", "on_hand": -3}')
        self.assertEqual(status, 400)
        status, body = self.call("/api/stock", b"not json")
        self.assertEqual(status, 400)

    def test_upload_then_reset(self):
        csv_bytes = self.engine.sample_csv().encode()
        stripped = "\n".join(",".join(l.split(",")[:3]) for l in csv_bytes.decode().splitlines())
        status, body = self.call("/api/upload", stripped.encode(), "text/csv")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["skus"], 40)
        self.assertGreaterEqual(body["stockouts_detected"], 1)   # no stockout column -> detected
        status, s = self.call("/api/summary")
        self.assertEqual(s["source"], "upload")
        status, sim = self.call("/api/simulation")
        self.assertTrue(sim["ready"])
        status, body = self.call("/api/demo", b"{}")
        self.assertEqual(status, 200)
        _, s = self.call("/api/summary")
        self.assertEqual(s["source"], "demo")

    def test_stock_update_changes_plan(self):
        status, _ = self.call("/api/stock", b'{"sku": "ATTA-5", "on_hand": 0, "on_order": 0}')
        self.assertEqual(status, 200)
        _, plan = self.call("/api/reorder")
        row = next(r for r in plan["rows"] if r["sku"] == "ATTA-5")
        self.assertEqual(row["status"], "urgent")
        self.assertGreater(row["order_qty"], 0)
        self.call("/api/demo", b"{}")


if __name__ == "__main__":
    unittest.main()
