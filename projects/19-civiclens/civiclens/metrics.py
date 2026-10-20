"""Evaluation metrics written out by hand."""

import math


def accuracy(y, p):
    return sum(1 for a, b in zip(y, p) if a == b) / float(len(y)) if y else 0.0


def confusion(y, p, k):
    m = [[0] * k for _ in range(k)]
    for a, b in zip(y, p):
        m[a][b] += 1
    return m


def per_class(y, p, k):
    m = confusion(y, p, k)
    out = []
    for c in range(k):
        tp = m[c][c]
        fp = sum(m[r][c] for r in range(k)) - tp
        fn = sum(m[c]) - tp
        prec = tp / float(tp + fp) if tp + fp else 0.0
        rec = tp / float(tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out.append({"precision": prec, "recall": rec, "f1": f1, "support": sum(m[c])})
    return out


def macro_f1(y, p, k):
    pc = [r for r in per_class(y, p, k) if r["support"] > 0]
    return sum(r["f1"] for r in pc) / len(pc) if pc else 0.0


def roc_auc(y, s):
    """Rank-based AUC (Mann-Whitney U) with average ranks for ties."""
    pairs = sorted(zip(s, y))
    n_pos = sum(1 for v in y if v == 1)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    rank_sum, i, n = 0.0, 0, len(pairs)
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        rank_sum += avg * sum(1 for k in range(i, j + 1) if pairs[k][1] == 1)
        i = j + 1
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier(y, s):
    return sum((a - b) ** 2 for a, b in zip(y, s)) / float(len(y)) if y else 0.0


def log_loss(y, s):
    eps = 1e-12
    return -sum(math.log(max(eps, v)) if a == 1 else math.log(max(eps, 1 - v)) for a, v in zip(y, s)) / float(len(y))


def binary_prf(y, p):
    tp = sum(1 for a, b in zip(y, p) if a == 1 and b == 1)
    fp = sum(1 for a, b in zip(y, p) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y, p) if a == 1 and b == 0)
    prec = tp / float(tp + fp) if tp + fp else 0.0
    rec = tp / float(tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def same_cluster_pairs(labels):
    """Set of unordered index pairs (i<j) that share a cluster label (None = singleton)."""
    groups = {}
    for i, g in enumerate(labels):
        if g is not None:
            groups.setdefault(g, []).append(i)
    pairs = set()
    for members in groups.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                pairs.add((members[a], members[b]))
    return pairs


def pair_prf(true_labels, pred_labels):
    """Pairwise precision / recall / F1 of a clustering against ground truth."""
    t = same_cluster_pairs(true_labels)
    p = same_cluster_pairs(pred_labels)
    tp = len(t & p)
    prec = tp / float(len(p)) if p else 0.0
    rec = tp / float(len(t)) if t else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "true_pairs": len(t), "pred_pairs": len(p), "tp": tp}


def percentile(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(len(s) - 1, lo + 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def expected_calibration_error(conf, correct, bins=10):
    """ECE: |accuracy - confidence| averaged over equal-width confidence bins, weighted by size."""
    tot = len(conf)
    if not tot:
        return 0.0
    err = 0.0
    for b in range(bins):
        lo, hi = b / float(bins), (b + 1) / float(bins)
        idx = [i for i, c in enumerate(conf) if (lo < c <= hi) or (b == 0 and c == 0)]
        if idx:
            acc = sum(1 for i in idx if correct[i]) / float(len(idx))
            avg = sum(conf[i] for i in idx) / float(len(idx))
            err += len(idx) / float(tot) * abs(acc - avg)
    return err
