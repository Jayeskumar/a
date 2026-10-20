"""Deterministic synthetic crop-recommendation dataset.

Each crop has an approximate range per feature (config.CROP_RANGES). A sample is drawn
uniformly inside every range and then jittered with gaussian noise (NOISE_FRACTION of the
range width) so neighbouring crops overlap, like real field data would. Fixed seed =>
identical data on every machine.

Run `python -m krishimitra.dataset` to (re)write data/crop_dataset.csv.
"""
import csv
import os
import random

from . import config


def generate(seed=config.DATASET_SEED, per_crop=config.SAMPLES_PER_CROP,
             noise=config.NOISE_FRACTION):
    """Return (X, y): X is a list of 7-float rows, y the crop label strings."""
    rng = random.Random(seed)
    X, y = [], []
    for crop in config.CROPS:
        ranges = config.CROP_RANGES[crop]
        for _ in range(per_crop):
            row = []
            for fi, (lo, hi) in enumerate(ranges):
                v = rng.uniform(lo, hi) + rng.gauss(0, noise * (hi - lo))
                flo, fhi = config.FEATURE_LIMITS[config.FEATURES[fi]]
                row.append(round(min(max(v, flo), fhi), 2))
            X.append(row)
            y.append(crop)
    return X, y


def stratified_split(X, y, test_fraction=config.TEST_FRACTION, seed=config.DATASET_SEED):
    """Shuffle within each class and hold out `test_fraction` of every class."""
    rng = random.Random(seed + 1)
    by_class = {}
    for i, label in enumerate(y):
        by_class.setdefault(label, []).append(i)
    train_idx, test_idx = [], []
    for label in sorted(by_class):
        idx = by_class[label][:]
        rng.shuffle(idx)
        n_test = int(round(len(idx) * test_fraction))
        test_idx.extend(idx[:n_test])
        train_idx.extend(idx[n_test:])
    train_idx.sort()
    test_idx.sort()
    return ([X[i] for i in train_idx], [y[i] for i in train_idx],
            [X[i] for i in test_idx], [y[i] for i in test_idx])


def write_csv(path):
    X, y = generate()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(config.FEATURES + ["label"])
        for row, label in zip(X, y):
            w.writerow(row + [label])
    return len(X)


def default_csv_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "crop_dataset.csv")


if __name__ == "__main__":
    n = write_csv(default_csv_path())
    print("wrote %d rows to %s" % (n, default_csv_path()))
