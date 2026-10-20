import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402
from studypilot.samples import SAMPLES  # noqa: E402
from studypilot.store import Store  # noqa: E402


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        app.STORE = Store(os.path.join(cls.tmp.name, "state.json"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        s = SAMPLES[0]
        cls.doc = cls.call("POST", "/api/docs", {"title": s["title"], "text": s["text"],
                                                 "sample": s["id"]})[1]["doc"]["id"]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    @classmethod
    def call(cls, method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(cls.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_health_and_samples(self):
        self.assertEqual(self.call("GET", "/api/health")[1]["ok"], True)
        self.assertEqual(len(self.call("GET", "/api/samples")[1]["samples"]), 3)
        self.assertEqual(self.call("GET", "/api/samples/nope")[0], 404)

    def test_doc_flow(self):
        d = "/api/docs/" + self.doc
        st, doc = self.call("GET", d)
        self.assertEqual(st, 200)
        self.assertTrue(doc["suggested_questions"])
        st, s = self.call("GET", d + "/summary?n=4")
        self.assertEqual(len(s["summary_ids"]), 4)
        st, c = self.call("GET", d + "/concepts?k=5")
        self.assertEqual(len(c["concepts"]), 5)
        st, q = self.call("GET", d + "/quiz?n=5&seed=2")
        self.assertEqual(len(q["questions"]), 5)
        self.assertNotIn("answer", q["questions"][0])
        answers = {x["id"]: (x["options"][0] if x["kind"] == "mcq" else "zzz") for x in q["questions"]}
        st, g = self.call("POST", d + "/quiz/grade", {"n": 5, "seed": 2, "answers": answers})
        self.assertEqual(st, 200)
        self.assertEqual(g["total"], 5)
        self.assertEqual(g["recorded"], 5)
        st, fc = self.call("GET", d + "/flashcards")
        cid = fc["queue"][0]
        st, r = self.call("POST", d + "/flashcards/review", {"card_id": cid, "rating": "good"})
        self.assertEqual(r["after"]["reps"], 1)
        self.assertEqual(r["deck"]["counts"]["learned"], 1)
        st, a = self.call("POST", d + "/ask", {"question": "What is a wait-for graph?"})
        self.assertIn("wait-for graph", a["results"][0]["text"])
        st, m = self.call("GET", d + "/mastery")
        self.assertGreater(m["totals"]["quiz_attempts"], 0)
        st, reset = self.call("POST", d + "/flashcards/reset", {})
        self.assertEqual(reset["counts"]["learned"], 0)

    def test_errors(self):
        self.assertEqual(self.call("POST", "/api/docs", raw=b"{bad")[0], 400)
        self.assertEqual(self.call("POST", "/api/docs", {"text": "short"})[0], 400)
        self.assertEqual(self.call("POST", "/api/docs", {"text": "x " * 200000})[0], 413)
        self.assertEqual(self.call("GET", "/api/docs/unknown/summary")[0], 404)
        self.assertEqual(self.call("GET", "/api/docs/%s/quiz?n=x" % self.doc)[0], 400)
        self.assertEqual(self.call("POST", "/api/docs/%s/ask" % self.doc, {"question": ""})[0], 400)
        self.assertEqual(self.call("POST", "/api/docs/%s/flashcards/review" % self.doc,
                                   {"card_id": "nope", "rating": "good"})[0], 404)
        self.assertEqual(self.call("DELETE", "/api/health")[0], 405)
        self.assertEqual(self.call("GET", "/api/nothing")[0], 404)

    def test_static(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"StudyPilot", r.read())
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/%2e%2e/app.py")


if __name__ == "__main__":
    unittest.main()
