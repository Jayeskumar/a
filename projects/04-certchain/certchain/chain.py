"""Permissioned blockchain: blocks, mining, full-chain validation and
certificate verification with step-by-step explanations.

Block layout (JSON):
    {"header": {"version", "index", "timestamp", "prev_hash", "merkle_root",
                "issuer_id", "difficulty", "record_count", "nonce"},
     "hash": SHA256(canonical(header minus nonce) || "|nonce:" || nonce),
     "signature": Ed25519_sign(issuer_key, "CertChain-block-v1:" || hash),
     "records": [certificate | revocation | authority records]}
"""

import hashlib
import time

from . import config
from . import ed25519
from . import merkle
from .records import canonical_json, record_hash, verify_revocation, verification_code


# --- Header hashing & PoW -------------------------------------------------

def _header_prefix(header):
    body = {k: v for k, v in header.items() if k != "nonce"}
    return canonical_json(body) + b"|nonce:"


def block_hash(header):
    return hashlib.sha256(_header_prefix(header) + str(header.get("nonce", 0)).encode()).hexdigest()


def meets_pow(hash_hex, difficulty):
    return isinstance(difficulty, int) and hash_hex.startswith("0" * difficulty)


def mine(header, difficulty):
    """Find a nonce so the header hash has `difficulty` leading hex zeros.
    Returns (nonce, hash_hex, attempts, seconds)."""
    t0 = time.perf_counter()
    base = hashlib.sha256(_header_prefix(header))
    target = "0" * difficulty
    nonce = 0
    while True:
        h = base.copy()
        h.update(str(nonce).encode())
        hx = h.hexdigest()
        if hx.startswith(target):
            return nonce, hx, nonce + 1, time.perf_counter() - t0
        nonce += 1


def block_sig_message(hash_hex):
    return config.BLOCK_SIG_PREFIX + bytes.fromhex(hash_hex)


def build_block(index, prev_hash, records, issuer_id, keypair, timestamp,
                difficulty=config.POW_DIFFICULTY):
    """Create, mine and sign a block. Returns (block, stats)."""
    hashes = [record_hash(r) for r in records]
    header = {
        "version": config.CHAIN_VERSION,
        "index": index,
        "timestamp": timestamp,
        "prev_hash": prev_hash,
        "merkle_root": merkle.merkle_root(hashes),
        "issuer_id": issuer_id,
        "difficulty": difficulty,
        "record_count": len(records),
        "nonce": 0,
    }
    nonce, hx, attempts, secs = mine(header, difficulty)
    header["nonce"] = nonce
    t0 = time.perf_counter()
    sig = keypair.sign(block_sig_message(hx))
    sign_secs = time.perf_counter() - t0
    block = {"header": header, "hash": hx, "signature": sig.hex(), "records": list(records)}
    stats = {"attempts": attempts, "mining_ms": round(secs * 1000, 2),
             "signing_ms": round(sign_secs * 1000, 2), "difficulty": difficulty}
    return block, stats


def _check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def _short(h):
    return (h[:10] + "...") if isinstance(h, str) and len(h) > 12 else str(h)


# --- Ledger ----------------------------------------------------------------

