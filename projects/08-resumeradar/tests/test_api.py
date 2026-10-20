import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["RR_QUIET"] = "1"

import app  # noqa: E402
from resumeradar.demo import get_demo  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        d = get_demo()
        cls.jd = d["jds"][0]["text"]
        cls.resumes = [{"id": r["id"], "name": r["name"], "text": r["text"]} for r in d["resumes"][:6]]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, path, body=None, method=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                payload = r.read()
                return r.status, (json.loads(payload) if "json" in ctype else payload)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_static_and_health(self):
        st, body = self.call("/")
        self.assertEqual(st, 200)
        self.assertIn(b"ResumeRadar", body)
        st, h = self.call("/api/health")
        self.assertTrue(h["ok"])
        self.assertGreaterEqual(h["skills"], 200)

    def test_get_endpoints(self):
        for path in ("/api/demo", "/api/config", "/api/ontology", "/api/ontology?q=k8s"):
            st, _ = self.call(path)
            self.assertEqual(st, 200, path)
        _, onto = self.call("/api/ontology?q=k8s")
        self.assertEqual([s["name"] for s in onto["skills"]], ["Kubernetes"])

    def test_screen_and_bias(self):
        st, res = self.call("/api/screen", {"jd": self.jd, "resumes": self.resumes, "blind": True})
        self.assertEqual(st, 200)
        self.assertEqual(res["count"], 6)
        scores = [r["score"] for r in res["ranking"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(res["ranking"][0]["display_name"].startswith("Candidate"))
        st, b = self.call("/api/bias-check", {"jd": self.jd, "resumes": self.resumes})
        self.assertEqual(st, 200)
        self.assertTrue(b["blind"]["invariant"])

    def test_single_resume_endpoints(self):
        r = self.resumes[2]["text"]
        for path, body in (("/api/match", {"resume": r, "jd": self.jd}),
                           ("/api/parse-resume", {"text": r}),
                           ("/api/parse-jd", {"text": self.jd}),
                           ("/api/mask", {"text": r}),
                           ("/api/ats", {"text": r, "jd": self.jd}),
                           ("/api/ats", {"text": r}),
                           ("/api/interview", {"resume": r, "jd": self.jd}),
                           ("/api/learning-path", {"targets": ["Kubernetes"], "known": ["Linux"]})):
            st, out = self.call(path, body)
            self.assertEqual(st, 200, path)
            self.assertIsInstance(out, dict)
        _, lp = self.call("/api/learning-path", {"targets": ["Kubernetes"], "known": ["Linux"]})
        self.assertEqual([s["name"] for s in lp["steps"]], ["Docker", "Kubernetes"])

    def test_errors(self):
        self.assertEqual(self.call("/api/match", raw=b"{nope")[0], 400)
        self.assertEqual(self.call("/api/match", raw=b"[1]")[0], 400)
        self.assertEqual(self.call("/api/match", {"resume": "tiny", "jd": self.jd})[0], 400)
        self.assertEqual(self.call("/api/match", {"resume": 5, "jd": self.jd})[0], 400)
        self.assertEqual(self.call("/api/screen", {"jd": self.jd, "resumes": []})[0], 400)
        self.assertEqual(self.call("/api/screen", {"jd": self.jd, "resumes": [7]})[0], 400)
        self.assertEqual(self.call("/api/match", {"resume": "x" * 70000, "jd": self.jd})[0], 413)
        self.assertEqual(self.call("/api/learning-path", {"targets": ["Nope"]})[0], 400)
        self.assertEqual(self.call("/api/nothing")[0], 404)
        self.assertEqual(self.call("/api/match")[0], 405)
        self.assertEqual(self.call("/missing.js")[0], 404)
        # the server keeps serving after bad input
        self.assertEqual(self.call("/api/health")[0], 200)


if __name__ == "__main__":
    unittest.main()
