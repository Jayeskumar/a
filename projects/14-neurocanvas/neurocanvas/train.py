"""Mini-batch SGD training loop, plus the CLI that builds data/weights.json.

    python -m neurocanvas.train          # ~1 minute on a laptop, pure Python
"""

import json
import math
import os
import random
import sys
import time

from . import config as C
from .metrics import accuracy, evaluate
from .mlp import MLP, SGDMomentum

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")


class Diverged(Exception):
    """The loss became NaN or infinite: the learning rate is too high."""


def train_epoch(model, opt, X, Y, batch, rng, on_batch=None, should_stop=None):
    """One shuffled pass. Returns (mean loss, train accuracy, stopped?). Raises Diverged."""
    order = list(range(len(X)))
    rng.shuffle(order)
    loss_sum = 0.0
    correct = 0
    seen = 0
    n_batches = (len(order) + batch - 1) // batch
    for bi, s in enumerate(range(0, len(order), batch)):
        if should_stop and should_stop():
            return (loss_sum / seen if seen else 0.0), (correct / seen if seen else 0.0), True
        idx = order[s:s + batch]
        loss, ok, gW, gb = model.batch_gradients([X[i] for i in idx], [Y[i] for i in idx])
        if not math.isfinite(loss):
            if on_batch:
                on_batch(bi + 1, n_batches, None)
            raise Diverged("loss became %s at batch %d" % (loss, bi + 1))
        opt.step(gW, gb, len(idx))
        loss_sum += loss
        correct += ok
        seen += len(idx)
        if on_batch:
            on_batch(bi + 1, n_batches, loss / len(idx))
    return loss_sum / seen, correct / seen, False


def fit(model, X, Y, Xte=None, Yte=None, epochs=10, batch=32, lr=0.05, momentum=0.9, l2=0.0,
        lr_decay=1.0, seed=0, on_epoch=None, on_batch=None, should_stop=None):
    """Train ``model`` in place. Returns the per-epoch history."""
    rng = random.Random(seed)
    opt = SGDMomentum(model, lr=lr, momentum=momentum, l2=l2)
    history = []
    for ep in range(1, epochs + 1):
        t0 = time.perf_counter()
        try:
            loss, acc, stopped = train_epoch(model, opt, X, Y, batch, rng, on_batch, should_stop)
        except Diverged:
            row = {"epoch": ep, "loss": None, "train_acc": None, "test_acc": None, "diverged": True,
                   "lr": round(opt.lr, 5), "seconds": round(time.perf_counter() - t0, 2)}
            history.append(row)
            if on_epoch:
                on_epoch(row)
            break
        row = {"epoch": ep, "loss": round(loss, 4), "train_acc": round(acc, 4),
               "lr": round(opt.lr, 5), "seconds": round(time.perf_counter() - t0, 2)}
        if Xte is not None:
            row["test_acc"] = round(accuracy(model, Xte, Yte), 4)
        if stopped:
            row["partial"] = True
        history.append(row)
        if on_epoch:
            on_epoch(row)
        if stopped:
            break
        opt.lr *= lr_decay
    return history


def train_main_model(ds, epochs=C.EPOCHS, log=print):
    X, Y = ds.arrays("train")
    Xte, Yte = ds.arrays("test")
    model = MLP(C.SIZES, C.ACTIVATION, seed=C.TRAIN_SEED)
    t0 = time.perf_counter()
    hist = fit(model, X, Y, Xte, Yte, epochs=epochs, batch=C.BATCH, lr=C.LR, momentum=C.MOMENTUM,
               l2=C.L2, lr_decay=C.LR_DECAY, seed=C.TRAIN_SEED,
               on_epoch=lambda r: log("  epoch %2d  loss %.4f  train %.3f  test %.3f  (%.1fs)"
                                      % (r["epoch"], r["loss"], r["train_acc"], r["test_acc"], r["seconds"])))
    seconds = time.perf_counter() - t0
    meta = {"history": hist, "train_seconds": round(seconds, 1), "epochs": epochs,
            "batch": C.BATCH, "lr": C.LR, "lr_decay": C.LR_DECAY, "momentum": C.MOMENTUM, "l2": C.L2,
            "seed": C.TRAIN_SEED, "n_train": len(Y), "n_test": len(Yte),
            "python": sys.version.split()[0]}
    return model, meta


def save_weights(model, meta, path):
    d = model.to_dict(digits=5)
    d["meta"] = meta
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, separators=(",", ":"))
    os.replace(tmp, path)


def load_weights(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return MLP.from_dict(d), d.get("meta", {})


def main(argv):
    from .dataset import load_or_generate
    ds = load_or_generate(os.path.join(DATA_DIR, "digits.bin.gz"))
    epochs = int(argv[0]) if argv else C.EPOCHS
    print("training %s on %d images for %d epochs..." % ("-".join(map(str, C.SIZES)), len(ds.train_y), epochs))
    model, meta = train_main_model(ds, epochs)
    path = os.path.join(DATA_DIR, "weights.json")
    save_weights(model, meta, path)
    model, _ = load_weights(path)                      # evaluate exactly what was saved (rounded)
    Xte, Yte = ds.arrays("test")
    ev = evaluate(model, Xte, Yte)
    print("saved %s (%d bytes); test accuracy after rounding: %.2f%%; %.1f s total training"
          % (os.path.normpath(path), os.path.getsize(path), 100 * ev["accuracy"], meta["train_seconds"]))


if __name__ == "__main__":
    main(sys.argv[1:])
