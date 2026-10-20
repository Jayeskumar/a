"""Deterministic demo election: 200 synthetic students, 3 posts, 168 tokens, 152 ballots.

    python -m campusvote.demo          # regenerate data/ (keeps existing keys)
    python -m campusvote.demo --keys   # also regenerate the deterministic DEMO keys

Every random choice (roster, codes, who votes, how, blinding factors, nonces, mix order)
comes from ``random.Random(seed)``, so the same seed and base time give a byte-identical
board. Live voters always use ``secrets`` instead. Names and register numbers are made up.
"""

import argparse
import os
import random
import sys

from . import config, rsa
from .client import VoterDevice
from .util import sha256_hex, now

# Department sizes (sum 200) - a typical mid-size engineering college mix, purely illustrative.
DEPTS = [("CSE", 50), ("ECE", 40), ("MECH", 35), ("IT", 30), ("EEE", 25), ("AIDS", 20)]
FIRST = ["Aarthi", "Abinaya", "Akash", "Anitha", "Arun", "Bharath", "Deepika", "Dhanush", "Dinesh", "Divya",
         "Gokul", "Gowtham", "Harini", "Hari", "Janani", "Jeeva", "Kavin", "Kaviya", "Keerthana", "Kishore",
         "Lavanya", "Madhan", "Mathi", "Monisha", "Naveen", "Nithya", "Pooja", "Pradeep", "Priya", "Ragul",
         "Ramya", "Sabari", "Sandhya", "Santhosh", "Sneha", "Surya", "Swetha", "Tamil", "Vignesh", "Yazhini",
         "Ajmal", "Ayesha", "Fathima", "Imran", "Jerin", "Joel", "Sharon", "Steffi"]
INITIALS = "ABCDGJKMNPRSTV"

POSTS = [
    {"title": "President", "candidates": [
        {"name": "Aarthi Raman", "dept": "CSE", "slogan": "Open labs till 9 pm, every weekday"},
        {"name": "Vignesh Kumar", "dept": "MECH", "slogan": "Hostel Wi-Fi that actually works"},
        {"name": "Divya Shree", "dept": "ECE", "slogan": "A placement-prep cell run by students"}]},
    {"title": "General Secretary", "candidates": [
        {"name": "Harish Babu", "dept": "IT", "slogan": "Publish every club budget online"},
        {"name": "Keerthana S", "dept": "EEE", "slogan": "Safer late buses for day scholars"}]},
    {"title": "Cultural Secretary", "candidates": [
        {"name": "Nivetha P", "dept": "AIDS", "slogan": "One inter-college fest every semester"},
        {"name": "Sanjay R", "dept": "CSE", "slogan": "A music and dance room in every block"},
        {"name": "Mohammed Irfan", "dept": "ECE", "slogan": "Short-film club with real equipment"}]},
]

# Synthetic voting preferences (weights per candidate, NOTA last) by department.
# Made-up numbers chosen only so the demo produces a close, realistic-looking race.
PREFS = {
    "president": {"CSE": [52, 22, 21, 5], "IT": [48, 24, 23, 5], "AIDS": [44, 26, 25, 5],
                  "ECE": [26, 20, 49, 5], "EEE": [27, 45, 23, 5], "MECH": [16, 68, 11, 5]},
    "general-secretary": {"CSE": [46, 49, 5], "IT": [70, 25, 5], "AIDS": [55, 40, 5],
                          "ECE": [42, 53, 5], "EEE": [24, 71, 5], "MECH": [50, 45, 5]},
    "cultural-secretary": {"CSE": [30, 44, 22, 4], "IT": [36, 32, 28, 4], "AIDS": [62, 18, 16, 4],
                           "ECE": [28, 22, 46, 4], "EEE": [38, 28, 30, 4], "MECH": [34, 30, 32, 4]},
}


def choose_for(student, manifest, rng):
    """Pick a full set of choices for a simulated student (falls back to uniform)."""
    out = {}
    for p in manifest["posts"]:
        ids = [c["id"] for c in p["candidates"]]
        w = PREFS.get(p["id"], {}).get(student.get("dept"))
        if not w or len(w) != len(ids):
            w = [1] * len(ids)
        out[p["id"]] = rng.choices(ids, weights=w)[0]
    return out


def make_roster(rng, n=None):
    n = n or config.DEMO_STUDENTS
    total = sum(c for _, c in DEPTS)
    rows, serial = [], {}
    for dept, cnt in DEPTS:
        k = max(1, round(cnt * n / total))
        for i in range(k):
            year = 1 + (i % 4)
            joined = 27 - year  # synthetic format: 2-digit joining year + dept + serial, e.g. 24CSE007
            serial[(joined, dept)] = serial.get((joined, dept), 0) + 1
            reg = "%02d%s%03d" % (joined, dept, serial[(joined, dept)])
            rows.append({"reg_no": reg, "name": "%s %s" % (rng.choice(FIRST), rng.choice(INITIALS)),
                         "dept": dept, "year": year})
    return rows[:n]


