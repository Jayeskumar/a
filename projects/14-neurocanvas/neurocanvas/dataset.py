"""Deterministic synthetic digit dataset, cached as one small gzip file.

File format (``data/digits.bin.gz``), gzip with mtime=0 so it is byte-stable:
    line 1: JSON header {"format": "neurocanvas-digits", "version": 1, "grid": 16, ...}
    then  : n_train + n_test label bytes, then 256 pixel bytes (0..255) per image,
            train images first, test images after.

Rebuild it with:  python -m neurocanvas.dataset
"""

import gzip
import json
import os
import sys
import time

from . import config as C
from .render import render_digit, sample_rng

FORMAT = "neurocanvas-digits"
VERSION = 1
LUT = [i / 255.0 for i in range(256)]     # byte -> float lookup (fast decode)


class Dataset:
    """Images stored as ``bytes`` (compact); decode to floats with ``x(i)``."""

    def __init__(self, train_y, train_b, test_y, test_b, header=None):
        self.train_y, self.train_b = list(train_y), list(train_b)
        self.test_y, self.test_b = list(test_y), list(test_b)
        self.header = header or {}

    @staticmethod
    def decode(b):
        return list(map(LUT.__getitem__, b))

    def train_x(self, i):
        return self.decode(self.train_b[i])

    def test_x(self, i):
        return self.decode(self.test_b[i])

    def arrays(self, split="train", limit=None):
        ys, bs = (self.train_y, self.train_b) if split == "train" else (self.test_y, self.test_b)
        n = len(ys) if limit is None else min(limit, len(ys))
        return [self.decode(b) for b in bs[:n]], ys[:n]

    def __len__(self):
        return len(self.train_y) + len(self.test_y)


def quantise(img):
    return bytes(min(255, max(0, int(v * 255.0 + 0.5))) for v in img)


def generate(per_class=C.PER_CLASS, test_per_class=C.TEST_PER_CLASS, seed=C.DATA_SEED,
             progress=None):
    """Render per_class images of each digit. Sample k of digit d uses its own seed."""
    train_y, train_b, test_y, test_b = [], [], [], []
    total = per_class * 10
    for k in range(per_class):
        for d in range(10):
            idx = k * 10 + d
            img = quantise(render_digit(d, sample_rng(seed, idx)))
            if k >= per_class - test_per_class:
                test_y.append(d)
                test_b.append(img)
            else:
                train_y.append(d)
                train_b.append(img)
            if progress and (idx + 1) % 500 == 0:
                progress(idx + 1, total)
    header = {"format": FORMAT, "version": VERSION, "grid": C.GRID, "fit": C.FIT, "seed": seed,
              "per_class": per_class, "test_per_class": test_per_class,
              "n_train": len(train_y), "n_test": len(test_y)}
    return Dataset(train_y, train_b, test_y, test_b, header)


def save(ds, path):
    head = (json.dumps(ds.header, sort_keys=True) + "\n").encode("utf-8")
    body = bytes(ds.train_y) + bytes(ds.test_y) + b"".join(ds.train_b) + b"".join(ds.test_b)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(gzip.compress(head + body, compresslevel=9, mtime=0))
    os.replace(tmp, path)


def load(path):
    with open(path, "rb") as f:
        raw = gzip.decompress(f.read())
    nl = raw.index(b"\n")
    header = json.loads(raw[:nl].decode("utf-8"))
    if header.get("format") != FORMAT:
        raise ValueError("not a NeuroCanvas digit file")
    g2 = header["grid"] * header["grid"]
    ntr, nte = header["n_train"], header["n_test"]
    body = raw[nl + 1:]
    if len(body) != (ntr + nte) * (1 + g2):
        raise ValueError("digit file is truncated")
    labels = body[:ntr + nte]
    px = body[ntr + nte:]
    imgs = [px[i * g2:(i + 1) * g2] for i in range(ntr + nte)]
    return Dataset(labels[:ntr], imgs[:ntr], labels[ntr:], imgs[ntr:], header)


def load_or_generate(path, log=print):
    """Load the committed cache; regenerate (about 15 s) if missing or stale."""
    if os.path.exists(path):
        try:
            ds = load(path)
            h = ds.header
            if h.get("grid") == C.GRID and h.get("seed") == C.DATA_SEED and h.get("per_class") == C.PER_CLASS:
                return ds
            log("  dataset settings changed - regenerating")
        except (OSError, ValueError, KeyError) as e:
            log("  dataset cache unreadable (%s) - regenerating" % e)
    log("  generating %d synthetic digits (one-off, ~15 s)..." % (C.PER_CLASS * 10))
    ds = generate(progress=lambda i, n: log("    %d / %d" % (i, n)))
    save(ds, path)
    return ds


def main(argv):
    out = argv[0] if argv else os.path.join(os.path.dirname(__file__), "..", "data", "digits.bin.gz")
    t = time.time()
    ds = generate(progress=lambda i, n: print("  %d / %d" % (i, n), flush=True))
    save(ds, out)
    print("wrote %s: %d train + %d test images in %.1f s (%d bytes)"
          % (os.path.normpath(out), len(ds.train_y), len(ds.test_y), time.time() - t, os.path.getsize(out)))


if __name__ == "__main__":
    main(sys.argv[1:])
