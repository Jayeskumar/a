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

import app  # noqa: E402


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.ENGINE = app.load_engine()
        app.Handler.log_message = lambda *a, **k: None
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
        r = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_static_and_get_endpoints(self):
        st, body = self.req("/")
        self.assertEqual(st, 200)
        self.assertIn(b"PhishGuard", body)
        for p in ("/api/health", "/api/samples", "/api/quiz", "/api/stats", "/api/rules"):
            st, body = self.req(p)
            self.assertEqual(st, 200, p)
            json.loads(body)

    def test_analyze_url_bulk(self):
        st, body = self.req("/api/analyze", {"text": "Share OTP now or your account will be blocked"})
        self.assertEqual(st, 200)
        self.assertIn(json.loads(body)["verdict"], ("Suspicious", "Dangerous"))
        st, body = self.req("/api/url", {"url": "http://paytrn-kyc.online/verify"})
        self.assertEqual(json.loads(body)["verdict"], "Dangerous")
        st, body = self.req("/api/bulk", {"text": "hi da\nbit.ly/x1y2z3"})
        self.assertEqual(json.loads(body)["count"], 2)

    def test_errors(self):
        self.assertEqual(self.req("/api/analyze", raw=b"not json")[0], 400)
        self.assertEqual(self.req("/api/analyze", {"text": ""})[0], 400)
        self.assertEqual(self.req("/api/analyze", {"text": 5})[0], 400)
        self.assertEqual(self.req("/api/analyze", {"text": "x" * 6000})[0], 413)
        self.assertEqual(self.req("/api/bulk", {"lines": [1, 2]})[0], 400)
        self.assertEqual(self.req("/api/bulk", {"lines": ["a"] * 201})[0], 413)
        self.assertEqual(self.req("/api/nope")[0], 404)
        self.assertEqual(self.req("/api/nope", {})[0], 404)
        self.assertEqual(self.req("/../app.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
