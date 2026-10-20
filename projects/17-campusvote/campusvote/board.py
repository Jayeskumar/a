"""Public bulletin board: an append-only, hash-chained log with signed checkpoints.

entry = {seq, type, time, data, prev, hash}
hash  = SHA-256(canonical({seq, type, time, data, prev}))
prev  = hash of the previous entry ("0"*64 for the genesis entry)

Editing any entry changes its hash, so the stored hash no longer matches (content break)
and/or the next entry's ``prev`` no longer matches (link break). An attacker who recomputes
every later hash is caught by the authority-signed checkpoints, which pin the head hash
at regular intervals, and by voters' receipts, which record their entry's hash.
"""

from . import rsa
from .util import canonical, sha256_hex

GENESIS_PREV = "0" * 64
ENTRY_TYPES = ("genesis", "phase", "issuance", "ballot", "checkpoint", "opening", "result")


def entry_hash(entry):
    body = {k: entry.get(k) for k in ("seq", "type", "time", "data", "prev")}
    return sha256_hex(canonical(body))


def make_entry(entries, etype, data, time):
    prev = entries[-1]["hash"] if entries else GENESIS_PREV
    e = {"seq": len(entries), "type": etype, "time": int(time), "data": data, "prev": prev}
    e["hash"] = entry_hash(e)
    return e


def checkpoint_message(eid, upto, head, ballots):
    return "CV1-checkpoint|%s|%d|%s|%d" % (eid, upto, head, ballots)


def result_message(eid, result_data):
    body = {k: v for k, v in result_data.items() if k != "sig"}
    return "CV1-result|%s|%s" % (eid, sha256_hex(canonical(body)))


def make_checkpoint_data(entries, eid, board_key, ballots=None):
    upto = len(entries) - 1
    head = entries[-1]["hash"]
    if ballots is None:
        ballots = sum(1 for e in entries if e.get("type") == "ballot")
    sig = rsa.sign_message(board_key, checkpoint_message(eid, upto, head, ballots))
    return {"upto": upto, "head": head, "ballots": ballots, "sig": "%x" % sig}


def verify_chain(entries, max_breaks=20):
    """Check sequence numbers, hash links and stored hashes. Reports where the chain breaks."""
    breaks = []
    prev = GENESIS_PREV
    for i, e in enumerate(entries):
        problems = []
        if not isinstance(e, dict):
            breaks.append({"seq": i, "kind": "malformed", "detail": "entry is not an object"})
            prev = None
            continue
        if e.get("seq") != i:
            problems.append(("sequence", "expected #%d, found %r - an entry was inserted or deleted" % (i, e.get("seq"))))
        if e.get("prev") != prev:
            problems.append(("link", "prev=%s... but previous entry hash is %s..." % (
                str(e.get("prev"))[:12], str(prev)[:12])))
        recomputed = entry_hash(e)
        if e.get("hash") != recomputed:
            problems.append(("content", "stored hash %s... != recomputed %s... - entry contents were edited" % (
                str(e.get("hash"))[:12], recomputed[:12])))
        for kind, detail in problems:
            if len(breaks) < max_breaks:
                breaks.append({"seq": i, "kind": kind, "detail": detail, "type": e.get("type")})
        prev = e.get("hash")
    return {"ok": not breaks, "entries": len(entries), "breaks": breaks,
            "first_break": breaks[0]["seq"] if breaks else None,
            "head": entries[-1].get("hash") if entries and isinstance(entries[-1], dict) else GENESIS_PREV}
