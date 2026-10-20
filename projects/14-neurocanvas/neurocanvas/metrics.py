"""Evaluation helpers: accuracy, confusion matrix, per-class scores, latency."""

import time

from .mlp import log_softmax


def evaluate(model, X, Y, n_classes=10, keep_wrong=40):
    """One pass over (X, Y). Returns accuracy, mean loss, confusion matrix,
    per-class precision/recall and the misclassified examples (most confident first)."""
    cm = [[0] * n_classes for _ in range(n_classes)]
    loss = 0.0
    wrong = []
    t0 = time.perf_counter()
    for i, (x, y) in enumerate(zip(X, Y)):
        z = model.forward(x)[0][-1]
        lp = log_softmax(z)
        loss -= lp[y]
        pred = max(range(n_classes), key=lp.__getitem__)
        cm[y][pred] += 1
        if pred != y:
            wrong.append({"index": i, "true": y, "pred": pred,
                          "conf": round(2.718281828459045 ** lp[pred], 4),
                          "p_true": round(2.718281828459045 ** lp[y], 4)})
    elapsed = time.perf_counter() - t0
    n = len(Y)
    correct = sum(cm[k][k] for k in range(n_classes))
    per_class = []
    for k in range(n_classes):
        support = sum(cm[k])
        predicted = sum(cm[r][k] for r in range(n_classes))
        recall = cm[k][k] / support if support else 0.0
        precision = cm[k][k] / predicted if predicted else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({"digit": k, "n": support, "accuracy": round(recall, 4),
                          "precision": round(precision, 4), "recall": round(recall, 4),
                          "f1": round(f1, 4)})
    pairs = sorted(((cm[a][b], a, b) for a in range(n_classes) for b in range(n_classes) if a != b),
                   reverse=True)
    wrong.sort(key=lambda w: -w["conf"])
    return {
        "n": n, "correct": correct, "accuracy": round(correct / n, 4) if n else 0.0,
        "loss": round(loss / n, 4) if n else 0.0,
        "confusion": cm, "per_class": per_class,
        "top_confusions": [{"true": a, "pred": b, "count": c} for c, a, b in pairs[:5] if c],
        "misclassified": wrong[:keep_wrong], "n_wrong": len(wrong),
        "ms_per_image": round(1000.0 * elapsed / n, 4) if n else 0.0,
    }


def accuracy(model, X, Y):
    ok = 0
    for x, y in zip(X, Y):
        z = model.forward(x)[0][-1]
        if max(range(len(z)), key=z.__getitem__) == y:
            ok += 1
    return ok / len(Y) if Y else 0.0
