"""Sealed openings: RSA-KEM + SHA-256 stream cipher + HMAC-SHA256 (encrypt-then-MAC).

Each ballot carries its commitment opening (choices + nonce) encrypted to the election
*trustee* key, so voters do not have to come back to reveal (the classic weakness of the
FOO'92 commitment protocol). The trustee opens all ballots only after voting closes.

  r  <- random in [2, n-2]          c0 = r^e mod n
  K  = SHA-256("CV1-KEM" || I2OSP(r, k))
  kE = HMAC(K, "enc")   kM = HMAC(K, "mac")
  ct = pt XOR (SHA-256(kE || 0) || SHA-256(kE || 1) || ...)
  tag = HMAC(kM, aad "|" hex(c0) "|" hex(ct))      aad = the ballot token

RSA-KEM is the ISO/IEC 18033-2 construction (IND-CCA2 in the random-oracle model);
binding the token as associated data stops anyone swapping sealed blobs between ballots.
Mirrored in static/crypto.js (seal).
"""

import hashlib
import hmac
import secrets

from . import config
from .rsa import i2osp
from .util import ValidationError, check_hex, int_to_hex, parse_hex_int

_SYSRAND = secrets.SystemRandom()
MAX_PLAINTEXT = 4096


class SealError(Exception):
    pass


def _keys(r, k):
    K = hashlib.sha256(config.KEM_DOMAIN + i2osp(r, k)).digest()
    return hmac.new(K, b"enc", hashlib.sha256).digest(), hmac.new(K, b"mac", hashlib.sha256).digest()


def _keystream(kenc, length):
    out = bytearray()
    i = 0
    while len(out) < length:
        out += hashlib.sha256(kenc + i.to_bytes(4, "big")).digest()
        i += 1
    return bytes(out[:length])


def _tag(kmac, aad, c0_hex, ct_hex):
    return hmac.new(kmac, ("%s|%s|%s" % (aad, c0_hex, ct_hex)).encode("utf-8"), hashlib.sha256).hexdigest()


def seal(pub, plaintext, aad, rng=None):
    if len(plaintext) > MAX_PLAINTEXT:
        raise ValueError("plaintext too long")
    rng = rng or _SYSRAND
    r = 2 + rng.randrange(pub.n - 3)
    c0_hex = int_to_hex(pow(r, pub.e, pub.n), pub.size)
    kenc, kmac = _keys(r, pub.size)
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(kenc, len(plaintext))))
    ct_hex = ct.hex()
    return {"c0": c0_hex, "ct": ct_hex, "tag": _tag(kmac, aad, c0_hex, ct_hex)}


def validate_sealed(sealed, pub):
    """Shape check done when a ballot arrives (content stays secret until the tally)."""
    if not isinstance(sealed, dict):
        raise ValidationError("sealed must be an object {c0, ct, tag}")
    c0 = check_hex(sealed.get("c0"), 2 * pub.size, "sealed.c0")
    if parse_hex_int(c0, pub.size, "sealed.c0") >= pub.n:
        raise ValidationError("sealed.c0 out of range")
    ct = sealed.get("ct")
    if not isinstance(ct, str) or not 2 <= len(ct) <= 2 * MAX_PLAINTEXT or len(ct) % 2:
        raise ValidationError("sealed.ct has a bad length")
    check_hex(ct, len(ct), "sealed.ct")
    check_hex(sealed.get("tag"), 64, "sealed.tag")
    return {"c0": c0, "ct": ct, "tag": sealed["tag"]}


def open_sealed(priv, sealed, aad):
    try:
        c0_hex, ct_hex, tag = sealed["c0"], sealed["ct"], sealed["tag"]
        c0 = int(c0_hex, 16)
        ct = bytes.fromhex(ct_hex)
    except (KeyError, TypeError, ValueError):
        raise SealError("malformed sealed opening")
    if not 0 < c0 < priv.n:
        raise SealError("c0 out of range")
    r = priv.raw_decrypt(c0)
    kenc, kmac = _keys(r, priv.size)
    if not hmac.compare_digest(_tag(kmac, aad, c0_hex, ct_hex), str(tag)):
        raise SealError("authentication tag mismatch (wrong ballot or corrupted)")
    return bytes(a ^ b for a, b in zip(ct, _keystream(kenc, len(ct))))
