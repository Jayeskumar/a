"""Citizen segregation reports and the gamified ward leaderboard ("green points").

A report says: household H in ward W put item X into bin Y. The classifier decides the
correct bin; a correct report earns POINTS_CORRECT, a wrong one still earns POINTS_REPORT
for participating plus a tip. Reports persist in data/reports.json.
"""

import json
import os
import random
import re
import threading

from . import config as C
from .classifier import DATA, LABELS, classify
from .town import WARDS, date_of

# fictional segregation habits per ward, only used to generate the demo reports
_DEMO_COMPLIANCE = {"W1": 0.80, "W2": 0.62, "W3": 0.88, "W4": 0.72, "W5": 0.56, "W6": 0.91}
_HH_RE = re.compile(r"^[A-Za-z0-9\-]{1,20}$")


class ReportError(ValueError):
    pass


def _ward_ids():
    return [w[0] for w in WARDS]


def demo_reports(n=None):
    """Deterministic demo reports spread over the 28 days before day 0."""
    r = random.Random(C.SEED * 7 + 3)
    items = [t for t, _ in DATA]
    out = []
    wards = _ward_ids()
    weights = [w[5] for w in WARDS]
    for k in range(n or C.DEMO_REPORTS):
        wid = r.choices(wards, weights=weights)[0]
        hh = "%s-%03d" % (wid, r.randint(1, 60))
        item = r.choice(items)
        correct = classify(item)["label"]
        if r.random() < _DEMO_COMPLIANCE[wid]:
            used = correct
        else:
            used = r.choice([x for x in LABELS if x != correct])
        day = -28 + int(28 * k / (n or C.DEMO_REPORTS))
        out.append(_make(k + 1, wid, hh, item, used, correct, date_of(day).isoformat()))
    return out


def _make(rid, ward, hh, item, used, correct, date):
    ok = used == correct
    return {"id": rid, "date": date, "ward": ward, "household": hh, "item": item,
            "bin_used": used, "correct_bin": correct, "correct": ok,
            "points": C.POINTS_CORRECT if ok else C.POINTS_REPORT}


class ReportStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.reports = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.reports = data
                    return
            except (OSError, ValueError):
                pass
        self.reset()

    def reset(self):
        with self.lock:
            self.reports = demo_reports()
            self._save()

    def _save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.reports, f, ensure_ascii=False, indent=0)
        os.replace(tmp, self.path)

    def add(self, body, today):
        if not isinstance(body, dict):
            raise ReportError("body must be a JSON object")
        ward = body.get("ward")
        if ward not in _ward_ids():
            raise ReportError("'ward' must be one of %s" % ", ".join(_ward_ids()))
        item = body.get("item")
        if not isinstance(item, str) or not item.strip() or len(item) > 80:
            raise ReportError("'item' must be a non-empty string of at most 80 characters")
        used = body.get("bin_used")
        if used not in LABELS:
            raise ReportError("'bin_used' must be one of %s" % ", ".join(LABELS))
        hh = body.get("household") or "%s-guest" % ward
        if not isinstance(hh, str) or not _HH_RE.match(hh):
            raise ReportError("'household' must be 1-20 letters, digits or '-'")
        verdict = classify(item.strip())
        with self.lock:
            rid = (max(r["id"] for r in self.reports) + 1) if self.reports else 1
            rep = _make(rid, ward, hh, item.strip(), used, verdict["label"], today)
            self.reports.append(rep)
            self._save()
        return rep, verdict

    def leaderboard(self):
        by = {w[0]: {"ward": w[0], "name": w[1], "households": w[5], "points": 0, "reports": 0,
                     "correct": 0, "participants": set()} for w in WARDS}
        hh_pts = {}
        for r in self.reports:
            b = by.get(r["ward"])
            if not b:
                continue
            b["points"] += r["points"]
            b["reports"] += 1
            b["correct"] += 1 if r["correct"] else 0
            b["participants"].add(r["household"])
            hh_pts[r["household"]] = hh_pts.get(r["household"], 0) + r["points"]
        rows = []
        for b in by.values():
            comp = b["correct"] / b["reports"] if b["reports"] else 0.0
            rows.append({"ward": b["ward"], "name": b["name"], "points": b["points"],
                         "reports": b["reports"], "compliance": round(comp, 3),
                         "participants": len(b["participants"]),
                         "points_per_1000_households": round(1000.0 * b["points"] / b["households"], 1)})
        # rank by compliance-weighted points so spamming wrong reports does not win
        for row in rows:
            row["score"] = round(row["points"] * (0.5 + 0.5 * row["compliance"]), 1)
        rows.sort(key=lambda x: (-x["score"], x["ward"]))
        for i, row in enumerate(rows):
            row["rank"] = i + 1
            row["badge"] = ("Segregation Champion" if i == 0 else
                            "Green Star" if row["compliance"] >= 0.8 else
                            "Rising" if row["compliance"] >= 0.65 else "Needs a drive")
        top = sorted(hh_pts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        types = {}
        for r in self.reports:
            k = r["correct_bin"]
            t = types.setdefault(k, [0, 0])
            t[1] += 1
            if r["correct"]:
                t[0] += 1
        total = len(self.reports)
        ok = sum(1 for r in self.reports if r["correct"])
        return {"wards": rows, "top_households": [{"household": h, "points": p} for h, p in top],
                "total_reports": total, "overall_compliance": round(ok / total, 3) if total else 0,
                "by_bin": {k: {"correct": a, "total": b} for k, (a, b) in types.items()},
                "recent": list(reversed(self.reports[-8:])),
                "rules": {"correct": C.POINTS_CORRECT, "participation": C.POINTS_REPORT}}
