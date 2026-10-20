"""Attack lab: each attack drives the REAL code paths (login, issue, cast, audit) and reports
what stopped it and why. Nothing here is a canned answer.
"""

import copy
import random
import secrets

from . import audit, blind, board, seal
from .client import VoterDevice
from .commitment import commit, new_nonce
from .rsa import fdh
from .util import Conflict, Forbidden, ValidationError, canonical, sha256_hex


def _outcome(attack, title, blocked, message, why, detail=None, kind="REJECTED"):
    return {"attack": attack, "title": title, "outcome": kind if blocked else "SUCCEEDED",
            "blocked": blocked, "message": message, "why": why, "detail": detail or {}}


def _try(fn):
    try:
        return None, fn()
    except (ValidationError, Conflict, Forbidden) as exc:
        return exc, None


def _a_ballot(svc):
    ballots = svc.ballot_entries()
    if not ballots:
        raise Conflict("no ballots on the board yet - Load demo data first")
    return ballots[len(ballots) // 3]


def double_token(svc):
    """A student who already holds a token asks for a second one."""
    regs = sorted(svc.state["issued"])
    if not regs:
        raise Conflict("no tokens issued yet")
    reg = regs[0]
    dev = VoterDevice(svc.eid, svc.keys["issuer"].public(), svc.keys["trustee"].public())
    err, _ = _try(lambda: svc._issue_for(reg, "%x" % dev.prepare_token(), check_phase=False))
    return _outcome("double_token", "Double voting: ask for a second token", err is not None,
                    str(err) if err else "a second token was issued!",
                    "The authority records which register numbers have been served (never what they "
                    "received). A second request with a new blinded value is refused; re-sending the SAME "
                    "blinded value just returns the same signature, so retries never mint extra tokens.",
                    {"reg_no": reg})


def double_cast(svc):
    """Re-use a token that has already voted, with a different (re-committed) choice."""
    b = _a_ballot(svc)
    forged = dict(b["data"])
    forged.pop("batch", None)
    forged["commitment"] = sha256_hex("second vote " + forged["commitment"])
    err, _ = _try(lambda: svc.validate_ballot(forged))
    return _outcome("double_cast", "Double voting: cast the same token twice", err is not None,
                    str(err) if err else "accepted!",
                    "Every token can appear on the board once. The server checks the board and the mix pool; "
                    "auditors re-check 'no duplicate tokens' independently.",
                    {"token": b["data"]["token"][:16] + "...", "original_seq": b["seq"]})


def forge_random(svc):
    """Make up a token and a random 'signature'."""
    issuer = svc.keys["issuer"]
    token = blind.new_token()
    sig = 2 + secrets.randbelow(issuer.n - 3)
    dev_ballot = _fake_ballot(svc, token, sig)
    err, _ = _try(lambda: svc.validate_ballot(dev_ballot))
    return _outcome("forge_random", "Forge a token without a signature", err is not None,
                    str(err) if err else "accepted!",
                    "A valid signature is s with s^e = FDH(token) mod n. Without the private key d, finding s "
                    "is the RSA problem; a random guess succeeds with probability ~2^-2047.",
                    {"token": token[:16] + "...", "fake_sig": ("%x" % sig)[:24] + "..."})


def forge_multiply(svc):
    """Textbook-RSA malleability: multiply two real signatures."""
    issuer = svc.keys["issuer"]
    ballots = svc.ballot_entries()
    if len(ballots) < 2:
        raise Conflict("need at least two ballots on the board")
    b1, b2 = ballots[0]["data"], ballots[1]["data"]
    s1, s2 = int(b1["sig"], 16), int(b2["sig"], 16)
    s = (s1 * s2) % issuer.n
    m1 = fdh(blind.token_message(svc.eid, b1["token"]), issuer.n)
    m2 = fdh(blind.token_message(svc.eid, b2["token"]), issuer.n)
    textbook_ok = pow(s, issuer.e, issuer.n) == (m1 * m2) % issuer.n
    token = blind.new_token()
    err, _ = _try(lambda: svc.validate_ballot(_fake_ballot(svc, token, s)))
    return _outcome("forge_multiply", "Forge by multiplying two real signatures", err is not None,
                    str(err) if err else "accepted!",
                    "s1*s2 really is a valid textbook-RSA signature on m1*m2 (checked: %s). But tokens are "
                    "hashed with a full-domain hash, so the forger would need a token whose hash equals m1*m2 "
                    "- a SHA-256 preimage. FDH turns RSA's malleability into a dead end." % textbook_ok,
                    {"textbook_signature_on_product_valid": textbook_ok})


def replay(svc):
    """Capture a ballot off the wire/board and submit it again unchanged."""
    b = _a_ballot(svc)
    again = dict(b["data"])
    again.pop("batch", None)
    err, _ = _try(lambda: svc.validate_ballot(again))
    return _outcome("replay", "Replay a captured ballot", err is not None, str(err) if err else "accepted!",
                    "A replay is a byte-identical duplicate: same token, so it is rejected exactly like a double "
                    "vote. Token issuance is idempotent too, so replaying a signing request yields no new token.",
                    {"replayed_seq": b["seq"]})


def cross_election(svc):
    """Replay a genuinely signed ballot from a different (e.g. last year's) election."""
    issuer = svc.keys["issuer"]
    old_eid = "KSRCE-SC-2025-OLD"
    dev = VoterDevice(old_eid, issuer.public(), svc.keys["trustee"].public())
    blinded = dev.prepare_token()
    dev.finish_token(blind.sign_blinded(issuer, blinded))  # a real signature, for the OLD election
    valid_there = blind.verify_token(issuer, old_eid, dev.token, dev.sig)
    ballot = dev.build_ballot({p["id"]: p["candidates"][0]["id"] for p in svc.manifest["posts"]})
    err, _ = _try(lambda: svc.validate_ballot(ballot))
    return _outcome("cross_election", "Replay a token from another election", err is not None,
                    str(err) if err else "accepted!",
                    "The signed message is FDH('CV1-token|<election id>|<token>'). The same token and signature "
                    "that are valid for %s (checked: %s) do not verify for %s." % (old_eid, valid_there, svc.eid),
                    {"old_election": old_eid})


def otp_bruteforce(svc):
    """Guess one-time codes for a student."""
    roster = svc.state["roster"]
    issued = svc.state["issued"]
    target = next((r for r in sorted(roster) if r in issued and roster[r].get("failed", 0) == 0), None) or \
        next(iter(sorted(roster)), None)
    if not target:
        raise Conflict("no roster")
    attempts = []
    rng = random.Random()
    for _ in range(7):
        guess = "%06d" % rng.randrange(10 ** 6)
        err, ok = _try(lambda: svc._authenticate(target, guess))
        attempts.append({"guess": guess, "result": "success" if ok else str(err)})
        if ok:
            break
    locked = roster[target].get("failed", 0) >= 5
    svc.unlock(target)  # keep the demo roster usable
    return _outcome("otp_bruteforce", "Brute-force a student's one-time code", locked,
                    "Locked after %d wrong guesses (account unlocked again for the demo)" % 5,
                    "6-digit codes have 10^6 values; 5 guesses succeed with probability 0.0005%. Stored codes are "
                    "salted PBKDF2 hashes, never plaintext.", {"target": target, "attempts": attempts}, kind="BLOCKED")


def link_attempt(svc):
    """The authority tries to work out how a specific student voted."""
    res = svc.linkability()
    blocked = res["ballots"] > 1 and res["consistent"] == res["ballots"]
    return _outcome("link_attempt", "Authority tries to link a voter to a ballot", blocked,
                    "Issuance #%d is consistent with %d of %d ballots - best guess is %s" % (
                        res["issuance_seq"], res["consistent"], res["ballots"], res["guess_probability"]),
                    res["explanation"], res, kind="UNLINKABLE")


def stuffing(svc):
    """The authority signs extra tokens for itself (dry run on a COPY of the board)."""
    entries = copy.deepcopy(svc.entries)
    issued = sum(1 for e in entries if e["type"] == "issuance")
    ballots = sum(1 for e in entries if e["type"] == "ballot")
    if not ballots:
        raise Conflict("no ballots yet")
    extra = issued - ballots + 1
    issuer, bkey = svc.keys["issuer"], svc.keys["board"]
    rng = random.Random(7)
    for _ in range(extra):
        tok = blind.new_token(rng)
        sig = issuer.raw_sign(fdh(blind.token_message(svc.eid, tok), issuer.n))
        entries.append(board.make_entry(entries, "ballot", {"token": tok, "sig": "%x" % sig,
                                                            "commitment": sha256_hex(tok), "sealed": {}}, 0))
    entries.append(board.make_entry(entries, "checkpoint", board.make_checkpoint_data(entries, svc.eid, bkey), 0))
    rep = audit.audit(entries, expected_eid=svc.eid)
    failed = [s for s in rep["steps"] if not s["ok"]]
    detected = any(s["id"] == "counts" for s in failed)
    return _outcome("stuffing", "Insider stuffs ballots with the signing key", detected,
                    "Stuffed %d ballots (more than the %d token-holders who have not voted): %s" % (
                        extra, issued - ballots, failed[0]["detail"] if failed else "not detected"),
                    "Every issuance is public, so ballots can never exceed tokens issued. HONEST LIMIT: an insider "
                    "holding the signing key could add up to (tokens issued - ballots cast) = %d ballots without "
                    "breaking the count. Mitigation: split the key across 3 officials (threshold RSA)." % (
                        issued - ballots), {"stuffed": extra, "verdict": rep["verdict"]}, kind="DETECTED")


def _fake_ballot(svc, token, sig):
    trustee = svc.keys["trustee"]
    choices = {p["id"]: p["candidates"][0]["id"] for p in svc.manifest["posts"]}
    nonce = new_nonce()
    return {"token": token, "sig": "%x" % sig, "commitment": commit(svc.eid, token, choices, nonce),
            "sealed": seal.seal(trustee.public(), canonical({"choices": choices, "nonce": nonce}), token)}


def tamper(svc, mode):
    res = svc.tamper(mode)
    rep = res["report"]
    failed = [s for s in rep["steps"] if not s["ok"]]
    titles = {"edit": "Admin edits a ballot in board.json", "rehash": "Admin edits AND re-hashes the chain",
              "delete": "Admin deletes a ballot from board.json"}
    why = {"edit": "The edited entry's hash no longer recomputes, so the chain breaks at exactly that entry.",
           "rehash": "Recomputing hashes hides the edit from the chain check, but the authority-signed checkpoints "
                     "pin the old hashes and cannot be re-signed without the board key. Voters' receipts also hold "
                     "their entry hash.",
           "delete": "Sequence numbers and prev-hash links jump at the gap; the affected voter's receipt check "
                     "reports 'missing'."}
    return _outcome("tamper_" + mode, titles[mode], rep["verdict"] != "VERIFIED",
                    "Insider %s. Audit %s at: %s" % (res["what"], rep["verdict"],
                                                    "; ".join(s["title"] for s in failed) or "nothing"),
                    why[mode], {"target_seq": res["target_seq"], "first_break": rep["first_break"],
                                "failed_steps": [s["id"] for s in failed], "report": rep,
                                "halted": res["halted"]}, kind="DETECTED")


ATTACKS = {
    "double_token": double_token, "double_cast": double_cast, "forge_random": forge_random,
    "forge_multiply": forge_multiply, "replay": replay, "cross_election": cross_election,
    "otp_bruteforce": otp_bruteforce, "link_attempt": link_attempt, "stuffing": stuffing,
    "tamper_edit": lambda s: tamper(s, "edit"), "tamper_rehash": lambda s: tamper(s, "rehash"),
    "tamper_delete": lambda s: tamper(s, "delete"),
}


def run(svc, name):
    fn = ATTACKS.get(name)
    if not fn:
        raise ValidationError("unknown attack %r" % name)
    with svc.lock:
        return fn(svc)

