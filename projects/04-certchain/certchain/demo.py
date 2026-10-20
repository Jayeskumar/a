"""Deterministic demo data: consortium + two institutions, ~20 certificates.

Run `python -m certchain.demo` from the project folder to regenerate data/.
Demo keys are derived from fixed seeds so the committed data is
reproducible; real deployments call ed25519.generate_secret() (os.urandom)
and keep the secret in an HSM / smart card, never in a JSON file.
"""

import hashlib
import json
import os
import random

from . import config
from .chain import Ledger, build_block
from .ed25519 import KeyPair
from .records import clean_certificate_input, make_authority, make_certificate, make_revocation

SEED = 2026

CONSORTIUM = {"id": config.CONSORTIUM_ID, "code": "ROOT",
              "name": "CertChain Consortium (demo regulator)", "city": "Chennai"}
INSTITUTIONS = [
    {"id": "ksrce", "code": "KSRCE", "name": "K.S.R. College of Engineering", "city": "Tiruchengode"},
    {"id": "cvct", "code": "CVCT", "name": "Cauvery Valley College of Technology (demo)", "city": "Erode"},
]

FIRST = ["Aarthi", "Bharath", "Deepika", "Gokul", "Harini", "Karthik", "Keerthana", "Madhan",
         "Nandhini", "Pranav", "Priyadharshini", "Ragul", "Sandhiya", "Santhosh", "Swetha",
         "Tharun", "Vaishnavi", "Vignesh", "Yamuna", "Arjun", "Divya", "Naveen"]
INITIALS = ["A.", "B.", "K.", "M.", "N.", "P.", "R.", "S.", "T.", "V."]
KSRCE_PROGS = [("B.E. Computer Science and Engineering", "CS"),
               ("B.E. Electronics and Communication Engineering", "EC"),
               ("B.E. Mechanical Engineering", "ME"),
               ("B.Tech Information Technology", "IT"),
               ("B.E. Electrical and Electronics Engineering", "EE")]
CVCT_PROGS = [("B.E. Civil Engineering", "CE"),
              ("B.Tech Artificial Intelligence and Data Science", "AD"),
              ("B.E. Computer Science and Engineering", "CS")]

# The certificate the tamper demo edits by default (a modest CGPA an
# attacker would like to "upgrade").
TAMPER_TARGET = "KSRCE-26-00003"


def demo_secret(entity_id):
    return hashlib.sha256(("CertChain demo seed v1/" + entity_id).encode()).digest()


def build_keys():
    def entry(e):
        kp = KeyPair(demo_secret(e["id"]))
        d = dict(e)
        d["secret_seed"] = kp.secret.hex()
        d["public_key"] = kp.public.hex()
        return d
    return {"note": "DEMO KEYS - deterministic seeds for a reproducible demo. "
                    "Never store real issuer keys in a file.",
            "consortium": entry(CONSORTIUM),
            "institutions": [entry(i) for i in INSTITUTIONS]}


class _Issuer(object):
    def __init__(self, inst, keys, rng):
        self.inst = inst
        self.kp = KeyPair(bytes.fromhex(keys["secret_seed"]))
        self.rng = rng
        self.seq = 0

    def cert(self, fields):
        self.seq += 1
        cleaned = clean_certificate_input(fields)
        cid = "%s-%s-%05d" % (self.inst["code"], cleaned["issue_date"][2:4], self.seq)
        salt = "%032x" % self.rng.getrandbits(128)
        return make_certificate(cid, self.inst["id"], cleaned, salt)


def _student(rng, used, prog, batch_year, college_tag):
    while True:
        name = "%s %s" % (rng.choice(FIRST), rng.choice(INITIALS))
        if name not in used:
            used.add(name)
            break
    regno = "%s%s%s%03d" % (college_tag, str(batch_year)[2:], prog[1], rng.randint(1, 180))
    return name, regno


