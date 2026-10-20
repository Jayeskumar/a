"""Certificate / revocation / authority records and canonical hashing."""

import base64
import datetime
import hashlib
import json
import re

from . import config
from . import ed25519


def canonical_json(obj):
    """Deterministic JSON bytes: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def record_hash(record):
    """SHA-256 of the canonical JSON of a record (the Merkle leaf input)."""
    return sha256_hex(canonical_json(record))


def verification_code(rec_hash_hex):
    """Short human-typable code printed on the certificate (8 base32 chars)."""
    digest = hashlib.sha256(b"CertChain-vcode:" + bytes.fromhex(rec_hash_hex)).digest()
    code = base64.b32encode(digest[:5]).decode("ascii")
    return code[:4] + "-" + code[4:8]


def normalise_code(code):
    return re.sub(r"[^A-Z2-7]", "", (code or "").upper())


class ValidationError(ValueError):
    pass


_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,79}$")
_REGNO_RE = re.compile(r"^[A-Za-z0-9/\-]{4,20}$")
_PROG_RE = re.compile(r"^[A-Za-z0-9 .,&()'\-/]{2,100}$")


def clean_certificate_input(fields):
    """Validate and normalise issuer form / CSV input. Raises ValidationError."""
    if not isinstance(fields, dict):
        raise ValidationError("expected an object")

    def s(key):
        v = fields.get(key, "")
        if v is None:
            v = ""
        if not isinstance(v, (str, int, float)):
            raise ValidationError("%s must be text" % key)
        return " ".join(str(v).split())

    name = s("student_name")
    if not _NAME_RE.match(name):
        raise ValidationError("student_name: 2-80 letters, spaces, . ' -")
    regno = s("register_no").upper()
    if not _REGNO_RE.match(regno):
        raise ValidationError("register_no: 4-20 letters/digits")
    prog = s("programme")
    if not _PROG_RE.match(prog):
        raise ValidationError("programme: 2-100 characters")
    ctype = s("cert_type") or "Degree Certificate"
    if ctype not in config.CERT_TYPES:
        raise ValidationError("cert_type must be one of: " + ", ".join(config.CERT_TYPES))
    raw_cgpa = s("cgpa")
    if raw_cgpa in ("", "N/A", "NA", "-"):
        if ctype not in config.CGPA_OPTIONAL_TYPES:
            raise ValidationError("cgpa is required for %s" % ctype)
        cgpa = "N/A"
    else:
        try:
            val = float(raw_cgpa)
        except ValueError:
            raise ValidationError("cgpa must be a number between 0 and 10")
        if not (0.0 <= val <= 10.0) or val != val:
            raise ValidationError("cgpa must be between 0 and 10")
        cgpa = "%.2f" % val
    date = s("issue_date")
    try:
        d = datetime.date.fromisoformat(date)
    except ValueError:
        raise ValidationError("issue_date must be YYYY-MM-DD")
    if not (1950 <= d.year <= 2100):
        raise ValidationError("issue_date year out of range")
    return {
        "student_name": name,
        "register_no": regno,
        "programme": prog,
        "cgpa": cgpa,
        "issue_date": d.isoformat(),
        "cert_type": ctype,
    }


def make_certificate(cert_id, issuer_id, cleaned, salt_hex):
    """A certificate record. The random salt stops anyone from brute-forcing
    a record's contents from its public hash (names + register numbers are
    low-entropy)."""
    rec = {"type": "certificate", "v": 1, "cert_id": cert_id,
           "issuer_id": issuer_id, "salt": salt_hex}
    rec.update(cleaned)
    return rec


def revocation_message(rev):
    body = {k: v for k, v in rev.items() if k != "signature"}
    return config.REVOCATION_SIG_PREFIX + canonical_json(body)


def make_revocation(cert_id, issuer_id, reason, revoked_at, keypair):
    rev = {"type": "revocation", "v": 1, "cert_id": cert_id,
           "issuer_id": issuer_id, "reason": reason, "revoked_at": revoked_at}
    rev["signature"] = keypair.sign(revocation_message(rev)).hex()
    return rev


def verify_revocation(rev, public_hex):
    try:
        return ed25519.verify(bytes.fromhex(public_hex), revocation_message(rev),
                              bytes.fromhex(rev.get("signature", "")))
    except (ValueError, TypeError):
        return False


def make_authority(inst, added_at):
    return {"type": "authority", "v": 1, "inst_id": inst["id"], "name": inst["name"],
            "code": inst["code"], "city": inst.get("city", ""),
            "public_key": inst["public_key"], "added_at": added_at}
