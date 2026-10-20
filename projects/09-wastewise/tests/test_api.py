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


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wastewise-test-")
        cls.httpd = app.make_server("127.0.0.1", 0, data_dir=cls.tmp)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_get_endpoints(self):
        for p in ("/api/health", "/api/town", "/api/state", "/api/plan", "/api/forecast?bin=B01",
                  "/api/leaderboard", "/api/impact?diesel=95&bins=400&kmpl=4.5",
                  "/api/classify?item=banana%20peel", "/api/simulate?days=10"):
            code, data = self.req(p)
            self.assertEqual(code, 200, p)
            self.assertIsInstance(data, dict)
        code, plan = self.req("/api/plan")
        self.assertIn("savings", plan)
        self.assertGreater(plan["savings"]["km"], 0)

    def test_static(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            self.assertIn(b"WasteWise", r.read())

    def test_errors(self):
        self.assertEqual(self.req("/api/forecast")[0], 400)
        self.assertEqual(self.req("/api/forecast?bin=B99")[0], 404)
        self.assertEqual(self.req("/api/impact?diesel=abc")[0], 400)
        self.assertEqual(self.req("/api/nope")[0], 404)
        self.assertEqual(self.req("/api/report")[0], 405)
        self.assertEqual(self.req("/api/report", raw=b"{not json")[0], 400)
        self.assertEqual(self.req("/api/report", body=[1, 2])[0], 400)
        self.assertEqual(self.req("/api/report", body={"ward": "W9", "item": "x", "bin_used": "wet"})[0], 400)
        self.assertEqual(self.req("/api/sim/advance", body={"days": 0})[0], 400)
        self.assertEqual(self.req("/api/sim/advance", body={"days": "3"})[0], 400)
        self.assertEqual(self.req("/api/classify", body={"item": ""})[0], 400)

    def test_report_and_simulation_flow(self):
        code, r = self.req("/api/report", body={"ward": "W3", "household": "W3-001",
                                                 "item": "plastic bottle", "bin_used": "recyclable"})
        self.assertEqual(code, 200)
        self.assertTrue(r["report"]["correct"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "reports.json")))
        code, r = self.req("/api/sim/advance", body={"days": 2})
        self.assertEqual(code, 200)
        self.assertEqual(r["state"]["today"]["day"], 2)
        code, r = self.req("/api/demo", body={})
        self.assertEqual(code, 200)
        self.assertEqual(r["state"]["today"]["day"], 0)


if __name__ == "__main__":
    unittest.main()
