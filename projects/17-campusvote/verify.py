"""Independent auditor: re-verify and recount an election from its public bulletin board.

    python verify.py                         # data/board.json
    python verify.py board-KSRCE.json        # a downloaded copy
    python verify.py http://192.168.1.5:8017 # fetch /api/board from a running server

Needs nothing but the board: the public keys are in its genesis entry. Exit code 0 = VERIFIED.
"""

import json
import os
import sys
import urllib.request

from campusvote.audit import audit


def load(src):
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src.rstrip("/") + "/api/board", timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(src, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def main(argv):
    src = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "board.json")
    doc = load(src)
    entries = doc["entries"] if isinstance(doc, dict) else doc
    rep = audit(entries)
    print("CampusVote independent audit of %s" % src)
    if rep.get("election"):
        print("  election %(eid)s - %(title)s (%(eligible)d eligible)" % rep["election"])
    for s in rep["steps"]:
        print("  [%s] %s\n        %s" % ("ok" if s["ok"] else "FAIL", s["title"], s["detail"]))
    if rep.get("tally"):
        man = entries[0]["data"]["election"]
        for p in man["posts"]:
            names = {c["id"]: c["name"] for c in p["candidates"]}
            row = ", ".join("%s %d" % (names[c], n) for c, n in rep["tally"]["counts"][p["id"]].items())
            print("  %s: %s" % (p["title"], row))
    print("VERDICT: %s (%d entries, %.1f ms)" % (rep["verdict"], len(entries), rep["ms"]))
    return 0 if rep["verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
