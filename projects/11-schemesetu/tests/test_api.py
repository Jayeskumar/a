"""End-to-end HTTP tests against an in-process server with a temporary state file."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import app  # noqa: E402
from schemesetu.engine import Engine  # noqa: E402
from schemesetu.store import Store  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        app.ENGINE = Engine(os.path.join(HERE, "data"))
        app.STORE = Store(os.path.join(cls.tmp, "state.json"))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def call(self, path, body=None, method=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        req = Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_health_meta_schemes(self):
        s, d = self.call("/api/health")
        self.assertEqual((s, d["status"]), (200, "ok"))
        s, d = self.call("/api/schemes")
        self.assertEqual(d["count"], len(app.ENGINE.cat.schemes))
        self.assertTrue(all("verify_note" in x for x in d["schemes"]))
        s, d = self.call("/api/schemes/pm_kisan")
        self.assertEqual(d["short"], "PM-KISAN")
        self.assertEqual(self.call("/api/schemes/zzz")[0], 404)
        self.assertEqual(self.call("/api/meta")[0], 200)
        self.assertEqual(self.call("/api/questions")[0], 200)

    def test_next_and_evaluate(self):
        s, d = self.call("/api/next", {"profile": {}})
        self.assertEqual(s, 200)
        self.assertFalse(d["done"])
        self.assertIn(d["next"]["id"], app.ENGINE.cat.q_by_id)
        s, d = self.call("/api/evaluate", {"profile": {"rural": True, "land_ha": 1}})
        self.assertEqual(s, 200)
        self.assertEqual(sum(d["counts"].values()), len(app.ENGINE.cat.schemes))

    def test_bad_input(self):
        self.assertEqual(self.call("/api/evaluate", {"profile": {"land_ha": "lots"}})[0], 400)
        self.assertEqual(self.call("/api/evaluate", {"profile": {"unknown": 1}})[0], 400)
        self.assertEqual(self.call("/api/evaluate", raw=b"{oops")[0], 400)
        self.assertEqual(self.call("/api/evaluate", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.call("/api/next", {"profile": {}, "skipped": "x"})[0], 400)
        self.assertEqual(self.call("/api/next", {"profile": {}, "strategy": "magic"})[0], 400)
        self.assertEqual(self.call("/api/search")[0], 400)
        self.assertEqual(self.call("/api/search?q=x&k=abc")[0], 400)
        self.assertEqual(self.call("/api/nope")[0], 404)
        self.assertEqual(self.call("/api/evaluate")[0], 405)
        self.assertEqual(self.call("/api/simulate", {"demo": "nobody"})[0], 404)
        self.assertEqual(self.call("/api/../../etc/passwd")[0], 404)

    def test_search_simulate_checklist(self):
        s, d = self.call("/api/search?q=" + quote("பயிர் காப்பீடு"))
        self.assertEqual(d["results"][0]["id"], "pmfby")
        s, d = self.call("/api/simulate", {"demo": "demo-farmer"})
        self.assertEqual(s, 200)
        self.assertLess(d["questions_asked"], d["full_form"] + 4)
        self.assertEqual(d["evaluation"]["counts"]["possibly"], 0)
        s, d = self.call("/api/checklist", {"scheme_ids": ["pm_kisan", "pmfby"]})
        self.assertEqual(s, 200)
        self.assertEqual(len(set(x["id"] for x in d["items"])), d["count"])

    def test_household_tracker_village(self):
        s, d = self.call("/api/households", {"name": "Test family", "village": "Testur", "profile": {"rural": True}})
        self.assertEqual(s, 200)
        hid = d["household"]["id"]
        s, d = self.call("/api/households/%s/applications" % hid, {"scheme_id": "mgnrega", "status": "applied"})
        self.assertEqual(d["household"]["applications"]["mgnrega"]["status"], "applied")
        self.assertEqual(self.call("/api/households/%s/applications" % hid, {"scheme_id": "mgnrega", "status": "won"})[0], 400)
        self.assertEqual(self.call("/api/households/%s/applications" % hid, {"scheme_id": "zzz", "status": "applied"})[0], 400)
        s, d = self.call("/api/households/%s" % hid, {"profile": {"rural": True, "willing_manual_work": True}}, method="PUT")
        self.assertEqual(s, 200)
        st = dict((r["id"], r) for r in d["evaluation"]["results"])
        self.assertEqual(st["mgnrega"]["status"], "eligible")
        self.assertEqual(st["mgnrega"]["application"], "applied")
        s, d = self.call("/api/village?village=Testur")
        self.assertEqual(d["totals"]["households"], 1)
        self.assertEqual(self.call("/api/households", {"name": "", "profile": {}})[0], 400)
        s, d = self.call("/api/households/%s" % hid, method="DELETE")
        self.assertEqual(s, 200)
        self.assertEqual(self.call("/api/households/%s" % hid)[0], 404)

    def test_demo_village_seed(self):
        s, d = self.call("/api/demo/village", {})
        self.assertEqual(s, 200)
        s, v = self.call("/api/village")
        self.assertGreaterEqual(v["totals"]["households"], d["households"])
        self.assertGreater(v["totals"]["unclaimed_pairs"], 0)

    def test_static(self):
        with urlopen(self.base + "/", timeout=10) as r:
            self.assertIn(b"SchemeSetu", r.read())
        with urlopen(self.base + "/app.js", timeout=10) as r:
            self.assertIn("javascript", r.headers.get("Content-Type"))


if __name__ == "__main__":
    unittest.main()
