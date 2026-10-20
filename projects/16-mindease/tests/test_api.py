import datetime as dt
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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import app  # noqa: E402
from mindease.store import Store  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        app.STORE = Store(os.path.join(cls.tmp, "state.json"),
                          today_fn=lambda: dt.date(2026, 10, 23))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, path, method="GET", body=None, raw=None, token=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None
                                            else None)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers.get("Content-Type"), resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read().decode()

    def j(self, *a, **kw):
        status, _, text = self.req(*a, **kw)
        return status, json.loads(text)

    def login(self):
        s, d = self.j("/api/counsellor/login", "POST", {"pin": "2468", "name": "Ms. Test"})
        self.assertEqual(s, 200)
        return d["token"]

    # ------------------------------------------------------------------ student side
    def test_health_and_static(self):
        s, d = self.j("/api/health")
        self.assertEqual((s, d["status"], d["product"]), (200, "ok", "MindEase"))
        s, ctype, html = self.req("/")
        self.assertEqual(s, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("MindEase", html)
        s, ctype, _ = self.req("/app.js")
        self.assertIn("javascript", ctype)
        self.assertEqual(self.req("/../app.py")[0], 404)
        self.assertEqual(self.req("/nope.html")[0], 404)

    def test_no_external_urls_in_frontend(self):
        for name in ("index.html", "app.js", "style.css"):
            with open(os.path.join(HERE, "static", name), encoding="utf-8") as f:
                text = f.read()
            self.assertNotRegex(text, r"(src|href)=[\"']https?://", name)
            self.assertNotIn("@import", text)

    def test_questionnaires_and_screening(self):
        s, d = self.j("/api/questionnaires")
        self.assertEqual((s, len(d["phq9"]["items"]), len(d["gad7"]["items"])), (200, 9, 7))
        s, d = self.j("/api/screening", "POST", {"instrument": "gad7", "answers": [3] * 7})
        self.assertEqual((s, d["total"], d["band"]), (200, 21, "severe"))
        s, d = self.j("/api/screening", "POST", {"instrument": "phq9", "answers": [0] * 8 + [1]})
        self.assertTrue(d["support"]["show"])
        self.assertEqual(d["support"]["helplines"][0]["numbers"][0], "14416")
        s, d = self.j("/api/screening", "POST", {"instrument": "phq9", "answers": [0] * 5})
        self.assertEqual(s, 400)
        self.assertIn("answers", d["details"])

    def test_journal_flow(self):
        s, d = self.j("/api/journal", "POST", {"mood": 2, "sleep": 5, "text":
                                               "Not able to cope, I can't go on like this"})
        self.assertEqual(s, 201)
        self.assertTrue(d["safety"]["flagged"])
        self.assertIsNotNone(d["support"])
        eid = d["entry"]["id"]
        s, st = self.j("/api/student")
        self.assertEqual(st["journal"][0]["id"], eid)
        self.assertIn("insights", st["trends"])
        self.assertEqual(self.j("/api/journal/" + eid, "DELETE")[0], 200)
        self.assertEqual(self.j("/api/journal/" + eid, "DELETE")[0], 404)
        self.assertEqual(self.j("/api/journal", "POST", {"mood": 9})[0], 400)
        self.assertEqual(self.j("/api/journal", "GET")[0], 405)

    def test_analyze(self):
        s, d = self.j("/api/analyze", "POST", {"text": "not bad, semma day \U0001F604"})
        self.assertEqual((s, d["sentiment"]["label"]), (200, "positive"))
        self.assertFalse(d["safety"]["flagged"])
        self.assertNotIn("support", d)
        s, d = self.j("/api/analyze", "POST", {"text": "I want to die"})
        self.assertEqual(d["support"]["level"], "urgent")
        self.assertEqual(self.j("/api/analyze", "POST", {"text": 5})[0], 400)
        self.assertEqual(self.j("/api/analyze", "POST", {"text": "x" * 1001})[0], 400)

    def test_bad_bodies(self):
        self.assertEqual(self.req("/api/analyze", "POST", raw=b"{oops")[0], 400)
        self.assertEqual(self.req("/api/analyze", "POST", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.req("/api/analyze", "POST", raw=b"\xff\xfe")[0], 400)
        self.assertEqual(self.j("/api/nothing")[0], 404)
        self.assertEqual(self.j("/api/health", "POST", {})[0], 405)

    def test_trends_planner_script_resources_support(self):
        s, d = self.j("/api/trends")
        self.assertEqual(s, 200)
        self.assertTrue(d["series"])
        s, d = self.j("/api/planner", "POST", {"exams": [{"subject": "Maths", "date": "2026-10-27",
                                                          "confidence": 2}],
                                               "hours_per_day": 2})
        self.assertEqual(s, 200)
        self.assertEqual(d["days"][0]["date"], "2026-10-23")
        self.assertEqual(self.j("/api/planner", "POST", {"exams": []})[0], 400)
        s, d = self.j("/api/script", "POST", {"audience": "friend", "feelings": ["tired"]})
        self.assertEqual(s, 200)
        self.assertIn("tired all the time", d["full_text"])
        self.assertEqual(self.j("/api/script", "POST", {"feelings": ["x"]})[0], 400)
        self.assertEqual(self.j("/api/script/options")[0], 200)
        s, d = self.j("/api/resources")
        self.assertEqual(len(d["helplines"]), 2)
        s, d = self.j("/api/support?reason=journal&level=concern")
        self.assertEqual((s, d["level"]), (200, "concern"))
        self.assertEqual(self.j("/api/support?reason=hack")[0], 400)
        s, d = self.j("/api/support/contact", "POST", {"reason": "journal"})
        self.assertEqual(s, 200)
        self.assertIn("Tele-MANAS", d["message"])
        self.assertEqual(self.j("/api/consent", "POST", {"share_aggregate": "no"})[0], 400)
        s, d = self.j("/api/consent", "POST", {"share_aggregate": True})
        self.assertEqual((s, d["consent"]["share_aggregate"]), (200, True))

    # ------------------------------------------------------------------ counsellor side
    def test_counsellor_requires_login(self):
        self.assertEqual(self.j("/api/counsellor/dashboard")[0], 401)
        self.assertEqual(self.j("/api/counsellor/dashboard", token="forged")[0], 401)
        self.assertEqual(self.j("/api/counsellor/login", "POST", {"pin": "1234"})[0], 401)
        self.assertEqual(self.j("/api/counsellor/alerts/A001/ack", "POST", {})[0], 401)

    def test_counsellor_workflow(self):
        tok = self.login()
        s, d = self.j("/api/counsellor/dashboard", token=tok)
        self.assertEqual(s, 200)
        self.assertEqual(d["viewer"]["name"], "Ms. Test")
        new = next(a for a in d["alerts"] if a["status"] == "new")
        path = "/api/counsellor/alerts/%s/ack" % new["id"]
        s, r = self.j(path, "POST", {"note": "Will call"}, token=tok)
        self.assertEqual((s, r["alert"]["status"]), (200, "acknowledged"))
        self.assertEqual(r["alert"]["history"][-1]["by"], "Ms. Test")
        self.assertEqual(self.j(path, "POST", {}, token=tok)[0], 409)
        s, r = self.j("/api/counsellor/alerts/%s/followup" % new["id"], "POST", {}, token=tok)
        self.assertEqual(r["alert"]["status"], "followed_up")
        self.assertEqual(self.j("/api/counsellor/alerts/A999/ack", "POST", {}, token=tok)[0], 404)
        pending = next(c for c in d["contacts"] if c["status"] == "pending")
        s, r = self.j("/api/counsellor/contacts/%s/done" % pending["id"], "POST", token=tok)
        self.assertEqual((s, r["contact"]["status"]), (200, "contacted"))
        self.assertEqual(self.j("/api/counsellor/logout", "POST", token=tok)[0], 200)
        self.assertEqual(self.j("/api/counsellor/dashboard", token=tok)[0], 401)

    def test_evaluation_and_demo_reset(self):
        s, d = self.j("/api/evaluation")
        self.assertEqual(s, 200)
        self.assertIn("sentiment", d)
        self.assertIn("safety", d)
        s, d = self.j("/api/demo/reset", "POST")
        self.assertEqual((s, d["ok"]), (200, True))
        s, d = self.j("/api/student/erase", "POST")
        self.assertEqual(s, 200)
        s, st = self.j("/api/student")
        self.assertEqual(st["journal"], [])
        self.j("/api/demo/reset", "POST")


if __name__ == "__main__":
    unittest.main()
