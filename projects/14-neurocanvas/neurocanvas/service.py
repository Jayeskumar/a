"""Application state and use-cases. app.py maps HTTP routes onto these methods.

Thread-safety: the active model is never mutated in place. Fine-tuning and
live training work on copies, and swapping the active model is one assignment
under a lock, so concurrent /api/predict calls always see a whole model.
"""

import os
import random
import statistics
import threading
import time

from . import __version__
from . import config as C
from .dataset import load_or_generate
from .explain import explain, inspect
from .live import LiveTrainer
from .metrics import accuracy, evaluate
from .mlp import softmax
from .preprocess import preprocess
from .render import demo_strokes, render_digit
from .teach import TeachStore, finetune, validate_pixels
from .train import load_weights, save_weights, train_main_model

MAX_RAW_SIDE = 512


def _int(v, name, lo, hi, default=None):
    if v is None:
        if default is None:
            raise ValueError("'%s' is required" % name)
        return default
    if isinstance(v, bool):
        raise ValueError("'%s' must be an integer" % name)
    try:
        iv = int(v)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be an integer" % name)
    if not lo <= iv <= hi:
        raise ValueError("'%s' must be between %d and %d" % (name, lo, hi))
    return iv


def _float(v, name, lo, hi, default):
    if v is None:
        return default
    if isinstance(v, bool):
        raise ValueError("'%s' must be a number" % name)
    try:
        fv = float(v)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be a number" % name)
    if fv != fv or not lo <= fv <= hi:
        raise ValueError("'%s' must be between %s and %s" % (name, lo, hi))
    return fv


