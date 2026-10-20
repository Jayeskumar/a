import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from helpers import make_election, voter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402
from campusvote import config  # noqa: E402


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc, cls.codes = make_election(n=6)
        app.SERVICE = cls.svc
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        app.Handler.log_message = lambda *a: None
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, method=None, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_static_and_security_headers(self):
        st, body, h = self.req("/")
        self.assertEqual(st, 200)
        self.assertIn(b"CampusVote", body)
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(self.req("/../app.py")[0], 404)
        self.assertEqual(self.req("/crypto.js")[0], 200)

    def test_errors_are_json_with_status(self):
        self.assertEqual(self.req("/api/nope")[0], 404)
        self.assertEqual(self.req("/api/login", raw=b"{bad json")[0], 400)
        self.assertEqual(self.req("/api/login", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.req("/api/health", method="PUT")[0], 405)
        self.assertEqual(self.req("/api/admin/phase", {"phase": "tally"})[0], 403)
        self.assertEqual(self.req("/api/results")[0], 409)
        st, body, _ = self.req("/api/ballot", {"token": "ab" * 32})
        self.assertEqual(st, 400)
        self.assertIn("error", json.loads(body))

    def test_voter_flow_over_http(self):
        reg, code = sorted(self.codes.items())[0]
        st, body, _ = self.req("/api/login", {"reg_no": reg, "code": code})
        self.assertEqual(st, 200)
        sess = json.loads(body)["session"]
        dev = voter(self.svc)
        st, body, _ = self.req("/api/issue", {"session": sess, "blinded": "%x" % dev.prepare_token()})
        self.assertEqual(st, 200)
        dev.finish_token(int(json.loads(body)["blind_sig"], 16))
        ballot = dev.build_ballot({"president": "c2", "secretary": "c3"})
        st, body, _ = self.req("/api/ballot", ballot)
        self.assertEqual(st, 202)
        self.assertEqual(self.req("/api/ballot", ballot)[0], 409)   # replay
        st, body, _ = self.req("/api/admin/flush", {}, headers={"X-Admin-Key": config.ADMIN_KEY})
        self.assertEqual(st, 200)
        th = json.loads(self.req("/api/receipt/" + dev.receipt["token_hash"][:16])[1])
        self.assertEqual(th["status"], "posted")
        for path in ("/api/stats", "/api/election", "/api/board", "/api/board/verify", "/api/security", "/api/info",
                     "/api/link"):
            self.assertEqual(self.req(path)[0], 200, path)


if __name__ == "__main__":
    unittest.main()
