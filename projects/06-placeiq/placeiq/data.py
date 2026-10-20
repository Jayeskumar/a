"""Synthetic student dataset (documented latent model) and CSV import/validation.

Latent model (all synthetic, illustrative - NOT real placement statistics)
-------------------------------------------------------------------------
Every student gets three hidden traits drawn from a standard normal:

* ``A`` academic ability
* ``C`` coding drive, correlated with A (rho = 0.35) and shifted by department
  (CS-family departments practise more coding; mechanical least)
* ``S`` soft skills, mildly correlated with A (rho = 0.20)

An "exam-focused" 18 % of students get A + 0.7 and C - 0.9 (marks over building).

Observed columns are noisy functions of those traits (see ``_student``), e.g.
CGPA = 7.2 + 0.85*A + noise, coding problems = exp(4.6 + 0.8*C + noise).

Placement is a Bernoulli draw from ``sigmoid(z)`` where ``z`` is a hand-written
"recruiter" score using the *observed* columns, with two non-linear eligibility
cut-offs that many campus drives use (more than 2 backlogs, CGPA below 6) and a
small department "market" term (fewer software-firm openings for core branches).
The model we train never sees ``dept`` and only gets linear features, so it has
to approximate this truth - which is what makes the evaluation honest.
"""

import csv
import io
import math
import random

from . import config as C

# Department mix for the 600 synthetic students (sums to 600).
DEPT_COUNTS = {"CSE": 150, "AI&DS": 100, "CSD": 70, "IT": 90, "ECE": 110, "MECH": 80}
# Shift of the latent coding trait by department (assumption).
DEPT_CODING_SHIFT = {"CSE": 0.35, "AI&DS": 0.30, "CSD": 0.20, "IT": 0.20, "ECE": -0.10, "MECH": -0.60}
# Department hiring-market term in the placement logit (assumption, small on purpose).
DEPT_MARKET = {"CSE": 0.0, "AI&DS": 0.0, "CSD": 0.0, "IT": 0.0, "ECE": -0.15, "MECH": -0.40}
PLACEMENT_INTERCEPT = 0.80   # tuned so the overall placement rate lands near 55-65 %
BATCHES = ["2025", "2026"]
# A sub-population that optimises for exam marks rather than building (assumption):
# raises academic ability, lowers coding drive. Creates the "toppers lacking projects" persona.
EXAM_FOCUSED_SHARE = 0.18
EXAM_FOCUSED_SHIFT = (0.7, -0.9)

_FIRST = ["Aarav", "Diya", "Kavin", "Nila", "Harish", "Meera", "Sanjay", "Priya", "Arjun",
          "Divya", "Karthik", "Lakshmi", "Vikram", "Anu", "Rohit", "Sneha", "Pranav", "Keerthi",
          "Gokul", "Swathi", "Naveen", "Janani", "Surya", "Abinaya", "Rahul", "Ishwarya",
          "Dinesh", "Pooja", "Bala", "Yamini", "Ashwin", "Kavya", "Manoj", "Revathi", "Tarun",
          "Monika", "Vignesh", "Harini", "Ajay", "Deepika"]