def roster_csv(rows):
    lines = ["reg_no,name,dept,year"] + ["%s,%s,%s,%d" % (r["reg_no"], r["name"], r["dept"], r["year"]) for r in rows]
    return "\n".join(lines) + "\n"


class FakeClock(object):
    def __init__(self, t):
        self.t = int(t)

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += int(s)


def demo_keys(seed=config.DEMO_SEED, bits=None):
    rng = random.Random(seed * 7919 + 1)
    return {k: rsa.generate_keypair(bits or config.RSA_BITS, rng) for k in ("issuer", "board", "trustee")}


def build_demo(svc, base_time=None, seed=config.DEMO_SEED, n_students=None, n_tokens=None, n_ballots=None):
    """Reset ``svc`` to the deterministic demo election (voting phase, ballots on the board)."""
    n_students = n_students or config.DEMO_STUDENTS
    n_tokens = min(n_tokens or config.DEMO_TOKENS, n_students)
    n_ballots = min(n_ballots or config.DEMO_BALLOTS, n_tokens)
    base = int(base_time if base_time is not None else now())
    base -= base % 60
    rng = random.Random(seed)
    saved = (svc.clock, svc.rng, svc.mix_wait)
    clock = FakeClock(base - 3 * 3600)
    svc.clock, svc.rng = clock, random.Random(seed + 1)
    svc.mix_wait = 10 ** 9  # batch strictly by size while generating
    try:
        with svc.batch():
            svc.create_election("Student Council Election 2026", POSTS, opens=base - 2 * 3600,
                                closes=base + config.DEMO_WINDOW_DAYS * 86400,
                                eid="%s-%s" % (config.DEMO_EID, sha256_hex(str(base))[:4].upper()), demo=True)
            rows = make_roster(rng, n_students)
            slips = svc.upload_roster(roster_csv(rows), code_rng=rng)["slips"]
            svc.open_registration()
            issuer, trustee = svc.keys["issuer"].public(), svc.keys["trustee"].public()
            order = [r["reg_no"] for r in rows]
            rng.shuffle(order)
            devices = []
            for reg in order[:n_tokens]:
                clock.advance(rng.randint(8, 30))
                dev = VoterDevice(svc.eid, issuer, trustee, rng)
                res = svc._issue_for(reg, "%x" % dev.prepare_token())
                dev.finish_token(int(res["blind_sig"], 16))
                devices.append((reg, dev))
            clock.t = base - 2 * 3600
            svc.open_voting()
            rng.shuffle(devices)
            span = 2 * 3600 - 600
            for i, (reg, dev) in enumerate(devices[:n_ballots]):
                clock.t = base - 2 * 3600 + 60 + int(span * (i / float(n_ballots)) ** 0.8)
                svc.cast(dev.build_ballot(choose_for(svc.state["roster"][reg], svc.manifest, rng)))
            svc.flush_pool(force=True)
        svc.set_demo_codes({s["reg_no"]: s["code"] for s in slips})
        if svc.dir:
            with open(os.path.join(svc.dir, "sample_roster.csv"), "w", encoding="utf-8", newline="") as f:
                f.write(roster_csv(rows))
    finally:
        svc.clock, svc.rng, svc.mix_wait = saved
    return {"eid": svc.eid, "students": n_students, "tokens": n_tokens, "ballots": n_ballots,
            "entries": len(svc.entries), "head": svc.entries[-1]["hash"]}


def main(argv=None):
    from .election import ElectionService
    ap = argparse.ArgumentParser(description="Regenerate CampusVote demo data")
    ap.add_argument("--data", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    ap.add_argument("--keys", action="store_true", help="regenerate deterministic demo keys too")
    args = ap.parse_args(argv)
    os.makedirs(args.data, exist_ok=True)
    kp = os.path.join(args.data, "keys.json")
    if args.keys and os.path.exists(kp):
        os.unlink(kp)
    if not os.path.exists(kp):
        from .util import atomic_write_json
        keys = demo_keys()
        out = {k: v.private_dict() for k, v in keys.items()}
        out["_note"] = "DEMO KEYS (deterministic, seed %d) - never use for a real election." % config.DEMO_SEED
        atomic_write_json(kp, out)
    for f in ("board.json", "state.json", "board.backup.json"):
        p = os.path.join(args.data, f)
        if os.path.exists(p):
            os.unlink(p)
    svc = ElectionService(args.data)
    info = build_demo(svc)
    print("demo election %(eid)s: %(students)d students, %(tokens)d tokens, %(ballots)d ballots, "
          "%(entries)d board entries, head %(head).16s..." % info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
