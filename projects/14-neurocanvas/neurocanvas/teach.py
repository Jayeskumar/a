"""'Teach it' mode: store user-labelled drawings and fine-tune on them.

Fine-tuning = a few SGD steps on the user's examples, each step mixed with a
random "replay" batch of original training images so the network does not
forget everything else (catastrophic forgetting). Each user example is also
shifted by up to 1 pixel per step (cheap augmentation).
"""

import json
import os
import random
import threading
import time

from . import config as C
from .metrics import accuracy
from .mlp import SGDMomentum, softmax


def shift(img, dx, dy, grid=C.GRID):
    out = [0.0] * (grid * grid)
    for y in range(grid):
        sy = y - dy
        if 0 <= sy < grid:
            for x in range(grid):
                sx = x - dx
                if 0 <= sx < grid:
                    out[y * grid + x] = img[sy * grid + sx]
    return out


def validate_pixels(px, n=C.GRID * C.GRID):
    if not isinstance(px, list) or len(px) != n:
        raise ValueError("pixels must be a list of %d numbers" % n)
    out = []
    for v in px:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            raise ValueError("pixels must be numbers")
        out.append(min(1.0, max(0.0, float(v))))
    return out


class TeachStore:
    """User examples persisted in data/teach.json (created on first add)."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.items = []
        self.next_id = 1
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                self.items = [it for it in d.get("items", []) if len(it.get("pixels", [])) == C.GRID * C.GRID]
                self.next_id = max([it["id"] for it in self.items] + [0]) + 1
            except (OSError, ValueError, KeyError, TypeError):
                self.items = []

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": self.items}, f, separators=(",", ":"))
        os.replace(tmp, self.path)

    def add(self, pixels, label, source="drawn"):
        label = int(label)
        if not 0 <= label <= 9:
            raise ValueError("label must be 0-9")
        px = validate_pixels(pixels)
        if sum(px) <= 0:
            raise ValueError("the drawing is empty")
        with self.lock:
            if len(self.items) >= C.TEACH_MAX:
                raise ValueError("teach set is full (%d examples) - clear it first" % C.TEACH_MAX)
            item = {"id": self.next_id, "label": label, "source": str(source)[:20],
                    "pixels": [round(v, 3) for v in px], "added": int(time.time())}
            self.next_id += 1
            self.items.append(item)
            self._save()
            return item

    def delete(self, item_id):
        with self.lock:
            n = len(self.items)
            self.items = [it for it in self.items if it["id"] != item_id]
            if len(self.items) == n:
                raise KeyError(item_id)
            self._save()

    def clear(self):
        with self.lock:
            self.items = []
            self._save()

    def snapshot(self):
        with self.lock:
            return [dict(it) for it in self.items]


def finetune(model, examples, replay_X, replay_Y, test_X=None, test_Y=None, steps=C.FINETUNE_STEPS,
             lr=C.FINETUNE_LR, replay=C.FINETUNE_REPLAY, seed=0):
    """Fine-tune a *copy* of model. Returns (new_model, report)."""
    if not examples:
        raise ValueError("add at least one labelled drawing first")
    rng = random.Random(seed)
    new = model.copy()
    opt = SGDMomentum(new, lr=lr, momentum=0.9, l2=C.L2)
    xs = [e["pixels"] for e in examples]
    ys = [e["label"] for e in examples]
    before = [softmax(model.forward(x)[0][-1]) for x in xs]
    t0 = time.perf_counter()
    losses = []
    for _ in range(steps):
        bx = [shift(x, rng.randint(-1, 1), rng.randint(-1, 1)) for x in xs]
        by = list(ys)
        if replay and replay_X:
            for _ in range(replay):
                i = rng.randrange(len(replay_X))
                bx.append(replay_X[i])
                by.append(replay_Y[i])
        loss, _, gW, gb = new.batch_gradients(bx, by)
        opt.step(gW, gb, len(bx))
        losses.append(round(loss / len(bx), 4))
    seconds = time.perf_counter() - t0
    after = [softmax(new.forward(x)[0][-1]) for x in xs]
    rows = []
    for e, pb, pa in zip(examples, before, after):
        y = e["label"]
        rows.append({"id": e["id"], "label": y,
                     "before": {"pred": max(range(10), key=pb.__getitem__), "p_label": round(pb[y], 4)},
                     "after": {"pred": max(range(10), key=pa.__getitem__), "p_label": round(pa[y], 4)}})
    report = {"steps": steps, "lr": lr, "replay": replay, "seconds": round(seconds, 2), "losses": losses,
              "examples": rows,
              "fixed": sum(1 for r in rows if r["before"]["pred"] != r["label"] and r["after"]["pred"] == r["label"]),
              "correct_before": sum(1 for r in rows if r["before"]["pred"] == r["label"]),
              "correct_after": sum(1 for r in rows if r["after"]["pred"] == r["label"])}
    if test_X:
        report["test_acc_before"] = round(accuracy(model, test_X, test_Y), 4)
        report["test_acc_after"] = round(accuracy(new, test_X, test_Y), 4)
    return new, report
