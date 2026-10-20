import datetime as dt
import json
import os
import threading
import unittest
import urllib.error
import urllib.request

import _path  # noqa: F401
os.environ["KM_QUIET"] = "1"
import app  # noqa: E402
from krishimitra import config  # noqa: E402


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
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read(), resp.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type")

    def jreq(self, path, body=None, **kw):
        code, data, _ = self.req(path, body, **kw)
        return code, json.loads(data.decode("utf-8"))

    def preset_body(self, p):
        b = dict(p["inputs"])
        b.update(lat=p["lat"], soil=p["soil"], method=p["method"], area_acres=p["area_acres"],
                 sowing_date=(dt.date.today() - dt.timedelta(days=p["sowing_days_ago"])).isoformat())
        return b

    def test_static(self):
        code, data, ctype = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"KrishiMitra", data)
        for f in ("/app.js", "/style.css", "/i18n.js"):
            self.assertEqual(self.req(f)[0], 200)
        self.assertEqual(self.req("/../app.py")[0], 404)
        self.assertEqual(self.req("/nope.html")[0], 404)

    def test_get_endpoints(self):
        for path in ("/api/health", "/api/meta", "/api/presets", "/api/model",
                     "/api/market?crop=turmeric&date=2026-10-20",
                     "/api/calendar?crop=rice&sowing_date=2026-09-15",
                     "/api/et0?lat=-20&doy=246&tmin=22&tmax=34", "/api/forecast?lat=11.4"):
            code, j = self.jreq(path)
            self.assertEqual(code, 200, path)
        code, j = self.jreq("/api/et0?lat=-20&doy=246&tmin=22&tmax=34")
        self.assertAlmostEqual(j["ra_mj_m2_day"], 32.2, places=1)
        code, j = self.jreq("/api/meta")
        self.assertEqual(len(j["crops"]), 14)
        self.assertGreater(j["metrics"]["rf_accuracy"], 0.85)

    def test_presets_recommend_expected_crops(self):
        expected = {"namakkal": "groundnut", "delta": "rice", "erode": "turmeric", "dharmapuri": "ragi"}
        for p in config.PRESETS:
            code, j = self.jreq("/api/advise", self.preset_body(p))
            self.assertEqual(code, 200)
            self.assertEqual(j["crop"], expected[p["id"]])
            self.assertEqual(len(j["recommendation"]["top3"]), 3)
            self.assertEqual(len(j["irrigation"]["days"]), 7)
            self.assertTrue(j["speech"]["ta"])

    def test_post_endpoints(self):
        p = config.PRESETS[1]
        code, j = self.jreq("/api/recommend", p["inputs"])
        self.assertEqual(code, 200)
        self.assertAlmostEqual(sum(1 for _ in j["explanation"]["features"]), 7)
        b = dict(p["inputs"], crop="rice", area_acres=3)
        code, j = self.jreq("/api/fertiliser", b)
        self.assertEqual(code, 200)
        b = {"crop": "rice", "lat": 10.79, "sowing_date": "2026-09-15", "start_date": "2026-10-20",
             "soil": "alluvial", "method": "flood",
             "forecast": [{"tmax": 33, "tmin": 24, "rain": 0}] * 5}
        code, j = self.jreq("/api/irrigation", b)
        self.assertEqual(code, 200)
        self.assertEqual(j["forecast_source"], "user")
        self.assertEqual(len(j["days"]), 5)
        b = dict(self.preset_body(p), crop="coconut")
        code, j = self.jreq("/api/advise", b)
        self.assertEqual(j["crop"], "coconut")

    def test_bad_inputs(self):
        good = dict(config.PRESETS[0]["inputs"])
        cases = [
            ("/api/recommend", dict(good, N="lots")),
            ("/api/recommend", dict(good, ph=14)),
            ("/api/recommend", {k: v for k, v in good.items() if k != "K"}),
            ("/api/advise", dict(good, crop="wheatgrass")),
            ("/api/advise", dict(good, soil="moon")),
            ("/api/advise", dict(good, sowing_date="yesterday")),
            ("/api/advise", dict(good, forecast="sunny")),
            ("/api/fertiliser", dict(good)),
            ("/api/irrigation", {"crop": "rice", "forecast": [{"tmax": "hot", "tmin": 20}]}),
        ]
        for path, body in cases:
            code, j = self.jreq(path, body)
            self.assertEqual(code, 400, (path, body))
            self.assertIn("error", j)
        self.assertEqual(self.jreq("/api/advise", raw=b"{not json")[0], 400)
        self.assertEqual(self.jreq("/api/advise", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.jreq("/api/market?crop=gold")[0], 400)
        self.assertEqual(self.jreq("/api/market?crop=rice&date=1999-01-01")[0], 400)
        self.assertEqual(self.jreq("/api/nothing")[0], 404)
        self.assertEqual(self.jreq("/api/advise")[0], 405)      # GET on a POST route
        self.assertEqual(self.jreq("/api/health", raw=b"{}")[0], 405)
        self.assertEqual(self.jreq("/api/health")[0], 200)     # server still alive


if __name__ == "__main__":
    unittest.main()