class Service:
    def __init__(self, data_dir, teach_path=None, log=print):
        t0 = time.perf_counter()
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.ds = load_or_generate(os.path.join(data_dir, "digits.bin.gz"), log=log)
        wpath = os.path.join(data_dir, "weights.json")
        if os.path.exists(wpath):
            self.base, self.meta = load_weights(wpath)
        else:
            log("  no data/weights.json - training a quick model (run `python -m neurocanvas.train` for the full one)")
            self.base, self.meta = train_main_model(self.ds, epochs=2, log=log)
            save_weights(self.base, self.meta, wpath)
        self.model = self.base.copy()
        self.source = "pretrained"
        self.version = 1
        self.test_X, self.test_Y = self.ds.arrays("test")
        self.train_X, self.train_Y = self.ds.arrays("train")
        self.teach = TeachStore(teach_path if teach_path is not None else os.path.join(data_dir, "teach.json"))
        self.live = LiveTrainer(self.ds)
        self._eval = None
        self._lcd = None
        self.startup_seconds = round(time.perf_counter() - t0, 2)

    # ---- model state ----
    def _active(self):
        with self.lock:
            return self.model, self.version, self.source

    def _swap(self, model, source):
        with self.lock:
            self.model = model
            self.source = source
            self.version += 1
            self._eval = None
            return self.version

    def health(self):
        m, v, src = self._active()
        return {"status": "ok", "version": __version__, "model": src, "model_version": v,
                "sizes": m.sizes, "startup_seconds": self.startup_seconds,
                "train_images": len(self.train_Y), "test_images": len(self.test_Y)}

    def model_info(self):
        m, v, src = self._active()
        hist = self.meta.get("history", [])
        return {"sizes": m.sizes, "activation": m.activation, "n_params": m.n_params,
                "source": src, "model_version": v, "grid": C.GRID, "fit": C.FIT,
                "pretrained": {"history": hist, "train_seconds": self.meta.get("train_seconds"),
                               "epochs": self.meta.get("epochs"), "lr": self.meta.get("lr"),
                               "batch": self.meta.get("batch"), "momentum": self.meta.get("momentum"),
                               "l2": self.meta.get("l2"), "n_train": self.meta.get("n_train"),
                               "test_acc": hist[-1].get("test_acc") if hist else None},
                "dataset": self.ds.header}

    def reset_model(self):
        v = self._swap(self.base.copy(), "pretrained")
        return {"ok": True, "model_version": v, "source": "pretrained"}

    # ---- inputs ----
    def _pixels(self, body):
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object")
        if "pixels" in body:
            return validate_pixels(body["pixels"])
        raw = body.get("raw")
        if isinstance(raw, dict):
            w = _int(raw.get("width"), "raw.width", 1, MAX_RAW_SIDE)
            h = _int(raw.get("height"), "raw.height", 1, MAX_RAW_SIDE)
            data = raw.get("data")
            if not isinstance(data, list) or len(data) != w * h:
                raise ValueError("raw.data must be a list of width*height numbers")
            img = validate_pixels(data, w * h)
            return preprocess(img, w, h)
        raise ValueError("send {'pixels': [256 numbers in 0..1]} or {'raw': {width, height, data}}")

    # ---- predict / explain ----
    def predict(self, body):
        x = self._pixels(body)
        m, v, src = self._active()
        t0 = time.perf_counter()
        out = inspect(m, x)
        out["latency_ms"] = round(1000 * (time.perf_counter() - t0), 3)
        out["input"] = [round(p, 3) for p in x]
        out["empty"] = sum(x) == 0
        out["model_version"] = v
        out["model"] = src
        return out

    def explain(self, body):
        x = self._pixels(body)
        if sum(x) == 0:
            raise ValueError("draw something first - the canvas is empty")
        label = body.get("label")
        label = None if label in (None, "", "auto") else _int(label, "label", 0, 9)
        lr = _float(body.get("lr"), "lr", 0.0001, 5.0, 0.05)
        m, v, src = self._active()
        out = explain(m, x, label, lr)
        out["model_version"] = v
        out["sizes"] = m.sizes
        return out

    def weights(self):
        m, v, _ = self._active()
        tiles = []
        for row in m.W[0]:
            mx = max(abs(w) for w in row) or 1.0
            tiles.append([round(w / mx, 2) for w in row])
        return {"model_version": v, "layer1": tiles, "sizes": m.sizes}

    # ---- evaluation ----
    def evaluation(self):
        m, v, src = self._active()
        with self.lock:
            if self._eval and self._eval["model_version"] == v:
                return self._eval
        ev = evaluate(m, self.test_X, self.test_Y)
        for w in ev["misclassified"]:
            w["pixels"] = list(self.ds.test_b[w["index"]])
        times = []
        for x in self.test_X[:200]:
            t0 = time.perf_counter()
            inspect(m, x)
            times.append(1000 * (time.perf_counter() - t0))
        ev["inspect_ms_median"] = round(statistics.median(times), 3)
        ev["model_version"] = v
        ev["model"] = src
        ev["history"] = self.meta.get("history", [])        # always the pretrained run
        ev["train_seconds"] = self.meta.get("train_seconds")
        with self.lock:
            if self.version == v:
                self._eval = ev
        return ev

    def samples(self, digit=None, n=24, split="train", offset=0):
        if split not in ("train", "test"):
            raise ValueError("split must be 'train' or 'test'")
        n = _int(n, "n", 1, 200, 24)
        offset = _int(offset, "offset", 0, 100000, 0)
        ys, bs = (self.ds.train_y, self.ds.train_b) if split == "train" else (self.ds.test_y, self.ds.test_b)
        if digit is not None:
            digit = _int(digit, "digit", 0, 9)
        idx = [i for i, y in enumerate(ys) if digit is None or y == digit][offset:offset + n]
        return {"split": split, "digit": digit, "samples": [{"index": i, "label": ys[i], "pixels": list(bs[i])}
                                                           for i in idx]}

    def demo(self, digit=None, seed=None, style="hand"):
        if style not in ("hand", "lcd"):
            raise ValueError("style must be 'hand' or 'lcd'")
        seed = _int(seed, "seed", 0, 10 ** 9, random.randrange(10 ** 6))
        digit = _int(digit, "digit", 0, 9, random.Random(seed).randrange(10))
        return {"digit": digit, "seed": seed, "style": style, "strokes": demo_strokes(digit, seed, style)}

    # ---- live training ----
    def train_start(self, body):
        try:
            return self.live.start(body or {})
        except RuntimeError as e:
            raise ConflictError(str(e))

    def train_status(self):
        return self.live.status()

    def train_stop(self):
        return self.live.stop()

    def train_adopt(self):
        m = self.live.trained_model()
        if m is None:
            raise ConflictError("no finished training run to use yet")
        st = self.live.status()
        v = self._swap(m, "live run #%d (%s)" % (st.get("run", 0), "-".join(map(str, m.sizes))))
        return {"ok": True, "model_version": v, "source": self.source}

    # ---- teach it ----
    def _lcd_check(self):
        """30 seven-segment digits the user never adds: does teaching generalise?"""
        if self._lcd is None:
            rng = random.Random(4242)
            X, Y = [], []
            for k in range(3):
                for d in range(10):
                    X.append(render_digit(d, rng, "lcd", noise=False))
                    Y.append(d)
            self._lcd = (X, Y)
        return self._lcd

    def teach_list(self):
        m, v, src = self._active()
        items = []
        for it in self.teach.snapshot():
            p = softmax(m.forward(it["pixels"])[0][-1])
            pred = max(range(10), key=p.__getitem__)
            items.append({"id": it["id"], "label": it["label"], "source": it.get("source", "drawn"),
                          "pixels": it["pixels"], "pred": pred, "p_label": round(p[it["label"]], 4)})
        X, Y = self._lcd_check()
        return {"items": items, "model": src, "model_version": v, "max": C.TEACH_MAX,
                "lcd_check_acc": round(accuracy(m, X, Y), 4)}

    def teach_add(self, body):
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object")
        label = _int(body.get("label"), "label", 0, 9)
        item = self.teach.add(body.get("pixels"), label, body.get("source", "drawn"))
        return {"ok": True, "id": item["id"], "count": len(self.teach.items)}

    def teach_delete(self, body):
        item_id = _int((body or {}).get("id"), "id", 0, 10 ** 9)
        self.teach.delete(item_id)
        return {"ok": True}

    def teach_clear(self):
        self.teach.clear()
        return {"ok": True}

    def teach_demo(self):
        """Add 2 LCD-style examples of every digit: a style absent from training."""
        rng = random.Random(77)
        added = 0
        for k in range(2):
            for d in range(10):
                self.teach.add(render_digit(d, rng, "lcd", noise=False), d, "lcd-demo")
                added += 1
        return {"ok": True, "added": added, "count": len(self.teach.items)}

    def teach_finetune(self, body):
        body = body or {}
        steps = _int(body.get("steps"), "steps", 1, 300, C.FINETUNE_STEPS)
        lr = _float(body.get("lr"), "lr", 0.0001, 1.0, C.FINETUNE_LR)
        replay = _int(body.get("replay"), "replay", 0, 256, C.FINETUNE_REPLAY)
        m, v, src = self._active()
        examples = self.teach.snapshot()
        new, report = finetune(m, examples, self.train_X, self.train_Y, self.test_X, self.test_Y,
                               steps=steps, lr=lr, replay=replay, seed=v)
        X, Y = self._lcd_check()
        report["lcd_check_before"] = round(accuracy(m, X, Y), 4)
        report["lcd_check_after"] = round(accuracy(new, X, Y), 4)
        report["model_version"] = self._swap(new, "fine-tuned on %d drawings" % len(examples))
        report["source"] = self.source
        return report


class ConflictError(Exception):
    """Maps to HTTP 409."""
