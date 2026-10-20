"""Application service: persistence in data/*.json and the use-cases the
HTTP layer exposes (issue, bulk issue, revoke, verify, tamper, restore)."""

import csv
import datetime
import io
import json
import os
import secrets
import shutil
import threading

from . import config, demo, merkle, qr
from .chain import Ledger, block_hash
from .ed25519 import KeyPair
from .records import (ValidationError, clean_certificate_input, make_certificate,
                      make_revocation, record_hash)


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CertChainService(object):
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.keys_path = os.path.join(data_dir, "keys.json")
        self.chain_path = os.path.join(data_dir, "chain.json")
        self.backup_path = os.path.join(data_dir, "chain.backup.json")
        self.lock = threading.RLock()
        self.ensure_initialised()

    # -- persistence ------------------------------------------------------
    def ensure_initialised(self):
        with self.lock:
            if not (os.path.exists(self.keys_path) and os.path.exists(self.chain_path)):
                demo.write_demo(self.data_dir)

    def _keys(self):
        with open(self.keys_path, encoding="utf-8") as f:
            return json.load(f)

    def _raw_chain(self):
        with open(self.chain_path, encoding="utf-8") as f:
            return json.load(f)

    def _write_chain(self, raw):
        tmp = self.chain_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.chain_path)

    def ledger(self):
        """Always read from disk: the tamper demo edits the file directly."""
        try:
            blocks = self._raw_chain().get("blocks", [])
        except (ValueError, OSError):
            blocks = []
        return Ledger(blocks, self._keys()["consortium"]["public_key"])

    def _keypair(self, issuer_id):
        for inst in self._keys()["institutions"]:
            if inst["id"] == issuer_id:
                return inst, KeyPair(bytes.fromhex(inst["secret_seed"]))
        raise NotFound("unknown issuer '%s'" % issuer_id)

    def _require_valid(self, led):
        rep = led.validate()
        if not rep["valid"]:
            raise Conflict("Ledger integrity check failed at block %s - refusing to extend a "
                           "tampered chain. Restore it first." % rep["first_bad_block"])
        return rep

    # -- read models ------------------------------------------------------
    def institutions(self):
        led = self.ledger()
        counts = {}
        for cid, (bi, ri) in led.cert_index().items():
            iss = led.blocks[bi]["records"][ri].get("issuer_id")
            counts[iss] = counts.get(iss, 0) + 1
        out = []
        for inst_id, a in led.authorities().items():
            out.append({"id": inst_id, "name": a["name"], "code": a["code"], "city": a.get("city"),
                        "public_key": a["public_key"], "certificates": counts.get(inst_id, 0)})
        return out

    def stats(self):
        with self.lock:
            led = self.ledger()
            rep = led.validate()
            n_certs = len(led.cert_index())
            n_rev = len(led.revocations())
            return {
                "blocks": len(led.blocks),
                "certificates": n_certs,
                "revocations": n_rev,
                "active": n_certs - n_rev,
                "institutions": len(led.authorities()),
                "difficulty": config.POW_DIFFICULTY,
                "chain_valid": rep["valid"],
                "broken_blocks": rep["broken_blocks"],
                "validation_ms": rep["validation_ms"],
                "tip_hash": led.tip["hash"] if led.blocks else None,
                "last_block_time": led.tip["header"]["timestamp"] if led.blocks else None,
                "tampered": os.path.exists(self.backup_path),
            }

    def chain_summary(self):
        with self.lock:
            led = self.ledger()
            rep = led.validate()
            auth = led.authorities()
            out = []
            for b, rb in zip(led.blocks, rep["blocks"]):
                h = b.get("header", {})
                recs = []
                for r in b.get("records", []):
                    item = {"type": r.get("type"), "hash": record_hash(r)}
                    if r.get("type") == "certificate":
                        item.update(cert_id=r.get("cert_id"), student_name=r.get("student_name"),
                                    cert_type=r.get("cert_type"), cgpa=r.get("cgpa"))
                    elif r.get("type") == "revocation":
                        item.update(cert_id=r.get("cert_id"), reason=r.get("reason"))
                    elif r.get("type") == "authority":
                        item.update(inst_id=r.get("inst_id"), name=r.get("name"))
                    recs.append(item)
                signer = h.get("issuer_id")
                out.append({
                    "index": h.get("index"), "timestamp": h.get("timestamp"),
                    "hash": b.get("hash"), "prev_hash": h.get("prev_hash"),
                    "merkle_root": h.get("merkle_root"), "nonce": h.get("nonce"),
                    "difficulty": h.get("difficulty"), "issuer_id": signer,
                    "issuer_name": "CertChain Consortium" if signer == config.CONSORTIUM_ID
                    else auth.get(signer, {}).get("name", signer),
                    "signature": b.get("signature"), "records": recs,
                    "ok": rb["ok"], "link_ok": rb["link_ok"], "checks": rb["checks"],
                })
            return {"blocks": out, "validation": {k: rep[k] for k in
                                                  ("valid", "broken_blocks", "errors", "validation_ms")}}

    def block(self, index):
        led = self.ledger()
        if not 0 <= index < len(led.blocks):
            raise NotFound("no block %d" % index)
        return led.blocks[index]

    def certificates(self, query=""):
        led = self.ledger()
        revs = led.revocations()
        q = (query or "").lower()
        out = []
        for b in led.blocks:
            for r in b.get("records", []):
                if r.get("type") != "certificate":
                    continue
                if q and q not in (r.get("cert_id", "") + " " + r.get("student_name", "") + " " +
                                   r.get("register_no", "")).lower():
                    continue
                out.append({"cert_id": r.get("cert_id"), "student_name": r.get("student_name"),
                            "register_no": r.get("register_no"), "programme": r.get("programme"),
                            "cgpa": r.get("cgpa"), "cert_type": r.get("cert_type"),
                            "issue_date": r.get("issue_date"), "issuer_id": r.get("issuer_id"),
                            "block": b["header"].get("index"), "revoked": r.get("cert_id") in revs})
        return out

    def certificate(self, cert_id, base_url):
        with self.lock:
            led = self.ledger()
            bundle = led.certificate_bundle(cert_id)
            if bundle is None:
                raise NotFound("certificate %s not found" % cert_id)
            url = "%s/#verify=%s" % (base_url.rstrip("/"), cert_id)
            result = led.verify_bundle(bundle)
            return {"bundle": bundle, "verify_url": url, "qr_svg": qr.to_svg(url, module_px=4),
                    "status": {"valid": result["valid"], "verdict": result["verdict"],
                               "summary": result["summary"]}}

    # -- use cases -----------------------------------------------------------
    def _next_ids(self, led, inst, cleaned_rows):
        existing = set(led.cert_index())
        seq = sum(1 for cid in existing if cid.startswith(inst["code"] + "-"))
        ids = []
        for row in cleaned_rows:
            while True:
                seq += 1
                cid = "%s-%s-%05d" % (inst["code"], row["issue_date"][2:4], seq)
                if cid not in existing:
                    break
            existing.add(cid)
            ids.append(cid)
        return ids

    def _issue_rows(self, issuer_id, cleaned_rows):
        with self.lock:
            led = self.ledger()
            self._require_valid(led)
            inst, kp = self._keypair(issuer_id)
            if issuer_id not in led.authorities():
                raise Conflict("issuer %s is not registered on-chain" % issuer_id)
            ids = self._next_ids(led, inst, cleaned_rows)
            records = [make_certificate(cid, issuer_id, row, secrets.token_hex(16))
                       for cid, row in zip(ids, cleaned_rows)]
            block, stats = led.append(records, issuer_id, kp, utc_now())
            self._write_chain({"blocks": led.blocks})
            return led, block, stats, ids

    def issue(self, issuer_id, fields):
        cleaned = clean_certificate_input(fields)
        led, block, stats, ids = self._issue_rows(issuer_id, [cleaned])
        return {"cert_id": ids[0], "block_index": block["header"]["index"], "block_hash": block["hash"],
                "merkle_root": block["header"]["merkle_root"], "mining": stats,
                "bundle": led.certificate_bundle(ids[0])}

    def bulk_issue(self, issuer_id, csv_text):
        if not isinstance(csv_text, str) or not csv_text.strip():
            raise ValidationError("csv is empty")
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        need = {"student_name", "register_no", "programme", "cgpa", "issue_date", "cert_type"}
        if not reader.fieldnames or not need.issubset({(h or "").strip() for h in reader.fieldnames}):
            raise ValidationError("CSV header must contain: " + ", ".join(sorted(need)))
        rows, errors = [], []
        for n, row in enumerate(reader, start=2):
            row = {(k or "").strip(): v for k, v in row.items()}
            try:
                rows.append(clean_certificate_input(row))
            except ValidationError as exc:
                errors.append("line %d: %s" % (n, exc))
            if len(rows) + len(errors) > config.MAX_BULK_ROWS:
                raise ValidationError("at most %d rows per batch" % config.MAX_BULK_ROWS)
        if errors:
            raise ValidationError("; ".join(errors[:10]))
        if not rows:
            raise ValidationError("CSV has no data rows")
        led, block, stats, ids = self._issue_rows(issuer_id, rows)
        return {"issued": len(ids), "cert_ids": ids, "block_index": block["header"]["index"],
                "block_hash": block["hash"], "merkle_root": block["header"]["merkle_root"],
                "mining": stats}

    def revoke(self, issuer_id, cert_id, reason):
        reason = " ".join(str(reason or "").split())
        if not 3 <= len(reason) <= 200:
            raise ValidationError("reason: 3-200 characters")
        with self.lock:
            led = self.ledger()
            self._require_valid(led)
            loc = led.cert_index().get(cert_id)
            if loc is None:
                raise NotFound("certificate %s not found" % cert_id)
            rec = led.blocks[loc[0]]["records"][loc[1]]
            if rec["issuer_id"] != issuer_id:
                raise Conflict("only the issuing institution (%s) can revoke %s" % (rec["issuer_id"], cert_id))
            if cert_id in led.revocations():
                raise Conflict("%s is already revoked" % cert_id)
            _, kp = self._keypair(issuer_id)
            now = utc_now()
            rev = make_revocation(cert_id, issuer_id, reason, now, kp)
            block, stats = led.append([rev], issuer_id, kp, now)
            self._write_chain({"blocks": led.blocks})
            return {"cert_id": cert_id, "block_index": block["header"]["index"],
                    "block_hash": block["hash"], "signature": rev["signature"], "mining": stats}

    def verify(self, cert_id=None, bundle=None, code=None):
        with self.lock:
            led = self.ledger()
            if bundle is None:
                if not cert_id:
                    raise ValidationError("give cert_id or bundle")
                bundle = led.certificate_bundle(cert_id.strip().upper())
                if bundle is None:
                    return {"valid": False, "verdict": "NOT FOUND",
                            "summary": "No certificate with ID %s exists on the ledger - likely fake." % cert_id,
                            "steps": [{"key": "lookup", "title": "Certificate ID on ledger", "ok": False,
                                       "detail": "%s not found in %d blocks" % (cert_id, len(led.blocks)),
                                       "why": "Every genuine certificate is recorded on-chain at issue time."}],
                            "cert_id": cert_id, "record": None}
            elif not isinstance(bundle, dict):
                raise ValidationError("bundle must be a JSON object")
            return led.verify_bundle(bundle, printed_code=code or None)

    def validate(self):
        with self.lock:
            return self.ledger().validate()

    # -- tamper demo ---------------------------------------------------------
    def tamper(self, mode="edit", cert_id=None):
        if mode not in ("edit", "rehash"):
            raise ValidationError("mode must be 'edit' or 'rehash'")
        cert_id = (cert_id or demo.TAMPER_TARGET).strip().upper()
        with self.lock:
            raw = self._raw_chain()
            target = None
            for b in raw["blocks"]:
                for r in b["records"]:
                    if r.get("type") == "certificate" and r.get("cert_id") == cert_id:
                        target = (b, r)
            if target is None:
                raise NotFound("certificate %s not found" % cert_id)
            if not os.path.exists(self.backup_path):
                shutil.copyfile(self.chain_path, self.backup_path)
            b, r = target
            old = r.get("cgpa")
            new = "9.91" if old != "9.91" else "9.99"
            r["cgpa"] = new                               # the attacker's edit
            steps = ["Opened data/chain.json directly (no keys, bypassing the app)",
                     "Changed %s CGPA %s -> %s in block %d" % (cert_id, old, new, b["header"]["index"])]
            if mode == "rehash":
                hashes = [record_hash(x) for x in b["records"]]
                b["header"]["merkle_root"] = merkle.merkle_root(hashes)
                from .chain import mine
                nonce, hx, attempts, _ = mine(dict(b["header"], nonce=0), b["header"]["difficulty"])
                b["header"]["nonce"] = nonce
                b["hash"] = hx
                steps += ["Recomputed the block's Merkle root to hide the edit",
                          "Re-mined proof-of-work (%d attempts) -> new hash %s..." % (attempts, hx[:12]),
                          "Could NOT re-sign: the institution's private key is not in the database"]
            self._write_chain(raw)
            led = self.ledger()
            rep = led.validate()
            ver = led.verify_bundle(led.certificate_bundle(cert_id), validation=rep)
            return {"mode": mode, "cert_id": cert_id, "block_index": b["header"]["index"],
                    "old_cgpa": old, "new_cgpa": new, "attacker_steps": steps,
                    "validation": rep, "verification": ver}

    def restore(self):
        with self.lock:
            if not os.path.exists(self.backup_path):
                return {"restored": False, "message": "nothing to restore", "validation": self.validate()}
            os.replace(self.backup_path, self.chain_path)
            return {"restored": True, "message": "chain.json restored from backup",
                    "validation": self.validate()}

    def reset_demo(self):
        with self.lock:
            demo.write_demo(self.data_dir)
            return self.stats()
