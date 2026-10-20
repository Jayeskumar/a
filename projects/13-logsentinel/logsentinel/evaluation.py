"""Measure detection quality against the generator's ground truth.

An alert MATCHES a label when it shares the source IP, its time window overlaps
the label's (with a small slack), and the alert's category is one the label
expects. From that we compute per-attack-type recall and detection precision,
false positives on a benign-only log, and parser throughput.
"""

import time

from .parsers import parse_text
from .engine import Analysis
from . import generator, config as C

SLACK_S = 120


def _overlap(a_start, a_end, b_start, b_end):
    return a_start <= b_end + SLACK_S and b_start <= a_end + SLACK_S


def _epoch(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso).timestamp()


def evaluate(seed=generator.SEED):
    g = generator.generate(seed)
    gt = g.ground_truth()
    attacker_ips = set(gt["attacker_ips"])

    t0 = time.perf_counter()
    events, pstats = parse_text(g.text())
    parse_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    an = Analysis(events, pstats)
    detect_s = time.perf_counter() - t1

    alerts = an.alerts
    alert_rows = []
    for a in alerts:
        alert_rows.append({
            "cat": a.category, "src": a.src,
            "start": a.start.timestamp() if a.start else 0,
            "end": a.end.timestamp() if a.end else 0,
        })

    # ---- per-label recall ----
    per_type = {}
    for lb in gt["labels"]:
        ls, le = _epoch(lb["start"]), _epoch(lb["end"])
        hit = any(
            r["src"] == lb["src"]
            and r["cat"] in lb["expected_categories"]
            and _overlap(r["start"], r["end"], ls, le)
            for r in alert_rows)
        d = per_type.setdefault(lb["type"], {"labels": 0, "detected": 0})
        d["labels"] += 1
        d["detected"] += 1 if hit else 0

    total_labels = sum(d["labels"] for d in per_type.values())
    total_detected = sum(d["detected"] for d in per_type.values())
    recall = total_detected / total_labels if total_labels else 0.0

    # ---- precision at IP level: an alert is a true positive if its source IP
    # is a labelled attacker; a false positive if it is a benign IP. ----
    tp = sum(1 for r in alert_rows if r["src"] in attacker_ips)
    fp = sum(1 for r in alert_rows if r["src"] and r["src"] not in attacker_ips)
    precision = tp / (tp + fp) if (tp + fp) else 1.0

    # ---- false positives on a benign-only log ----
    bevents, bstats = parse_text(g.benign_text())
    ban = Analysis(bevents, bstats)
    benign_fp = len(ban.alerts)
    benign_fp_detail = [{"rule": a.rule, "src": a.src, "cat": a.category}
                        for a in ban.alerts]

    # ---- throughput ----
    lines = len(g.records)
    throughput = lines / parse_s if parse_s else 0.0
    e2e = lines / (parse_s + detect_s) if (parse_s + detect_s) else 0.0

    return {
        "seed": seed,
        "lines": lines,
        "events_parsed": pstats["parsed"],
        "malformed": pstats["malformed"],
        "alerts": len(alerts),
        "incidents": len(an.incidents),
        "per_type": per_type,
        "recall": round(recall, 3),
        "labels_detected": "%d/%d" % (total_detected, total_labels),
        "precision": round(precision, 3),
        "true_positive_alerts": tp,
        "false_positive_alerts": fp,
        "benign_false_positives": benign_fp,
        "benign_fp_detail": benign_fp_detail,
        "parse_seconds": round(parse_s, 4),
        "detect_seconds": round(detect_s, 4),
        "throughput_lines_per_s": int(throughput),
        "end_to_end_lines_per_s": int(e2e),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(evaluate(), indent=2))
