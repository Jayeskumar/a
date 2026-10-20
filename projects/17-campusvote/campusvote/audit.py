"""Universal verification: anyone can re-check and recount an election from the board alone.

``audit(entries)`` needs nothing but the public board (public keys live in the genesis
entry). It is used by the server, by ``verify.py`` (offline CLI) and by the tests; the
browser runs an equivalent check in static/crypto.js so voters need not trust the server.
"""

import time

from . import blind, board, commitment, rsa
from .util import sha256_hex


def _step(steps, sid, title, ok, detail, why, t0):
    steps.append({"id": sid, "title": title, "ok": ok, "detail": detail, "why": why,
                  "ms": round((time.perf_counter() - t0) * 1000, 1)})


def valid_choices(manifest, choices):
    """True if choices names exactly one known candidate for every post."""
    if not isinstance(choices, dict):
        return False
    posts = {p["id"]: {c["id"] for c in p["candidates"]} for p in manifest["posts"]}
    if set(choices) != set(posts):
        return False
    return all(isinstance(choices[p], str) and choices[p] in posts[p] for p in posts)


def empty_counts(manifest):
    return {p["id"]: {c["id"]: 0 for c in p["candidates"]} for p in manifest["posts"]}


def winners_of(counts):
    out = {}
    for post, cc in counts.items():
        real = {c: v for c, v in cc.items() if c != "NOTA"}
        top = max(real.values()) if real else 0
        out[post] = sorted(c for c, v in real.items() if v == top and top > 0)
    return out