class Ledger(object):
    """An ordered list of blocks plus the pinned consortium root public key."""

    def __init__(self, blocks, root_public_hex):
        self.blocks = blocks
        self.root_public = root_public_hex

    # -- indexes (built from the data as stored; validate() says if trustable)
    def authorities(self):
        out = {}
        for b in self.blocks:
            if b.get("header", {}).get("issuer_id") != config.CONSORTIUM_ID:
                continue
            for r in b.get("records", []):
                if r.get("type") == "authority":
                    out[r["inst_id"]] = r
        return out

    def public_key_of(self, issuer_id):
        if issuer_id == config.CONSORTIUM_ID:
            return self.root_public
        a = self.authorities().get(issuer_id)
        return a["public_key"] if a else None

    def cert_index(self):
        idx = {}
        for bi, b in enumerate(self.blocks):
            for ri, r in enumerate(b.get("records", [])):
                if r.get("type") == "certificate":
                    idx.setdefault(r.get("cert_id"), (bi, ri))
        return idx

    def revocations(self):
        out = {}
        for bi, b in enumerate(self.blocks):
            for r in b.get("records", []):
                if r.get("type") == "revocation":
                    out.setdefault(r.get("cert_id"), (bi, r))
        return out

    @property
    def tip(self):
        return self.blocks[-1]

    def append(self, records, issuer_id, keypair, timestamp, difficulty=config.POW_DIFFICULTY):
        prev = self.tip
        ts = max(timestamp, prev["header"]["timestamp"])
        block, stats = build_block(len(self.blocks), prev["hash"], records, issuer_id,
                                   keypair, ts, difficulty)
        self.blocks.append(block)
        return block, stats

    # -- full-chain validation ------------------------------------------
    def validate(self):
        """Re-check every block. Returns a report with per-block checks."""
        t0 = time.perf_counter()
        auth = {}                 # inst_id -> public key hex (built as we go)
        issued = {}               # cert_id -> issuer_id
        revoked = set()
        report_blocks = []
        errors = []
        prev_ts = ""
        for i, b in enumerate(self.blocks):
            checks = []
            try:
                h = b["header"]
                records = b["records"]
                stored_hash = b["hash"]
                recomputed = block_hash(h)
                checks.append(_check("index", h.get("index") == i,
                                     "position %d, header says %s" % (i, h.get("index"))))
                expected_prev = config.GENESIS_PREV_HASH if i == 0 else self.blocks[i - 1].get("hash")
                checks.append(_check("prev_link", h.get("prev_hash") == expected_prev,
                                     "prev_hash %s %s hash of block %d (%s)" % (
                                         _short(h.get("prev_hash")),
                                         "==" if h.get("prev_hash") == expected_prev else "!=",
                                         i - 1, _short(expected_prev)) if i else
                                     "genesis must point to 000...0"))
                checks.append(_check("block_hash", recomputed == stored_hash,
                                     "recomputed %s vs stored %s" % (_short(recomputed), _short(stored_hash))))
                diff = h.get("difficulty")
                pow_ok = (isinstance(diff, int) and diff >= config.MIN_DIFFICULTY
                          and meets_pow(stored_hash, diff) and meets_pow(recomputed, diff))
                checks.append(_check("pow", pow_ok, "needs %s leading zeros (min %d)" % (diff, config.MIN_DIFFICULTY)))
                hashes = [record_hash(r) for r in records]
                root = merkle.merkle_root(hashes)
                checks.append(_check("merkle_root",
                                     root == h.get("merkle_root") and h.get("record_count") == len(records),
                                     "records hash to %s, header has %s" % (_short(root), _short(h.get("merkle_root")))))
                signer = h.get("issuer_id")
                pub = self.root_public if signer == config.CONSORTIUM_ID else auth.get(signer)
                if pub is None:
                    checks.append(_check("signature", False, "signer '%s' is not a registered institution" % signer))
                    sig_ok = False
                else:
                    try:
                        sig_ok = ed25519.verify(bytes.fromhex(pub), block_sig_message(recomputed),
                                                bytes.fromhex(b.get("signature", "")))
                    except ValueError:
                        sig_ok = False
                    checks.append(_check("signature", sig_ok,
                                         "Ed25519 signature by %s over the recomputed block hash" % signer))
                rec_problems = []
                new_auth = {}
                for r in records:
                    t = r.get("type")
                    if t == "certificate":
                        cid = r.get("cert_id")
                        if signer == config.CONSORTIUM_ID or r.get("issuer_id") != signer:
                            rec_problems.append("%s issued by %s inside a block signed by %s" % (cid, r.get("issuer_id"), signer))
                        elif cid in issued:
                            rec_problems.append("duplicate certificate id %s" % cid)
                        else:
                            issued[cid] = signer
                    elif t == "revocation":
                        cid = r.get("cert_id")
                        if r.get("issuer_id") != signer or issued.get(cid) != signer:
                            rec_problems.append("revocation of %s not by its issuer" % cid)
                        elif not verify_revocation(r, pub or ""):
                            rec_problems.append("bad signature on revocation of %s" % cid)
                        elif cid in revoked:
                            rec_problems.append("%s revoked twice" % cid)
                        else:
                            revoked.add(cid)
                    elif t == "authority":
                        if signer != config.CONSORTIUM_ID:
                            rec_problems.append("authority record outside a consortium block")
                        else:
                            new_auth[r.get("inst_id")] = r.get("public_key")
                    else:
                        rec_problems.append("unknown record type %r" % t)
                if sig_ok:
                    auth.update(new_auth)
                checks.append(_check("records", not rec_problems,
                                     "; ".join(rec_problems) if rec_problems else
                                     "%d records obey issuer rules" % len(records)))
                ts = h.get("timestamp", "")
                checks.append(_check("timestamp", isinstance(ts, str) and ts >= prev_ts,
                                     "%s (not earlier than previous block)" % ts))
                prev_ts = ts if isinstance(ts, str) else prev_ts
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                checks.append(_check("structure", False, "malformed block: %s" % exc))
            ok = all(c["ok"] for c in checks)
            if not ok:
                for c in checks:
                    if not c["ok"]:
                        errors.append("block %d: %s failed - %s" % (i, c["name"], c["detail"]))
            report_blocks.append({
                "index": i,
                "hash": b.get("hash") if isinstance(b, dict) else None,
                "ok": ok,
                "link_ok": next((c["ok"] for c in checks if c["name"] == "prev_link"), False),
                "checks": checks,
            })
        bad = [rb["index"] for rb in report_blocks if not rb["ok"]]
        return {
            "valid": not bad and bool(self.blocks),
            "block_count": len(self.blocks),
            "broken_blocks": bad,
            "first_bad_block": bad[0] if bad else None,
            "errors": errors,
            "blocks": report_blocks,
            "validation_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    # -- certificate bundles & verification --------------------------------
    def certificate_bundle(self, cert_id):
        loc = self.cert_index().get(cert_id)
        if loc is None:
            return None
        bi, ri = loc
        b = self.blocks[bi]
        hashes = [record_hash(r) for r in b["records"]]
        rec = b["records"][ri]
        issuer = self.authorities().get(rec.get("issuer_id"), {})
        return {
            "certchain": "certificate-bundle/v1",
            "record": rec,
            "record_hash": hashes[ri],
            "verification_code": verification_code(hashes[ri]),
            "merkle_proof": merkle.merkle_proof(hashes, ri),
            "leaf_index": ri,
            "block": {"header": b["header"], "hash": b["hash"], "signature": b["signature"]},
            "issuer": {"id": rec.get("issuer_id"), "name": issuer.get("name"),
                       "public_key": issuer.get("public_key")},
        }

    def verify_bundle(self, bundle, validation=None, printed_code=None):
        """Explainable verification of a certificate bundle against this ledger."""
        t0 = time.perf_counter()
        steps = []

        def step(key, title, ok, detail, why):
            steps.append({"key": key, "title": title, "ok": bool(ok), "detail": detail, "why": why})
            return ok

        try:
            rec = bundle["record"]
            proof = bundle["merkle_proof"]
            blk = bundle["block"]
            header = blk["header"]
            claimed_hash = blk["hash"]
            sig_hex = blk["signature"]
            if not isinstance(rec, dict) or rec.get("type") != "certificate":
                raise TypeError("record is not a certificate")
            if not isinstance(proof, list) or not isinstance(header, dict):
                raise TypeError("bad proof/header")
        except (KeyError, TypeError) as exc:
            step("format", "Certificate file is well-formed", False, str(exc),
                 "A CertChain certificate JSON carries the record, its Merkle proof and the block header.")
            return self._verdict(steps, None, t0)

        cert_id = rec.get("cert_id")
        computed = record_hash(rec)
        claimed_rh = bundle.get("record_hash")
        ok1 = claimed_rh in (None, computed)
        step("record_hash", "Record hash", ok1,
             "SHA-256(canonical JSON) = %s%s" % (_short(computed),
                                                 "" if ok1 else " but certificate claims %s" % _short(claimed_rh)),
             "Any change to name, register no., CGPA, date or type changes this hash completely.")
        if printed_code:
            want = verification_code(computed).replace("-", "")
            from .records import normalise_code
            step("printed_code", "Printed verification code matches", normalise_code(printed_code) == want,
                 "code on paper %s, record gives %s" % (printed_code, verification_code(computed)),
                 "The 8-character code on the paper certificate is derived from the record hash.")
        root = header.get("merkle_root")
        ok2 = merkle.verify_proof(computed, proof, root)
        step("merkle_proof", "Merkle inclusion proof", ok2,
             "%d-step proof %s block %s Merkle root %s" % (len(proof), "reaches" if ok2 else "does NOT reach",
                                                             header.get("index"), _short(root)),
             "Proves this exact record was one of the records the issuer sealed in that block.")
        try:
            recomputed = block_hash(header)
        except (TypeError, ValueError):
            recomputed = ""
        ok3 = recomputed == claimed_hash
        step("block_hash", "Block header hash", ok3,
             "recomputed %s %s %s" % (_short(recomputed), "==" if ok3 else "!=", _short(claimed_hash)),
             "The header commits to the Merkle root, previous block, time and nonce.")
        diff = header.get("difficulty")
        ok4 = isinstance(diff, int) and diff >= config.MIN_DIFFICULTY and meets_pow(recomputed, diff)
        step("pow", "Proof-of-work", ok4,
             "hash starts with %s zero(s) (required %s)" % (len(recomputed) - len(recomputed.lstrip("0")), diff),
             "Re-mining a block costs work, so rewriting history is slow, not free.")
        issuer_id = header.get("issuer_id")
        pub = self.public_key_of(issuer_id)
        auth = self.authorities().get(issuer_id, {})
        sig_ok = False
        if pub and rec.get("issuer_id") == issuer_id:
            try:
                sig_ok = ed25519.verify(bytes.fromhex(pub), block_sig_message(recomputed), bytes.fromhex(sig_hex))
            except ValueError:
                sig_ok = False
        if not pub:
            detail = "issuer '%s' is not in the on-chain registry" % issuer_id
        elif rec.get("issuer_id") != issuer_id:
            detail = "record claims issuer %s but block was signed by %s" % (rec.get("issuer_id"), issuer_id)
        else:
            detail = "Ed25519 signature by %s (key %s) %s" % (auth.get("name", issuer_id), _short(pub),
                                                               "verifies" if sig_ok else "does NOT verify")
        step("issuer_signature", "Issuer signature", sig_ok, detail,
             "Only the institution's private key can produce this; a forger cannot.")

        idx = header.get("index")
        anchored = False
        if isinstance(idx, int) and 0 <= idx < len(self.blocks) and self.blocks[idx].get("hash") == claimed_hash:
            anchored = True
        if validation is None:
            validation = self.validate()
        bad_near = [i for i in validation["broken_blocks"] if isinstance(idx, int) and i <= idx + 1]
        ok6 = anchored and not bad_near
        if not anchored:
            d6 = "block %s with this hash is not on the ledger" % idx
        elif bad_near:
            d6 = "ledger validation failed at block(s) %s" % ", ".join(map(str, bad_near))
        else:
            d6 = "block %s is on the ledger; %d blocks validated%s" % (
                idx, validation["block_count"],
                "" if validation["valid"] else " (other blocks broken: %s)" % validation["broken_blocks"])
        step("anchored", "Anchored on the ledger, links intact", ok6, d6,
             "Each block stores the previous block's hash; editing any block breaks every link after it.")

        rev = self.revocations().get(cert_id)
        revocation = None
        if rev:
            revocation = {"block": rev[0], "reason": rev[1].get("reason"), "revoked_at": rev[1].get("revoked_at")}
        step("not_revoked", "Not revoked", rev is None,
             "no revocation entry" if rev is None else
             "revoked on %s in block %d: %s" % (rev[1].get("revoked_at"), rev[0], rev[1].get("reason")),
             "Issuers publish signed revocations on-chain (e.g. issued in error, misconduct).")
        return self._verdict(steps, bundle, t0, revocation=revocation, issuer=auth)

    @staticmethod
    def _verdict(steps, bundle, t0, revocation=None, issuer=None):
        valid = all(s["ok"] for s in steps)
        failed = [s for s in steps if not s["ok"]]
        if valid:
            summary = "Genuine, unaltered and currently valid."
        elif len(failed) == 1 and failed[0]["key"] == "not_revoked":
            summary = "Genuine record, but the issuer has REVOKED it."
        else:
            summary = "Failed: " + ", ".join(s["title"] for s in failed) + "."
        rec = bundle.get("record") if bundle else None
        return {
            "valid": valid,
            "verdict": "VALID" if valid else ("REVOKED" if revocation and len(failed) == 1 else "INVALID"),
            "summary": summary,
            "steps": steps,
            "cert_id": rec.get("cert_id") if rec else None,
            "record": rec,
            "block_index": bundle["block"]["header"].get("index") if bundle else None,
            "issuer": {"id": issuer.get("inst_id"), "name": issuer.get("name"),
                       "city": issuer.get("city")} if issuer else None,
            "revocation": revocation,
            "verify_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