_LAST = ["K", "S", "R", "M", "P", "V", "N", "A", "T", "G", "B", "J", "D", "L"]


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _poisson(rng, lam, cap):
    """Knuth's Poisson sampler (fine for the small lambdas used here)."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return min(k, cap)
        k += 1


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def true_placement_logit(s):
    """The hidden "recruiter" score used to generate placements (documented truth)."""
    z = PLACEMENT_INTERCEPT
    z += 1.00 * (s["cgpa"] - 7.2)
    z += 0.90 * (math.log1p(s["coding_problems"]) - 4.7)
    z += 0.35 * s["internships"]
    z += 0.30 * (s["projects"] - 2)
    z += 0.12 * s["certifications"]
    z += 0.20 * s["hackathons"]
    z += 0.045 * (s["aptitude_score"] - 60)
    z += 0.035 * (s["communication_score"] - 62)
    z += 0.050 * (s["mock_interview_score"] - 58)
    z -= 0.55 * s["backlogs"]
    if s["backlogs"] > 2:
        z -= 1.5
    if s["cgpa"] < 6.0:
        z -= 1.2
    z += DEPT_MARKET.get(s["dept"], 0.0)
    return z


def _student(rng, idx, dept):
    a = rng.gauss(0, 1)
    c = 0.35 * a + math.sqrt(1 - 0.35 ** 2) * rng.gauss(0, 1) + DEPT_CODING_SHIFT[dept]
    if rng.random() < EXAM_FOCUSED_SHARE:  # studies for marks, builds little
        a += EXAM_FOCUSED_SHIFT[0]
        c += EXAM_FOCUSED_SHIFT[1]
    s = 0.20 * a + math.sqrt(1 - 0.20 ** 2) * rng.gauss(0, 1)
    n = rng.gauss
    row = {
        "student_id": "KSR%s%03d" % (dept.replace("&", ""), idx),
        "name": "%s %s" % (rng.choice(_FIRST), rng.choice(_LAST)),
        "dept": dept,
        "batch": rng.choice(BATCHES),
        "tenth_pct": round(_clip(80 + 8 * a + 5 * n(0, 1), 50, 100), 1),
        "twelfth_pct": round(_clip(76 + 9 * a + 6 * n(0, 1), 45, 100), 1),
        "cgpa": round(_clip(7.2 + 0.85 * a + 0.4 * n(0, 1), 5.0, 10.0), 2),
        "backlogs": _poisson(rng, math.exp(-0.5 - 1.1 * a), 8),
        "coding_problems": int(_clip(math.exp(4.6 + 0.8 * c + 0.3 * n(0, 1)), 0, 1500)),
        "projects": _poisson(rng, math.exp(0.6 + 0.45 * c + 0.10 * a), 10),
        "internships": _poisson(rng, math.exp(-0.7 + 0.40 * c + 0.20 * s), 4),
        "certifications": _poisson(rng, math.exp(0.4 + 0.25 * c + 0.20 * a), 10),
        "hackathons": _poisson(rng, math.exp(-0.5 + 0.55 * c + 0.20 * s), 10),
        "aptitude_score": round(_clip(60 + 10 * a + 6 * c + 8 * n(0, 1), 20, 100), 1),
        "communication_score": round(_clip(62 + 12 * s + 8 * n(0, 1), 20, 100), 1),
        "mock_interview_score": round(_clip(58 + 6 * c + 8 * s + 3 * a + 8 * n(0, 1), 15, 100), 1),
    }
    placed = rng.random() < _sigmoid(true_placement_logit(row))
    row["placed"] = 1 if placed else 0
    if placed:
        lp = (math.log(3.6) + 0.15 * (row["cgpa"] - 7.2)
              + 0.25 * (math.log1p(row["coding_problems"]) - 4.7)
              + 0.10 * row["internships"] + 0.04 * row["projects"]
              + 0.006 * (row["mock_interview_score"] - 58)
              + (0.15 if dept in ("CSE", "AI&DS", "CSD", "IT") else 0.0)
              + rng.gauss(0, 0.18))
        row["package_lpa"] = round(_clip(math.exp(lp), 3.0, 30.0), 2)
    else:
        row["package_lpa"] = 0.0
    return row


def generate(n=C.N_STUDENTS, seed=C.SEED):
    """Deterministic synthetic cohort. Same seed -> identical rows."""
    rng = random.Random(seed)
    total = sum(DEPT_COUNTS.values())
    rows = []
    for dept, cnt in DEPT_COUNTS.items():
        k = max(1, round(cnt * n / total))
        for i in range(k):
            rows.append(_student(rng, i + 1, dept))
    rng.shuffle(rows)
    return rows[:n] if len(rows) > n else rows


def to_csv(rows, columns=None):
    columns = columns or C.ALL_COLUMNS
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    return buf.getvalue()


# ----------------------------------------------------------------------------
# CSV import with row-level validation
# ----------------------------------------------------------------------------
HEADER_ALIASES = {
    "id": "student_id", "roll_no": "student_id", "rollno": "student_id", "register_no": "student_id",
    "department": "dept", "branch": "dept", "year": "batch",
    "10th": "tenth_pct", "10th_pct": "tenth_pct", "tenth": "tenth_pct",
    "12th": "twelfth_pct", "12th_pct": "twelfth_pct", "twelfth": "twelfth_pct",
    "coding": "coding_problems", "problems_solved": "coding_problems",
    "aptitude": "aptitude_score", "communication": "communication_score",
    "mock_interview": "mock_interview_score", "package": "package_lpa", "lpa": "package_lpa",
}
MAX_UPLOAD_ROWS = 20000


def _norm_header(h):
    h = h.strip().lstrip("﻿").lower().replace(" ", "_").replace("-", "_")
    return HEADER_ALIASES.get(h, h)


def normalise_dept(v):
    key = v.strip().upper().replace(" ", "")
    return C.DEPT_ALIASES.get(key)


def parse_bool(v):
    t = v.strip().lower()
    if t in ("1", "yes", "y", "true", "placed", "t"):
        return 1
    if t in ("0", "no", "n", "false", "not placed", "unplaced", "f"):
        return 0
    return None


def validate_csv(text):
    """Parse CSV text. Returns (valid_rows, report).

    ``report`` = {total_rows, valid_rows, invalid_rows, errors:[{line, student_id, problems}],
    missing_columns, ignored_columns, warnings}. Never raises on bad content.
    """
    report = {"total_rows": 0, "valid_rows": 0, "invalid_rows": 0, "errors": [],
              "missing_columns": [], "ignored_columns": [], "warnings": []}
    if not isinstance(text, str) or not text.strip():
        report["missing_columns"] = list(C.REQUIRED_COLUMNS)
        report["warnings"].append("File is empty.")
        return [], report
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as e:
        report["warnings"].append("Could not read header: %s" % e)
        return [], report
    cols = [_norm_header(h) for h in header]
    missing = [c for c in C.REQUIRED_COLUMNS if c not in cols]
    report["missing_columns"] = missing
    report["ignored_columns"] = [h for h, c in zip(header, cols) if c not in C.ALL_COLUMNS]
    if missing:
        return [], report
    index = {c: i for i, c in enumerate(cols) if c in C.ALL_COLUMNS}
    rows, seen = [], set()
    line = 1
    while True:
        try:
            raw = next(reader)
        except StopIteration:
            break
        except csv.Error as e:
            line += 1
            report["total_rows"] += 1
            report["invalid_rows"] += 1
            report["errors"].append({"line": line, "student_id": "", "problems": ["unreadable CSV row: %s" % e]})
            continue
        line += 1
        if not raw or all(not x.strip() for x in raw):
            continue
        report["total_rows"] += 1
        if report["total_rows"] > MAX_UPLOAD_ROWS:
            report["warnings"].append("Only the first %d rows were read." % MAX_UPLOAD_ROWS)
            report["total_rows"] -= 1
            break
        row, problems = _validate_row(raw, index, line)
        sid = row.get("student_id")
        if sid in seen:
            problems.append("duplicate student_id '%s'" % sid)
        if problems:
            report["invalid_rows"] += 1
            if len(report["errors"]) < 200:
                report["errors"].append({"line": line, "student_id": sid or "", "problems": problems})
            continue
        seen.add(sid)
        rows.append(row)
    report["valid_rows"] = len(rows)
    if len(report["errors"]) < report["invalid_rows"]:
        report["warnings"].append("Showing the first %d of %d bad rows."
                                  % (len(report["errors"]), report["invalid_rows"]))
    return rows, report


def _cell(raw, index, col):
    i = index.get(col)
    if i is None or i >= len(raw):
        return ""
    return raw[i].strip()


def _validate_row(raw, index, line):
    problems = []
    row = {}
    row["student_id"] = _cell(raw, index, "student_id") or "ROW%05d" % line
    row["name"] = _cell(raw, index, "name") or row["student_id"]
    d = normalise_dept(_cell(raw, index, "dept"))
    if d is None:
        problems.append("dept '%s' is not one of %s" % (_cell(raw, index, "dept"), ", ".join(C.DEPARTMENTS)))
    row["dept"] = d
    row["batch"] = _cell(raw, index, "batch") or "unknown"
    for col in C.FEATURE_NAMES:
        v = _cell(raw, index, col)
        if v == "":
            problems.append("%s is empty" % col)
            continue
        try:
            x = float(v)
        except ValueError:
            problems.append("%s '%s' is not a number" % (col, v))
            continue
        if math.isnan(x) or math.isinf(x):
            problems.append("%s is not a finite number" % col)
            continue
        lo, hi = C.FEATURE_RANGES[col]
        if x < lo or x > hi:
            problems.append("%s=%s outside %s-%s" % (col, v, lo, hi))
            continue
        if col in C.INTEGER_FEATURES:
            if abs(x - round(x)) > 1e-9:
                problems.append("%s=%s must be a whole number" % (col, v))
                continue
            x = int(round(x))
        row[col] = x
    pc = _cell(raw, index, "placed")
    p = parse_bool(pc) if pc else None  # blank = current batch, outcome pending (scored, not trained on)
    if pc and p is None:
        problems.append("placed '%s' must be yes/no, 1/0 or blank (pending)" % pc)
    row["placed"] = p
    pk = _cell(raw, index, "package_lpa")
    if pk == "":
        row["package_lpa"] = None if p == 1 else 0.0
    else:
        try:
            pkv = float(pk)
            if pkv < 0 or pkv > 200 or math.isnan(pkv):
                problems.append("package_lpa=%s outside 0-200" % pk)
            elif p != 1 and pkv > 0:
                problems.append("package_lpa is %s but the student is not placed" % pk)
            row["package_lpa"] = pkv
        except ValueError:
            problems.append("package_lpa '%s' is not a number" % pk)
    return row, problems
