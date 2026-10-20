import json
import os
import threading
import unittest
import urllib.error
import urllib.request

import _path  # noqa: F401
os.environ["AGRISKY_QUIET"] = "1"
import app  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = app.make_server("127.0.0.1", 0)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, raw=None, method=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, resp.read(), resp.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type")

    def jreq(self, path, body=None, **kw):
        code, data, _ = self.req(path, body, **kw)
        return code, json.loads(data.decode("utf-8"))

    def test_static(self):
        for p, ct in (("/", "text/html"), ("/app.js", "javascript"), ("/style.css", "text/css"),
                      ("/report.html", "text/html"), ("/favicon.svg", "svg")):
            code, data, ctype = self.req(p)
            self.assertEqual(code, 200, p)
            self.assertIn(ct, ctype)
        code, _, _ = self.req("/../app.py")
        self.assertEqual(code, 404)
        code, _, _ = self.req("/nope.html")
        self.assertEqual(code, 404)

    def test_health_meta(self):
        code, d = self.jreq("/api/health")
        self.assertEqual((code, d["status"]), (200, "ok"))
        code, d = self.jreq("/api/meta")
        self.assertEqual(code, 200)
        self.assertEqual(len(d["classes"]), 6)
        self.assertEqual(len(d["flights"]), 5)

    def test_scene(self):
        code, d = self.jreq("/api/scene?flight=5")
        self.assertEqual(code, 200)
        self.assertEqual(d["flight_no"], 5)
        for k in ("ndvi", "ndre", "gndvi", "savi", "ndwi", "nir", "truth", "zone", "cls", "dndvi",
                  "rx_pesticide", "rx_urea"):
            self.assertEqual(len(d["layers"][k]), 9600, k)
        self.assertEqual(d["change"]["spread"]["alert"]["level"], "red")
        self.assertGreater(d["accuracy"]["accuracy"], 0.97)
        self.assertEqual(d["mission"]["vra"]["totals"]["missed"], 0)
        code, d1 = self.jreq("/api/scene?flight=1")
        self.assertIsNone(d1["layers"]["dndvi"])

    def test_field_zones_change(self):
        code, d = self.jreq("/api/field?flight=2")
        self.assertEqual(code, 200)
        self.assertEqual(len(d["layers"]["ndvi"]), 9600)
        code, d = self.jreq("/api/zones?flight=3&k=4")
        self.assertEqual(code, 200)
        self.assertEqual(d["k"], 4)
        self.assertEqual(len(d["zone_grid"]), 9600)
        code, d = self.jreq("/api/change?flight=5&base=2")
        self.assertEqual(code, 200)
        self.assertEqual(d["base"], 2)
        self.assertTrue(d["diff"]["hotspots"])

    def test_prescription_and_mission(self):
        code, d = self.jreq("/api/prescription?flight=5&product=urea")
        self.assertEqual(code, 200)
        self.assertGreater(d["savings"]["pct"], 50)
        code, d = self.jreq("/api/mission?flight=5&plan=uniform")
        self.assertEqual(code, 200)
        self.assertEqual(d["totals"]["covered_multi"], 0)
        code, d = self.jreq("/api/mission", {"flight": 5, "tank": 0.5, "swath": 3})
        self.assertEqual(code, 200)
        self.assertGreater(d["totals"]["sorties"], 1)
        for s in d["sorties"]:
            self.assertLessEqual(s["payload"], 0.5 + 1e-9)

    def test_report_exports_indices(self):
        code, d = self.jreq("/api/report?flight=5")
        self.assertEqual(code, 200)
        self.assertTrue(d["report"]["lines"])
        code, data, ctype = self.req("/api/export/prescription.csv?flight=5")
        self.assertEqual(code, 200)
        self.assertIn("text/csv", ctype)
        self.assertTrue(data.decode().startswith("zone_id,class"))
        code, data, ctype = self.req("/api/export/prescription.geojson?flight=5&download=1")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(data)["type"], "FeatureCollection")
        code, d = self.jreq("/api/indices", {"green": 0.1, "red": 0.05, "rededge": 0.25, "nir": 0.5})
        self.assertEqual(code, 200)
        self.assertAlmostEqual(d["indices"]["ndvi"], 0.8182, places=4)
        code, d = self.jreq("/api/metrics")
        self.assertEqual(code, 200)
        self.assertIn("available", d)

    def test_errors(self):
        for path in ("/api/scene?flight=9", "/api/scene?seed=abc", "/api/zones?k=1",
                     "/api/prescription?product=gold", "/api/mission?plan=x",
                     "/api/mission?swath=0", "/api/change?flight=3&base=4",
                     "/api/mission?flight=5&plan=uniform&endurance=60"):
            code, d = self.jreq(path)
            self.assertEqual(code, 400, path)
            self.assertIn("error", d)
        self.assertEqual(self.jreq("/api/nope")[0], 404)
        self.assertEqual(self.jreq("/api/health", method="POST", raw=b"{}")[0], 405)
        self.assertEqual(self.jreq("/api/indices")[0], 405)
        self.assertEqual(self.jreq("/api/mission", raw=b"{bad")[0], 400)
        self.assertEqual(self.jreq("/api/mission", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.jreq("/api/indices", {"red": 0.1})[0], 400)
        self.assertEqual(self.jreq("/api/indices", {"green": 2, "red": 0.1, "nir": 0.3})[0], 400)
        code, _, _ = self.req("/api/mission", raw=b"x" * (app.MAX_BODY + 1))
        self.assertEqual(code, 413)
        # server still alive
        self.assertEqual(self.jreq("/api/health")[0], 200)


if __name__ == "__main__":
    unittest.main()
