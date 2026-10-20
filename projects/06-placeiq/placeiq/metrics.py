"""Classification and regression metrics, written out by hand."""


def confusion(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _div(a, b):
    return a / b if b else 0.0


def classification_report(y_true, y_pred):
    c = confusion(y_true, y_pred)
    n = len(y_true)
    precision = _div(c["tp"], c["tp"] + c["fp"])
    recall = _div(c["tp"], c["tp"] + c["fn"])
    return {
        "n": n,
        "accuracy": _div(c["tp"] + c["tn"], n),
        "precision": precision,
        "recall": recall,
        "f1": _div(2 * precision * recall, precision + recall),
        "fpr": _div(c["fp"], c["fp"] + c["tn"]),
        "fnr": _div(c["fn"], c["fn"] + c["tp"]),
        "confusion": c,
    }


def roc_auc(y_true, scores):
    """AUC = P(score of random positive > score of random negative), ties count 1/2.
    Computed with average ranks (Mann-Whitney U), O(n log n)."""
    pairs = sorted(zip(scores, y_true))
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    n_pos = sum(1 for _, t in pairs if t == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    rank_sum = sum(r for r, (_, t) in zip(ranks, pairs) if t == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def roc_curve(y_true, scores):
    """List of {fpr, tpr, threshold} points from (0,0) to (1,1)."""
    pos = sum(1 for t in y_true if t == 1)
    neg = len(y_true) - pos
    order = sorted(zip(scores, y_true), key=lambda p: -p[0])
    pts = [{"fpr": 0.0, "tpr": 0.0, "threshold": 1.0}]
    tp = fp = 0
    i = 0
    while i < len(order):
        thr = order[i][0]
        while i < len(order) and order[i][0] == thr:
            if order[i][1] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        pts.append({"fpr": _div(fp, neg), "tpr": _div(tp, pos), "threshold": thr})
    return pts


def r2_score(y, yhat):
    m = sum(y) / len(y)
    ss_tot = sum((v - m) ** 2 for v in y)
    ss_res = sum((a - b) ** 2 for a, b in zip(y, yhat))
    return 1 - _div(ss_res, ss_tot) if ss_tot else 0.0


def mae(y, yhat):
    return sum(abs(a - b) for a, b in zip(y, yhat)) / len(y)


def rmse(y, yhat):
    return (sum((a - b) ** 2 for a, b in zip(y, yhat)) / len(y)) ** 0.5