def build_demo_chain(keys):
    rng = random.Random(SEED)
    used = set()
    root = KeyPair(bytes.fromhex(keys["consortium"]["secret_seed"]))
    ks = _Issuer(INSTITUTIONS[0], keys["institutions"][0], rng)
    cv = _Issuer(INSTITUTIONS[1], keys["institutions"][1], rng)

    def degree(issuer, progs, tag, date, ctype="Degree Certificate", cgpa_range=(6.2, 9.6)):
        prog = rng.choice(progs)
        name, regno = _student(rng, used, prog, 2022, tag)
        cgpa = "" if ctype in config.CGPA_OPTIONAL_TYPES else "%.2f" % rng.uniform(*cgpa_range)
        return issuer.cert({"student_name": name, "register_no": regno, "programme": prog[0],
                            "cgpa": cgpa, "issue_date": date, "cert_type": ctype})

    blocks = []

    def add(records, issuer_id, kp, ts):
        prev = blocks[-1]["hash"] if blocks else config.GENESIS_PREV_HASH
        b, _ = build_block(len(blocks), prev, records, issuer_id, kp, ts)
        blocks.append(b)

    # 0: genesis - the consortium registers the permissioned issuers
    add([make_authority(dict(INSTITUTIONS[i], public_key=keys["institutions"][i]["public_key"]),
                        "2026-01-05T09:00:00Z") for i in range(2)],
        config.CONSORTIUM_ID, root, "2026-01-05T09:00:00Z")
    # 1: KSRCE convocation batch (7 degrees - odd count on purpose)
    b1 = [degree(ks, KSRCE_PROGS, "KSR", "2026-05-30") for _ in range(7)]
    b1[2]["cgpa"] = "6.84"                     # the tamper-demo target
    add(b1, "ksrce", ks.kp, "2026-05-30T10:15:00Z")
    # 2: CVCT degrees
    add([degree(cv, CVCT_PROGS, "CVC", "2026-06-02") for _ in range(4)], "cvct", cv.kp, "2026-06-02T11:40:00Z")
    # 3: KSRCE marksheets + internships
    b3 = [degree(ks, KSRCE_PROGS, "KSR", "2026-06-15", "Consolidated Marksheet") for _ in range(3)]
    b3 += [degree(ks, KSRCE_PROGS, "KSR", "2026-06-15", "Internship Certificate") for _ in range(2)]
    add(b3, "ksrce", ks.kp, "2026-06-15T14:05:00Z")
    # 4: KSRCE revokes one degree issued with the wrong programme, re-issues it
    wrong = b1[3]
    fixed = dict((k, wrong[k]) for k in ("student_name", "register_no", "cgpa", "cert_type"))
    fixed["programme"] = "B.E. Computer Science and Engineering" if "Computer" not in wrong["programme"] \
        else "B.Tech Information Technology"
    fixed["issue_date"] = "2026-07-01"
    reissue = ks.cert(fixed)
    add([make_revocation(wrong["cert_id"], "ksrce",
                         "Issued with wrong programme; replaced by %s" % reissue["cert_id"],
                         "2026-07-01T09:30:00Z", ks.kp), reissue],
        "ksrce", ks.kp, "2026-07-01T09:30:00Z")
    # 5: CVCT internship + course completion
    b5 = [degree(cv, CVCT_PROGS, "CVC", "2026-08-10", "Internship Certificate") for _ in range(2)]
    b5.append(degree(cv, CVCT_PROGS, "CVC", "2026-08-10", "Course Completion Certificate"))
    add(b5, "cvct", cv.kp, "2026-08-10T16:20:00Z")
    return Ledger(blocks, keys["consortium"]["public_key"])


SAMPLE_CSV = """student_name,register_no,programme,cgpa,issue_date,cert_type
Lakshmi R.,KSR22CS141,B.E. Computer Science and Engineering,8.91,2026-10-20,Degree Certificate
Mohan Kumar S.,KSR22EC077,B.E. Electronics and Communication Engineering,7.48,2026-10-20,Degree Certificate
Revathi P.,KSR22IT032,B.Tech Information Technology,9.12,2026-10-20,Degree Certificate
Surya Prakash K.,KSR22ME118,B.E. Mechanical Engineering,6.95,2026-10-20,Degree Certificate
Fathima N.,KSR22CS009,B.E. Computer Science and Engineering,,2026-10-20,Internship Certificate
"""


def write_demo(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    keys = build_keys()
    ledger = build_demo_chain(keys)
    with open(os.path.join(data_dir, "keys.json"), "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)
    with open(os.path.join(data_dir, "chain.json"), "w", encoding="utf-8") as f:
        json.dump({"blocks": ledger.blocks}, f, indent=1, ensure_ascii=False)
    with open(os.path.join(data_dir, "sample_bulk.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(SAMPLE_CSV)
    backup = os.path.join(data_dir, "chain.backup.json")
    if os.path.exists(backup):
        os.remove(backup)
    return keys, ledger


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _, led = write_demo(os.path.join(here, "data"))
    print("wrote %d blocks to data/chain.json" % len(led.blocks))
