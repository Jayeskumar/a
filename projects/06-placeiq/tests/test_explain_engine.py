import itertools
import json
import math
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from placeiq import config as C, data, explain  # noqa: E402
from placeiq.engine import Engine  # noqa: E402
from placeiq.models import LogisticRegression, StandardScaler, sigmoid  # noqa: E402


def toy_model(weights, bias=-2.0):
    """A hand-built model over the real feature list with std = 1 everywhere."""
    m = LogisticRegression()
    m.w = [weights.get(f, 0.0) for f in C.FEATURE_NAMES]
    m.b = bias
    sc = StandardScaler()
    sc.mean = [0.0] * len(C.FEATURE_NAMES)
    sc.std = [1.0] * len(C.FEATURE_NAMES)
    return m, sc


def student(**kw):
    x = {f: 0.0 for f in C.FEATURE_NAMES}
    x.update(cgpa=7.0, tenth_pct=80, twelfth_pct=80, aptitude_score=50, communication_score=50,
             mock_interview_score=50)
    x.update(kw)
    return [float(x[f]) for f in C.FEATURE_NAMES]


class TestCounterfactual(unittest.TestCase):
    def test_reaches_target_with_minimum_effort(self):
        # Three helpful levers; brute-force every combination and compare with the DP.
        w = {"projects": 0.5, "coding_problems": 0.01, "backlogs": -0.6}
        m, sc = toy_model(w, bias=-2.5)
        x = student(projects=0, coding_problems=50, backlogs=3)
        plan = explain.counterfactual(m, sc, x, target=0.7)
        self.assertTrue(plan["reachable"])
        self.assertGreaterEqual(plan["p_after"], 0.7 - 1e-9)
        self.assertLess(plan["p_before"], 0.7)
        need = math.log(0.7 / 0.3) - m.decision(x)
        best = None
        A = C.ACTIONS
        for sp, sc_, sb in itertools.product(range(4), range(11), range(4)):
            gain = sp * 0.5 + sc_ * A["coding_problems"][0] * 0.01 + sb * 0.6
            cost = sp * A["projects"][2] + sc_ * A["coding_problems"][2] + sb * A["backlogs"][2]
            if gain >= need - 1e-12 and (best is None or cost < best):
                best = cost
        self.assertAlmostEqual(plan["total_effort_weeks"], best)
        # actions are ranked by effort, with a non-decreasing probability staircase
        efforts = [a["effort_weeks"] for a in plan["actions"]]
        self.assertEqual(efforts, sorted(efforts))
        ps = [a["p_after"] for a in plan["actions"]]
        self.assertEqual(ps, sorted(ps))

    def test_never_suggests_history_or_harmful_levers(self):
        # Hackathons get a negative weight here: the planner must not push them.
        w = {"tenth_pct": 0.2, "twelfth_pct": 0.2, "hackathons": -0.3, "projects": 0.4}
        m, sc = toy_model(w, bias=-30)
        plan = explain.counterfactual(m, sc, student(projects=0), target=0.7)
        feats = set(plan["levers_considered"])
        self.assertNotIn("tenth_pct", feats)
        self.assertNotIn("twelfth_pct", feats)
        self.assertNotIn("hackathons", feats)
        self.assertIn("projects", feats)

    def test_unreachable_reports_best_effort(self):
        m, sc = toy_model({"projects": 0.1}, bias=-20)
        plan = explain.counterfactual(m, sc, student(projects=0), target=0.7)
        self.assertFalse(plan["reachable"])
        self.assertEqual(plan["actions"][0]["steps"], C.ACTIONS["projects"][1])  # all realistic steps used
        self.assertLess(plan["p_after"], 0.7)

    def test_already_above_target(self):
        m, sc = toy_model({"projects": 1.0}, bias=3)
        plan = explain.counterfactual(m, sc, student(projects=2), target=0.7)
        self.assertTrue(plan["already_above"])
        self.assertEqual(plan["actions"], [])
        self.assertTrue(plan["boosters"])

    def test_respects_feature_bounds(self):
        m, sc = toy_model({"backlogs": -1.0, "aptitude_score": 0.05}, bias=-4)
        plan = explain.counterfactual(m, sc, student(backlogs=2, aptitude_score=98), target=0.7)
        for a in plan["actions"]:
            lo, hi = C.FEATURE_RANGES[a["feature"]]
            self.assertTrue(lo <= a["to"] <= hi, a)

    def test_contributions_sum_to_logit(self):
        m, sc = toy_model({"projects": 0.4, "cgpa": 0.3, "backlogs": -0.5}, bias=-1)
        x = student(projects=3, backlogs=1)
        total = sum(c["contribution"] for c in explain.contributions(m, sc, x))
        self.assertAlmostEqual(m.b + total, m.decision(sc.transform_row(x)))


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = Engine()

    def test_holdout_metrics_are_sane(self):
        ev = self.E.eval
        self.assertEqual(ev["n_test"], 150)
        self.assertGreater(ev["roc_auc"], 0.85)
        self.assertGreater(ev["accuracy"], ev["majority_baseline_accuracy"] + 0.1)
        self.assertTrue(ev["converged"])
        self.assertGreater(self.E.package["r2"], 0.3)

    def test_model_info_is_json_safe(self):
        json.dumps(self.E.model_info(), allow_nan=False)
        json.dumps(self.E.eda(), allow_nan=False)
        json.dumps(self.E.dashboard(), allow_nan=False)

    def test_at_risk_sorted_and_csv(self):
        rows = self.E.at_risk(0.5)
        ps = [r["probability"] for r in rows]
        self.assertEqual(ps, sorted(ps))
        self.assertTrue(all(p < 0.5 for p in ps))
        self.assertTrue(all(r["status"] != "Placed" for r in rows))
        csv_text = self.E.at_risk_csv(0.5)
        self.assertTrue(csv_text.startswith("student_id,name,dept"))
        self.assertEqual(len(csv_text.strip().splitlines()), len(rows) + 1)

    def test_fairness_covers_departments(self):
        f = self.E.fairness()
        self.assertEqual({g["dept"] for g in f["groups"]}, set(C.DEPARTMENTS))
        self.assertFalse(f["dept_used_as_feature"])

    def test_student_explanation(self):
        sid = self.E.at_risk(0.5)[-1]["student_id"]
        s = self.E.student(sid)
        self.assertGreaterEqual(s["plan"]["p_after"], 0.7 - 1e-3)
        self.assertIsNotNone(s["top_gap"])
        self.assertIsNotNone(s["persona"])

    def test_clusters(self):
        c = self.E.clusters(4)
        self.assertEqual(sum(g["size"] for g in c["clusters"]), 600)
        self.assertEqual(len({g["name"] for g in c["clusters"]}), 4)

    def test_upload_rejects_tiny_file_and_keeps_old_data(self):
        e = Engine()
        ok, rep, msg = e.load_csv(data.to_csv(data.generate(n=12)), "tiny.csv")
        self.assertFalse(ok)
        self.assertEqual(len(e.rows), 600)


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        from http.server import ThreadingHTTPServer
        app.ENGINE = Engine()
        app.Handler.log_message = lambda *a: None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, path, body=None, ctype="application/json"):
        r = urllib.request.Request(self.base + path, data=body, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_endpoints(self):
        for p in ["/api/health", "/api/dataset", "/api/eda", "/api/model", "/api/fairness", "/api/dashboard",
                  "/api/students?dept=CSE", "/api/at-risk?threshold=0.4", "/api/clusters?k=3", "/"]:
            status, _ = self.req(p)
            self.assertEqual(status, 200, p)
        status, body = self.req("/api/at-risk.csv")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"student_id"))

    def test_predict_and_errors(self):
        feats = {f: 1 for f in C.FEATURE_NAMES}
        feats.update(cgpa=7.5, aptitude_score=60, communication_score=60, mock_interview_score=60,
                     tenth_pct=80, twelfth_pct=80, coding_problems=100)
        status, body = self.req("/api/predict", json.dumps({"features": feats}).encode())
        self.assertEqual(status, 200)
        self.assertIn("plan", json.loads(body))
        self.assertEqual(self.req("/api/predict", b"{bad")[0], 400)
        self.assertEqual(self.req("/api/predict", json.dumps({"features": {"cgpa": 99}}).encode())[0], 400)
        self.assertEqual(self.req("/api/student/NOPE")[0], 404)
        self.assertEqual(self.req("/api/dashboard?dept=CIVIL")[0], 400)
        self.assertEqual(self.req("/api/at-risk?threshold=7")[0], 400)
        self.assertEqual(self.req("/api/unknown")[0], 404)
        self.assertEqual(self.req("/../app.py")[0], 404)
        self.assertEqual(self.req("/api/upload", b"a,b\n1,2\n", "text/csv")[0], 422)


if __name__ == "__main__":
    unittest.main()
