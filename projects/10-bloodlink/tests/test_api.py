import json
import os
import threading
import unittest
import urllib.error
import urllib.request

import _helpers

os.environ["BLOODLINK_QUIET"] = "1"
import app  # noqa: E402


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = app.make_server("127.0.0.1", 0, os.path.join(_helpers.ROOT, "data"))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def j(self, path, body=None, status=200):
        code, data = self.call(path, body)
        self.assertEqual(code, status, data[:300])
        return json.loads(data)

    def test_static_and_traversal(self):
        code, data = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"BloodLink", data)
        self.assertEqual(self.call("/../app.py")[0], 404)
        self.assertEqual(self.call("/%2e%2e/app.py")[0], 404)

    def test_meta_and_compat(self):
        m = self.j("/api/meta")
        self.assertEqual(len(m["groups"]), 8)
        self.assertEqual(len(m["hospitals"]), 6)
        c = self.j("/api/compatibility")
        self.assertTrue(c["red"]["AB+"]["O-"])
        self.assertFalse(c["red"]["O-"]["AB+"])

    def test_match_and_errors(self):
        r = self.j("/api/match", {"hospital_id": "H1", "group": "A+", "units": 3, "urgency": "critical"})
        self.assertGreater(len(r["ranked"]), 10)
        self.assertEqual(r["ranked"][0]["rank"], 1)
        self.assertIn("explanation", r["ranked"][0])
        self.j("/api/match", {"hospital_id": "H1", "group": "Q+"}, status=400)
        code, _ = self.call("/api/match", raw=b"{not json")
        self.assertEqual(code, 400)
        code, _ = self.call("/api/match", raw=b"[1,2]")
        self.assertEqual(code, 400)
        self.j("/api/nope", status=404)

    def test_donors(self):
        lst = self.j("/api/donors?limit=5&group=O-")
        self.assertTrue(all(d["group"] == "O-" for d in lst["donors"]))
        self.assertNotIn("sim_willingness", lst["donors"][0])   # simulator truth stays hidden
        d = self.j("/api/donors/D-0001")
        self.assertIn("eligibility", d)
        self.assertEqual(len(d["badges"]), 8)
        self.j("/api/donors/D-9999", status=404)
        self.j("/api/donors/D-0001/availability", {"available": "yes"}, status=400)

    def test_eligibility_endpoint(self):
        r = self.j("/api/eligibility", {"today": "2026-10-23", "age": 30, "sex": "F", "weight_kg": 55,
                                        "last_donation": "2026-08-01"})
        self.assertFalse(r["eligible"])
        self.assertEqual(r["next_eligible_date"], "2026-11-29")
        self.j("/api/eligibility", {"age": 30, "sex": "M"}, status=400)

    def test_simulate_broadcast_reset(self):
        req = {"hospital_id": "H2", "group": "B+", "units": 2, "urgency": "urgent", "seed": 4}
        s = self.j("/api/simulate", req)
        self.assertEqual(set(s["strategies"]), {"waves", "broadcast", "first_come"})
        b = self.j("/api/broadcast", req)
        self.assertEqual(b["applied"]["alerted"], len(b["result"]["notified_ids"]))
        act = self.j("/api/activity")["activity"]
        self.assertTrue(act)
        if b["result"]["donated_ids"]:
            d = self.j("/api/donors/" + b["result"]["donated_ids"][0])
            self.assertFalse(d["eligibility"]["eligible"])     # just donated
        self.assertTrue(self.j("/api/demo/reset", {})["ok"])
        self.assertEqual(self.j("/api/activity")["activity"], [])

    def test_inventory_endpoints(self):
        inv = self.j("/api/inventory")
        self.assertEqual(len(inv["banks"]), 5)
        self.assertIn("forecast_backtest", inv)
        r = self.j("/api/inventory/issue", {"bank_id": "BB1", "group": "O+", "units": 2})
        days = [u["days_left"] for u in r["issued"] if u["tier"] == "exact"]
        self.assertEqual(days, sorted(days))
        self.j("/api/inventory/issue", {"bank_id": "BB9", "group": "O+"}, status=400)
        a = self.j("/api/inventory/transfers/apply", {})
        self.assertGreaterEqual(a["moved"], 0)
        m = self.j("/api/inventory/month?seeds=2")
        self.assertEqual(m["summary"]["seeds"], 2)
        self.j("/api/demo/reset", {})

    def test_evaluate(self):
        e = self.j("/api/evaluate?n=10&seed=2")
        self.assertEqual(e["n"], 10)
        self.j("/api/evaluate?n=abc", status=400)


if __name__ == "__main__":
    unittest.main()