def audit(entries, expected_eid=None):
    t_all = time.perf_counter()
    steps = []
    report = {"verdict": "FAILED", "steps": steps, "tally": None, "first_break": None,
              "breaks": [], "spoiled": [], "problems": []}
    problems = report["problems"]

    # 1. genesis -------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        g = entries[0]
        assert g["type"] == "genesis"
        manifest = g["data"]["election"]
        keys = {k: rsa.PublicKey.from_dict(v) for k, v in g["data"]["keys"].items()}
        issuer, board_key = keys["issuer"], keys["board"]
        eid = manifest["eid"]
        eligible = int(g["data"]["roster"]["eligible"])
        fps = {k: v.fingerprint() for k, v in keys.items()}
        ok = expected_eid is None or eid == expected_eid
        _step(steps, "genesis", "Genesis manifest and public keys", ok,
              "Election %s, %d posts, %d eligible voters. Key fingerprints: issuer %s, board %s, trustee %s"
              % (eid, len(manifest["posts"]), eligible, fps["issuer"], fps["board"], fps["trustee"]),
              "Compare these fingerprints with the ones on the official notice: a fake board needs fake keys.", t0)
    except Exception as exc:  # malformed genesis: nothing else can be checked
        _step(steps, "genesis", "Genesis manifest and public keys", False,
              "Genesis entry missing or malformed (%s)" % type(exc).__name__,
              "Without the genesis entry there are no public keys to verify against.", t0)
        report["ms"] = round((time.perf_counter() - t_all) * 1000, 1)
        return report
    report["election"] = {"eid": eid, "title": manifest.get("title"), "eligible": eligible,
                          "fingerprints": fps}

    # 2. hash chain ----------------------------------------------------------
    t0 = time.perf_counter()
    chain = board.verify_chain(entries)
    report["first_break"] = chain["first_break"]
    report["breaks"] = chain["breaks"]
    if chain["ok"]:
        detail = "%d entries, every hash recomputes and links to its predecessor. Head %s..." % (
            chain["entries"], chain["head"][:16])
    else:
        b = chain["breaks"][0]
        detail = "Chain BROKEN at entry #%d (%s): %s" % (b["seq"], b["kind"], b["detail"])
    _step(steps, "chain", "Hash chain intact", chain["ok"], detail,
          "Any edit, insertion or deletion changes a hash and breaks the chain at that exact entry.", t0)

    # classify entries
    phase_seq = {}
    issuances, ballots, openings, checkpoints, results = [], [], [], [], []
    for e in entries[1:]:
        try:
            t = e["type"]
            if t == "phase":
                phase_seq.setdefault(e["data"]["phase"], e["seq"])
            elif t == "issuance":
                issuances.append(e)
            elif t == "ballot":
                ballots.append(e)
            elif t == "opening":
                openings.append(e)
            elif t == "checkpoint":
                checkpoints.append(e)
            elif t == "result":
                results.append(e)
            elif t not in board.ENTRY_TYPES:
                problems.append("entry #%s has unknown type %r" % (e.get("seq"), t))
        except Exception:
            problems.append("entry is malformed")

    # 3. checkpoints ---------------------------------------------------------
    t0 = time.perf_counter()
    bad_cp = []
    prefix, running = [], 0  # prefix[i] = ballots among entries[0..i]
    for e in entries:
        running += isinstance(e, dict) and e.get("type") == "ballot"
        prefix.append(running)
    for cp in checkpoints:
        try:
            d = cp["data"]
            upto = int(d["upto"])
            ok = 0 <= upto < cp["seq"] and entries[upto]["hash"] == d["head"]
            ok = ok and prefix[upto] == int(d["ballots"])
            sig_ok = rsa.verify_message(board_key, board.checkpoint_message(eid, upto, d["head"], int(d["ballots"])),
                                        int(d["sig"], 16))
            if not sig_ok:
                bad_cp.append("#%d signature INVALID" % cp["seq"])
            elif not ok:
                bad_cp.append("#%d pins head %s... but entry #%d now hashes to %s..." % (
                    cp["seq"], d["head"][:12], upto, str(entries[upto].get("hash"))[:12]))
        except Exception:
            bad_cp.append("#%s malformed" % cp.get("seq"))
    _step(steps, "checkpoints", "Signed checkpoints valid", not bad_cp and bool(checkpoints),
          ("%d checkpoints, all signatures verify and pin the current hashes" % len(checkpoints)) if not bad_cp
          else "%d of %d checkpoints fail: %s" % (len(bad_cp), len(checkpoints), "; ".join(bad_cp[:3])),
          "Checkpoints are RSA-signed by the board key. Re-hashing history to hide an edit cannot re-sign them.", t0)

    # 4. phases --------------------------------------------------------------
    t0 = time.perf_counter()
    v_open = phase_seq.get("voting")
    v_close = phase_seq.get("closed")
    outside = [b["seq"] for b in ballots
               if v_open is None or b["seq"] < v_open or (v_close is not None and b["seq"] > v_close)]
    late_iss = [i["seq"] for i in issuances if v_close is not None and i["seq"] > v_close]
    ph_ok = not outside and not late_iss
    _step(steps, "phases", "Ballots only inside the voting phase", ph_ok,
          ("Voting opened at #%s%s; all %d ballots fall inside" % (
              v_open, (", closed at #%s" % v_close) if v_close is not None else " (still open)", len(ballots)))
          if ph_ok else "%d ballots outside the voting window (e.g. #%s); %d late token issuances" % (
              len(outside), outside[:1], len(late_iss)),
          "Ballots appended after close (or before opening) would be ballot stuffing.", t0)

    # 5. issuance records ----------------------------------------------------
    t0 = time.perf_counter()
    refs, bad_iss, dup_refs = set(), [], []
    for i in issuances:
        try:
            d = i["data"]
            if d["voter_ref"] in refs:
                dup_refs.append(d["voter_ref"])
            refs.add(d["voter_ref"])
            if not issuer.raw_verify(int(d["blinded"], 16), int(d["blind_sig"], 16)):
                bad_iss.append(i["seq"])
        except Exception:
            bad_iss.append(i.get("seq"))
    tokens_issued = len(issuances)
    iss_ok = not bad_iss and not dup_refs and tokens_issued <= eligible
    _step(steps, "issuance", "Token issuance: one blind signature per eligible voter", iss_ok,
          "%d tokens issued to %d distinct voters (of %d eligible); every blind signature is well-formed%s" % (
              tokens_issued, len(refs), eligible,
              "" if iss_ok else " - PROBLEMS: %d bad signatures, %d duplicate voters" % (len(bad_iss), len(dup_refs))),
          "Each student can look up their own voter reference: a token issued in their name without "
          "their knowledge would be exposed.", t0)

    # 6. ballot signatures ---------------------------------------------------
    t0 = time.perf_counter()
    bad_sig = []
    for b in ballots:
        try:
            if not blind.verify_token(issuer, eid, b["data"]["token"], int(b["data"]["sig"], 16)):
                bad_sig.append(b["seq"])
        except Exception:
            bad_sig.append(b.get("seq"))
    _step(steps, "signatures", "Every ballot carries a valid authority signature", not bad_sig,
          ("%d / %d ballot tokens verify: s^e = FDH(token) mod n" % (len(ballots), len(ballots))) if not bad_sig
          else "%d ballots have INVALID signatures (e.g. #%s)" % (len(bad_sig), bad_sig[0]),
          "Only tokens blind-signed for an eligible voter verify; forged tokens fail this check.", t0)

    # 7. duplicates ----------------------------------------------------------
    t0 = time.perf_counter()
    seen, dups = {}, []
    for b in ballots:
        tok = b.get("data", {}).get("token")
        if tok in seen:
            dups.append(b["seq"])
        seen[tok] = b
    _step(steps, "duplicates", "No token used twice", not dups,
          ("%d distinct tokens, 0 duplicates" % len(seen)) if not dups
          else "%d DUPLICATE tokens (e.g. #%s)" % (len(dups), dups[0]),
          "One token = one vote. A replayed or double-cast ballot repeats a token.", t0)

    # 8. counts --------------------------------------------------------------
    t0 = time.perf_counter()
    closed_ok = True
    if v_close is not None:
        try:
            cd = entries[v_close]["data"]
            closed_ok = int(cd["tokens_issued"]) == tokens_issued and int(cd["ballots"]) == len(ballots)
        except Exception:
            closed_ok = False
    cnt_ok = len(ballots) <= tokens_issued <= eligible and closed_ok
    _step(steps, "counts", "Ballots <= tokens issued <= eligible voters", cnt_ok,
          "%d ballots %s %d tokens %s %d eligible%s" % (
              len(ballots), "<=" if len(ballots) <= tokens_issued else "> (STUFFING)", tokens_issued,
              "<=" if tokens_issued <= eligible else ">", eligible,
              "" if closed_ok else " - close entry totals do NOT match the board"),
          "More ballots than issued tokens would prove stuffing by whoever holds the signing key.", t0)

    # 9. openings + recount --------------------------------------------------
    counts = empty_counts(manifest)
    counted = 0
    if v_close is not None:
        t0 = time.perf_counter()
        by_token = {}
        bad_open, unopened = [], []
        for o in openings:
            tok = o.get("data", {}).get("token")
            if tok in by_token:
                bad_open.append("token opened twice at #%s" % o.get("seq"))
            by_token[tok] = o
        for tok, b in seen.items():
            o = by_token.get(tok)
            if o is None:
                unopened.append(b["seq"])
                continue
            d = o["data"]
            if d.get("status") == "ok":
                good = commitment.verify_opening(eid, tok, d.get("choices"), d.get("nonce"),
                                                 b["data"].get("commitment")) and valid_choices(manifest, d.get("choices"))
                if good:
                    counted += 1
                    for post, cand in d["choices"].items():
                        counts[post][cand] += 1
                else:
                    bad_open.append("#%s opening does not match ballot #%s commitment" % (o["seq"], b["seq"]))
            else:
                if d.get("choices") is not None and commitment.verify_opening(
                        eid, tok, d.get("choices"), d.get("nonce"), b["data"].get("commitment")) \
                        and valid_choices(manifest, d.get("choices")):
                    bad_open.append("#%s marked spoiled but its opening is valid" % o.get("seq"))
                report["spoiled"].append({"seq": b["seq"], "token_hash": sha256_hex(tok)[:16],
                                          "reason": d.get("reason", "")})
        orphan = [t for t in by_token if t not in seen]
        op_ok = not bad_open and not unopened and not orphan
        _step(steps, "openings", "Every opening matches its commitment", op_ok,
              ("%d openings verified against their commitments; %d counted, %d spoiled" % (
                  len(openings), counted, len(report["spoiled"]))) if op_ok
              else "PROBLEMS: %s" % "; ".join((bad_open + ["%d ballots never opened" % len(unopened)] * bool(unopened)
                                                + ["%d openings for unknown tokens" % len(orphan)] * bool(orphan))[:3]),
              "Commitments are binding: an opening that names a different candidate cannot match.", t0)

        t0 = time.perf_counter()
        res_ok, res_detail = False, "No signed result posted yet"
        if results:
            r = results[-1]["data"]
            try:
                sig_ok = rsa.verify_message(board_key, board.result_message(eid, r), int(r["sig"], 16))
                same = r.get("counts") == counts and int(r.get("counted", -1)) == counted
                res_ok = sig_ok and same
                res_detail = ("Independent recount of %d ballots equals the signed result" % counted) if res_ok else (
                    "Signed result %s; recount %s" % ("signature INVALID" if not sig_ok else "valid",
                                                      "DIFFERS" if not same else "matches"))
            except Exception:
                res_detail = "Result entry malformed"
        _step(steps, "recount", "Independent recount matches the signed result", res_ok, res_detail,
              "Universal verifiability: anyone with board.json gets the same numbers.", t0)
        report["tally"] = {"counts": counts, "counted": counted, "spoiled": len(report["spoiled"]),
                           "winners": winners_of(counts)}

    report["summary"] = {"entries": len(entries), "ballots": len(ballots), "tokens_issued": tokens_issued,
                         "eligible": eligible, "checkpoints": len(checkpoints), "openings": len(openings),
                         "head": chain["head"]}
    report["verdict"] = "VERIFIED" if all(s["ok"] for s in steps) and not problems else "FAILED"
    report["ms"] = round((time.perf_counter() - t_all) * 1000, 1)
    return report
