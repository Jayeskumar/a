"""Regenerate the committed sample files (deterministic).

    python data/make_samples.py

* data/students_demo.csv            - the 600-student synthetic demo cohort (seed 2026)
* static/samples/students_with_errors.csv - a 140-row "other college" file (seed 7) with
  20 pending-outcome rows and 8 deliberately broken rows, used by the
  "Try a file with errors" button to demo CSV validation.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from placeiq import data  # noqa: E402


def main():
    rows = data.generate()
    with open(os.path.join(HERE, "students_demo.csv"), "w", newline="", encoding="utf-8") as f:
        f.write(data.to_csv(rows))

    other = data.generate(n=140, seed=7)
    for i, r in enumerate(other):
        r["student_id"] = "OTH%04d" % (i + 1)
    for r in other[-20:]:          # current batch: outcome not known yet
        r["batch"] = "2027"
        r["placed"] = ""
        r["package_lpa"] = ""
    other[3]["dept"] = "CIVIL"
    other[11]["cgpa"] = 11.2
    other[19]["coding_problems"] = "abc"
    other[27]["backlogs"] = 1.5
    other[35]["placed"] = "maybe"
    other[44]["aptitude_score"] = ""
    other[52]["student_id"] = other[51]["student_id"]
    other[60]["placed"] = 0
    other[60]["package_lpa"] = 6.5
    out = os.path.join(ROOT, "static", "samples", "students_with_errors.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        f.write(data.to_csv(other))
    print("wrote", len(rows), "demo rows and", len(other), "sample-upload rows")


if __name__ == "__main__":
    main()
