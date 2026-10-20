"""Shared test fixtures: small deterministic keys and a quick in-memory election."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from campusvote import rsa  # noqa: E402
from campusvote.election import ElectionService  # noqa: E402

_KEYS = {}


def small_keys(bits=1024):
    """1024-bit keys keep the suite fast; production uses 2048 (same code path)."""
    if bits not in _KEYS:
        rng = random.Random(4242 + bits)
        _KEYS[bits] = {k: rsa.generate_keypair(bits, rng) for k in ("issuer", "board", "trustee")}
    return _KEYS[bits]


POSTS = [{"title": "President", "candidates": [{"name": "Asha", "dept": "CSE"}, {"name": "Bala", "dept": "ECE"}]},
         {"title": "Secretary", "candidates": ["Chitra", "Deepak", "Esther"]}]


def roster_csv(n):
    depts = ["CSE", "ECE", "MECH"]
    return "reg_no,name,dept,year\n" + "\n".join(
        "24%s%03d,Student %d,%s,%d" % (depts[i % 3], i, i, depts[i % 3], 1 + i % 4) for i in range(n)) + "\n"


class Clock(object):
    def __init__(self, t=1_800_000_000):
        self.t = t

    def __call__(self):
        return self.t


def make_election(n=12, data_dir=None, phase="voting", clock=None):
    """Returns (service, {reg_no: code}) with a roster of n students."""
    clock = clock or Clock()
    svc = ElectionService(data_dir, keys=small_keys(), clock=clock, rng=random.Random(99), otp_iters=1)
    svc.create_election("Test Council 2026", POSTS, opens=clock() - 60, closes=clock() + 3600)
    slips = svc.upload_roster(roster_csv(n))["slips"]
    codes = {s["reg_no"]: s["code"] for s in slips}
    if phase in ("registration", "voting"):
        svc.open_registration()
    if phase == "voting":
        svc.open_voting()
    return svc, codes


def voter(svc, rng=None):
    from campusvote.client import VoterDevice
    return VoterDevice(svc.eid, svc.keys["issuer"].public(), svc.keys["trustee"].public(), rng)


def get_token(svc, reg, code, rng=None):
    """Full voter path: login with the one-time code, blind, get signed, unblind."""
    dev = voter(svc, rng)
    sess = svc.login(reg, code)["session"]
    res = svc.issue(sess, "%x" % dev.prepare_token())
    dev.finish_token(int(res["blind_sig"], 16))
    return dev
