import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import app  # noqa: E402
from neurocanvas.render import rasterise, to_canvas  # noqa: E402
from neurocanvas.preprocess import preprocess  # noqa: E402
from neurocanvas.service import ConflictError, Service  # noqa: E402
from neurocanvas.templates import strokes_for  # noqa: E402

_TMP = tempfile.TemporaryDirectory()
SVC = Service(os.path.join(ROOT, "data"), teach_path=os.path.join(_TMP.name, "teach.json"), log=lambda *a: None)


def tearDownModule():
    SVC.live.stop()
    _TMP.cleanup()


class ServiceCore(unittest.TestCase):
    def setUp(self):
        SVC.reset_model()
        SVC.teach.clear()

    def test_startup_is_fast_and_model_is_good(self):
        self.assertLess(SVC.startup_seconds, 10)
        ev = SVC.evaluation()
        self.assertGreater(ev["accuracy"], 0.95)
        self.assertEqual(sum(map(sum, ev["confusion"])), 1000)
        self.assertEqual(len(ev["per_class"]), 10)
        self.assertLess(ev["ms_per_image"], 50)

    def test_predict_returns_everything_the_ui_draws(self):
        x = SVC.test_X[0]
        out = SVC.predict({"pixels": x})
        self.assertEqual(out["pred"], SVC.test_Y[0])
        self.assertAlmostEqual(sum(out["probs"]), 1.0, places=3)
        self.assertEqual(len(out["saliency"]), 256)
        self.assertEqual([l["size"] for l in out["layers"]], [64, 32])
        self.assertTrue(out["edges"])
        # gradient x input + bias terms reproduce the winning logit
        ev = out["evidence"]
        self.assertAlmostEqual(ev["pixels"] + ev["bias"], out["logits"][out["pred"]], places=2)

    def test_raw_bitmap_goes_through_the_same_preprocessing(self):
        import random
        strokes = [[(x - 0.35, y - 0.5) for x, y in s] for s in strokes_for(7, random.Random(4))]
        img = rasterise(to_canvas(strokes, size=60, digit_px=40), 5.0, 60)
        a = SVC.predict({"raw": {"width": 60, "height": 60, "data": img}})
        b = SVC.predict({"pixels": preprocess(img, 60, 60)})
        self.assertEqual(a["input"], b["input"])
        self.assertEqual(a["pred"], 7)

    def test_bad_inputs_are_rejected(self):
        for body in ({}, {"pixels": [0.1] * 10}, {"pixels": ["a"] * 256}, {"pixels": [True] * 256},
                     {"pixels": [float("nan")] * 256}, {"raw": {"width": 2, "height": 2, "data": [0] * 3}},
                     {"raw": {"width": 9999, "height": 2, "data": []}}, [], "x"):
            with self.assertRaises((ValueError, TypeError)):
                SVC.predict(body)

    def test_empty_drawing(self):
        out = SVC.predict({"pixels": [0.0] * 256})
        self.assertTrue(out["empty"])
        with self.assertRaises(ValueError):
            SVC.explain({"pixels": [0.0] * 256})

    def test_explain_uses_real_numbers(self):
        x = SVC.test_X[5]
        auto = SVC.explain({"pixels": x})
        self.assertEqual(auto["label"], auto["pred"])
        self.assertGreaterEqual(len(auto["steps"]), 10)
        wrong = (auto["pred"] + 1) % 10
        forced = SVC.explain({"pixels": x, "label": wrong})
        self.assertGreater(forced["loss"], auto["loss"] + 1)
        self.assertGreater(forced["p_after_step"], forced["probs"][wrong])   # one SGD step helps
        self.assertIn("%.2f" % forced["loss"], " ".join(s["text"] for s in forced["steps"]))
        with self.assertRaises(ValueError):
            SVC.explain({"pixels": x, "label": 11})

    def test_teach_and_finetune_changes_predictions_then_reset(self):
        SVC.teach_demo()                      # 20 seven-segment digits
        listed = SVC.teach_list()
        self.assertEqual(len(listed["items"]), 20)
        rep = SVC.teach_finetune({"steps": 30, "replay": 32})
        self.assertGreaterEqual(rep["correct_after"], rep["correct_before"])
        self.assertGreaterEqual(rep["correct_after"], 18)
        self.assertGreater(rep["test_acc_after"], 0.9)     # replay limits forgetting
        self.assertGreaterEqual(rep["lcd_check_after"], rep["lcd_check_before"])
        self.assertTrue(SVC.model_info()["source"].startswith("fine-tuned"))
        SVC.reset_model()
        self.assertEqual(SVC.model_info()["source"], "pretrained")

    def test_teach_store_persists_and_validates(self):
        SVC.teach_add({"pixels": SVC.test_X[1], "label": 3})
        with open(SVC.teach.path) as f:
            self.assertEqual(len(json.load(f)["items"]), 1)
        with self.assertRaises(ValueError):
            SVC.teach_add({"pixels": SVC.test_X[1], "label": 12})
        with self.assertRaises(ValueError):
            SVC.teach_add({"pixels": [0.0] * 256, "label": 1})
        with self.assertRaises(ValueError):
            SVC.teach_finetune({"steps": 0})
        item = SVC.teach.snapshot()[0]
        SVC.teach_delete({"id": item["id"]})
        with self.assertRaises(KeyError):
            SVC.teach_delete({"id": item["id"]})

    def test_live_training_runs_and_can_be_adopted(self):
        st = SVC.train_start({"hidden": 16, "epochs": 2, "train_size": 600, "lr": 0.05})
        self.assertEqual(st["state"], "running")
        with self.assertRaises(ConflictError):
            SVC.train_start({})
        for _ in range(200):
            if SVC.train_status()["state"] != "running":
                break
            time.sleep(0.05)
        st = SVC.train_status()
        self.assertEqual(st["state"], "done")
        self.assertEqual(len(st["history"]), 2)
        self.assertEqual(len(st["tiles"]), 16)
        self.assertGreater(st["history"][-1]["test_acc"], 0.5)
        SVC.train_adopt()
        out = SVC.predict({"pixels": SVC.test_X[0]})
        self.assertEqual([l["size"] for l in out["layers"]], [16])
        SVC.reset_model()

    def test_live_params_are_validated(self):
        for bad in ({"lr": -1}, {"hidden": 0}, {"epochs": 1000}, {"activation": "gelu"}, {"lr": "fast"}):
            with self.assertRaises(ValueError):
                SVC.train_start(bad)

    def test_samples_and_demo(self):
        s = SVC.samples(digit=4, n=5)
        self.assertEqual([x["label"] for x in s["samples"]], [4] * 5)
        d = SVC.demo(digit=8, seed=2)
        self.assertEqual(d["digit"], 8)
        self.assertEqual(d, SVC.demo(digit=8, seed=2))
        with self.assertRaises(ValueError):
            SVC.demo(digit=3, style="comic")


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.SVC = SVC
        cls.httpd = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_endpoints_and_errors(self):
        st, body = self.call("/api/health")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["status"], "ok")
        st, body = self.call("/api/predict", {"pixels": SVC.test_X[2]})
        self.assertEqual(st, 200)
        self.assertIn("probs", json.loads(body))
        self.assertEqual(self.call("/api/predict", raw=b"{nope")[0], 400)
        self.assertEqual(self.call("/api/predict", {"pixels": [1]})[0], 400)
        self.assertEqual(self.call("/api/predict")[0], 405)          # GET on a POST route
        self.assertEqual(self.call("/api/health", {})[0], 405)       # POST on a GET route
        self.assertEqual(self.call("/api/nothing")[0], 404)
        self.assertEqual(self.call("/api/samples?digit=x")[0], 400)
        self.assertEqual(self.call("/api/train/adopt", {})[0] in (200, 409), True)
        SVC.reset_model()

    def test_static_files_and_traversal(self):
        st, body = self.call("/")
        self.assertEqual(st, 200)
        self.assertIn(b"NeuroCanvas", body)
        self.assertEqual(self.call("/app.js")[0], 200)
        self.assertEqual(self.call("/../app.py")[0], 404)
        self.assertEqual(self.call("/%2e%2e/app.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
