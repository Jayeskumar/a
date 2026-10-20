"""Measure CampusVote's pure-Python crypto: keygen, blind signing, verification, tally.

    python bench.py            # full run (~1-2 min): 2048-bit keys, 200 and 2,000 ballots
    python bench.py --quick    # smaller run for a sanity check

Results print as a table and are saved to docs/bench.json.
"""

import argparse
import json
import os
import platform
import random
import statistics
import time

from campusvote import audit, blind, config, rsa, seal
from campusvote.client import VoterDevice
from campusvote.demo import choose_for, make_roster, roster_csv
from campusvote.election import ElectionService
from campusvote.util import canonical

HERE = os.path.dirname(os.path.abspath(__file__))


def timeit(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    return out


def summary(ms):
    return {"mean_ms": round(statistics.mean(ms), 2), "median_ms": round(statistics.median(ms), 2),
            "min_ms": round(min(ms), 2), "max_ms": round(max(ms), 2), "runs": len(ms)}


class Clock(object):
    def __init__(self):
        self.t = int(time.time())

    def __call__(self):
        return self.t


def election_with(n_ballots, keys):
    clock = Clock()
    svc = ElectionService(None, keys=keys, clock=clock, rng=random.Random(5), otp_iters=1)
    svc.create_election("Bench Election", [
        {"title": "President", "candidates": ["A", "B", "C"]},
        {"title": "General Secretary", "candidates": ["D", "E"]},
        {"title": "Cultural Secretary", "candidates": ["F", "G", "H"]}], opens=clock() - 10, closes=clock() + 86400)
    rng = random.Random(77)
    rows = []
    while len(rows) < n_ballots:  # repeat the 200-student pattern with unique register numbers
        for r in make_roster(random.Random(len(rows))):
            r = dict(r, reg_no="%s%d" % (r["reg_no"], len(rows) // 200))
            rows.append(r)
    svc.upload_roster(roster_csv(rows[:n_ballots]))
    svc.open_voting()
    t_cast = []
    with svc.batch():
        for reg in sorted(svc.state["roster"]):
            dev = VoterDevice(svc.eid, keys["issuer"].public(), keys["trustee"].public(), rng)
            res = svc._issue_for(reg, "%x" % dev.prepare_token())
            dev.finish_token(int(res["blind_sig"], 16))
            ballot = dev.build_ballot(choose_for(svc.state["roster"][reg], svc.manifest, rng))
            t = time.perf_counter()
            svc.cast(ballot)
            t_cast.append((time.perf_counter() - t) * 1000)
        svc.flush_pool(force=True)
    return svc, t_cast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    out = {"python": platform.python_version(), "machine": platform.machine(), "processor": platform.processor(),
           "rsa_bits": config.RSA_BITS}

    print("Key generation (%d-bit, secrets randomness, Miller-Rabin %d rounds)..." % (config.RSA_BITS, config.MR_ROUNDS))
    kg, cand = [], []
    for _ in range(2 if args.quick else 6):
        st = {}
        t = time.perf_counter()
        rsa.generate_keypair(config.RSA_BITS, stats=st)
        kg.append((time.perf_counter() - t) * 1000)
        cand.append(st["candidates"])
    out["keygen_2048"] = dict(summary(kg), mean_candidates=round(statistics.mean(cand), 1))

    keys = {k: rsa.generate_keypair(config.RSA_BITS, random.Random(i)) for i, k in enumerate(("issuer", "board", "trustee"))}
    iss, pub = keys["issuer"], keys["issuer"].public()
    rng = random.Random(1)
    n = 50 if args.quick else 200
    tokens = [blind.new_token(rng) for _ in range(n)]
    msgs = [blind.token_message("E", t) for t in tokens]
    blinded = [blind.blind(pub, m, rng) for m in msgs]
    it = iter(range(n))
    out["blind"] = summary(timeit(lambda: blind.blind(pub, msgs[0], rng), n))
    sigs = []
    out["blind_sign_authority"] = summary(timeit(lambda: sigs.append(blind.sign_blinded(iss, blinded[next(it)][0])), n))
    finals = []
    out["unblind"] = summary(timeit(lambda: finals.append(blind.unblind(pub, sigs[len(finals)], blinded[len(finals)][1])), n))
    it = iter(range(n))
    ok = []
    out["verify_token"] = summary(timeit(lambda: ok.append(blind.verify_token(pub, "E", tokens[len(ok)], finals[len(ok)])), n))
    assert all(ok)
    pt = canonical({"choices": {"president": "c1", "general-secretary": "c2", "cultural-secretary": "c3"}, "nonce": "ab" * 32})
    tp = keys["trustee"].public()
    sealed = [seal.seal(tp, pt, "tok", rng) for _ in range(n)]
    out["seal_voter"] = summary(timeit(lambda: seal.seal(tp, pt, "tok", rng), n))
    it = iter(range(n))
    out["open_trustee"] = summary(timeit(lambda: seal.open_sealed(keys["trustee"], sealed[next(it)], "tok"), n))

    for nb in ((50, 200) if args.quick else (200, 2000)):
        print("Election with %d ballots..." % nb)
        svc, t_cast = election_with(nb, keys)
        t = time.perf_counter()
        res = svc.close_and_tally()
        t_tally = time.perf_counter() - t
        t = time.perf_counter()
        rep = audit.audit(svc.entries)
        t_audit = time.perf_counter() - t
        assert rep["verdict"] == "VERIFIED" and rep["tally"]["counted"] == nb, rep["verdict"]
        out["election_%d" % nb] = {
            "ballots": nb, "board_entries": len(svc.entries),
            "board_kb": round(len(svc.board_bytes()) / 1024, 1),
            "cast_validate_mean_ms": round(statistics.mean(t_cast), 2),
            "close_and_tally_s": round(t_tally, 2),
            "independent_audit_recount_s": round(t_audit, 3),
            "audit_steps_ms": {s["id"]: s["ms"] for s in rep["steps"]},
            "counted": res["tally"]["counted"],
        }

    print("\n%-34s %s" % ("measurement", "result"))
    for k, v in out.items():
        if isinstance(v, dict):
            vv = {kk: vv for kk, vv in v.items() if kk != "audit_steps_ms"}
            print("%-34s %s" % (k, vv))
        else:
            print("%-34s %s" % (k, v))
    if not args.quick:
        os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
        with open(os.path.join(HERE, "docs", "bench.json"), "w") as f:
            json.dump(out, f, indent=1)
        print("\nsaved docs/bench.json")


if __name__ == "__main__":
    main()
