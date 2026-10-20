"""Micro-benchmarks for REPORT.md:  python bench.py
Measures Ed25519 sign/verify, block mining at the configured difficulty,
single-certificate verification, full-chain validation and Merkle proofs."""

import os
import platform
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from certchain import config, demo, ed25519, merkle  # noqa: E402
from certchain.chain import build_block  # noqa: E402
from certchain.records import clean_certificate_input, make_certificate, record_hash  # noqa: E402


def timeit(fn, n):
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def fmt(xs):
    return "median %.2f ms (min %.2f, max %.2f, n=%d)" % (statistics.median(xs), min(xs), max(xs), len(xs))


def main():
    print("Python %s on %s" % (platform.python_version(), platform.machine()))
    kp = ed25519.KeyPair(demo.demo_secret("bench"))
    msg = b"CertChain-block-v1:" + bytes(32)
    sig = kp.sign(msg)
    print("Ed25519 sign      :", fmt(timeit(lambda: kp.sign(msg), 200)))
    print("Ed25519 verify    :", fmt(timeit(lambda: kp.verify(msg, sig), 200)))

    keys = demo.build_keys()
    led = demo.build_demo_chain(keys)
    ks = ed25519.KeyPair(bytes.fromhex(keys["institutions"][0]["secret_seed"]))
    cleaned = clean_certificate_input({"student_name": "Bench Student", "register_no": "KSR22CS001",
                                       "programme": "B.E. CSE", "cgpa": "8.5", "issue_date": "2026-10-20",
                                       "cert_type": "Degree Certificate"})
    attempts, mine_ms = [], []
    for i in range(30):
        recs = [make_certificate("KSRCE-26-B%04d" % i, "ksrce", cleaned, "%032x" % i)]
        _, st = build_block(6, led.tip["hash"], recs, "ksrce", ks, "2026-10-20T00:00:%02dZ" % (i % 60))
        attempts.append(st["attempts"])
        mine_ms.append(st["mining_ms"])
    print("Mining (diff %d)   : %s, mean %.1f ms, mean attempts %d" % (
        config.POW_DIFFICULTY, fmt(mine_ms), statistics.mean(mine_ms), statistics.mean(attempts)))

    rep = led.validate()
    cid = "KSRCE-26-00001"
    bundle = led.certificate_bundle(cid)
    print("Verify 1 cert (incl. full-chain check):", fmt(timeit(lambda: led.verify_bundle(bundle), 30)))
    print("Verify 1 cert (chain check cached)   :", fmt(timeit(lambda: led.verify_bundle(bundle, validation=rep), 50)))
    print("Full-chain validation (%d blocks, %d records):" % (len(led.blocks), sum(len(b["records"]) for b in led.blocks)),
          fmt(timeit(led.validate, 30)))

    # scaling: 50 more blocks x 20 certificates = 1,000 extra certificates
    big = demo.build_demo_chain(keys)
    t0 = time.perf_counter()
    for bi in range(50):
        recs = [make_certificate("KSRCE-27-%05d" % (bi * 20 + j), "ksrce", cleaned, "%032x" % (bi * 20 + j))
                for j in range(20)]
        big.append(recs, "ksrce", ks, "2026-10-20T00:00:00Z")
    build_s = time.perf_counter() - t0
    print("Built 56-block chain with %d certificates in %.1f s" % (len(big.cert_index()), build_s))
    print("Full-chain validation (56 blocks, ~1,000 certs):", fmt(timeit(big.validate, 5)))

    hashes = [record_hash({"i": i}) for i in range(500)]
    print("Merkle root, 500 leaves  :", fmt(timeit(lambda: merkle.merkle_root(hashes), 30)))
    proof = merkle.merkle_proof(hashes, 321)
    root = merkle.merkle_root(hashes)
    print("Merkle proof verify (500 leaves, %d steps):" % len(proof),
          fmt(timeit(lambda: merkle.verify_proof(hashes[321], proof, root), 500)))


if __name__ == "__main__":
    main()
