"""RSA from scratch: key generation, CRT signing, full-domain hash (RSA-FDH).

Textbook RSA is malleable (s1*s2 signs m1*m2). We never sign raw numbers chosen by an
attacker *as messages*: every message is first mapped through a full-domain hash, so a
forger would need a token whose hash equals some chosen product - a SHA-256 preimage.
(Blind signing deliberately signs a value the authority cannot see; FDH is what keeps
that safe - see blind.py.)
"""

import hashlib
import secrets

from . import config
from .numtheory import gcd, gen_prime, modinv
from .util import sha256_hex

_SYSRAND = secrets.SystemRandom()


def i2osp(x, k):
    return x.to_bytes(k, "big")


def os2ip(b):
    return int.from_bytes(b, "big")


def fdh(message, n):
    """Full-domain hash: SHA-256 in counter mode, truncated to |n|-1 bits so the result < n.

    out = SHA256(FDH_DOMAIN || ctr_32be || message) for ctr = 0, 1, ...
    Mirrored exactly in static/crypto.js (fdh).
    """
    if isinstance(message, str):
        message = message.encode("utf-8")
    outbits = n.bit_length() - 1
    k = (outbits + 7) // 8
    buf = b""
    ctr = 0
    while len(buf) < k:
        buf += hashlib.sha256(config.FDH_DOMAIN + ctr.to_bytes(4, "big") + message).digest()
        ctr += 1
    return os2ip(buf[:k]) >> (8 * k - outbits)


class PublicKey(object):
    def __init__(self, n, e):
        self.n = n
        self.e = e

    @property
    def bits(self):
        return self.n.bit_length()

    @property
    def size(self):
        """Modulus length in bytes (k in PKCS#1)."""
        return (self.n.bit_length() + 7) // 8

    def fingerprint(self):
        return sha256_hex("%x:%x" % (self.n, self.e))[:16]

    def raw_verify(self, m, s):
        return 0 < s < self.n and pow(s, self.e, self.n) == m

    def public_dict(self):
        return {"n": "%x" % self.n, "e": self.e, "bits": self.bits, "fp": self.fingerprint()}

    @classmethod
    def from_dict(cls, d):
        return cls(int(d["n"], 16), int(d["e"]))

    def public(self):
        return PublicKey(self.n, self.e)


class PrivateKey(PublicKey):
    def __init__(self, n, e, d, p, q):
        super(PrivateKey, self).__init__(n, e)
        self.d, self.p, self.q = d, p, q
        self.dp = d % (p - 1)
        self.dq = d % (q - 1)
        self.qinv = modinv(q, p)

    def raw_sign(self, m):
        """m^d mod n via the Chinese Remainder Theorem (~3-4x faster than a direct pow).

        The result is verified before release: a computational fault in one CRT half would
        otherwise leak a factor of n (Boneh-DeMillo-Lipton / Bellcore attack).
        """
        if not 0 <= m < self.n:
            raise ValueError("message representative out of range")
        s1 = pow(m % self.p, self.dp, self.p)
        s2 = pow(m % self.q, self.dq, self.q)
        h = (self.qinv * (s1 - s2)) % self.p
        s = s2 + h * self.q
        if pow(s, self.e, self.n) != m:
            raise RuntimeError("RSA-CRT self-check failed")
        return s

    def raw_decrypt(self, c):
        return self.raw_sign(c)

    def private_dict(self):
        d = self.public_dict()
        d.update({"d": "%x" % self.d, "p": "%x" % self.p, "q": "%x" % self.q})
        return d

    @classmethod
    def from_dict(cls, d):
        key = cls(int(d["n"], 16), int(d["e"]), int(d["d"], 16), int(d["p"], 16), int(d["q"], 16))
        if key.p * key.q != key.n:
            raise ValueError("corrupt key: p*q != n")
        return key


def generate_keypair(bits=None, rng=None, e=None, stats=None):
    """RSA key generation with our own Miller-Rabin primes.

    d = e^-1 mod lcm(p-1, q-1) (Carmichael's lambda, as in FIPS 186-4).
    """
    bits = bits or config.RSA_BITS
    e = e or config.PUBLIC_EXPONENT
    rng = rng or _SYSRAND
    half = bits // 2
    while True:
        p = gen_prime(half, rng, e=e, stats=stats)
        q = gen_prime(bits - half, rng, e=e, stats=stats)
        if p == q:
            continue
        # FIPS 186-4: |p - q| must exceed 2^(bits/2 - 100) to resist Fermat factoring.
        if abs(p - q) <= (1 << max(half - 100, 1)):
            continue
        if p < q:
            p, q = q, p
        n = p * q
        if n.bit_length() != bits:
            continue
        lam = (p - 1) * (q - 1) // gcd(p - 1, q - 1)
        d = modinv(e, lam)
        return PrivateKey(n, e, d, p, q)


def sign_message(priv, message):
    """RSA-FDH signature on bytes/str."""
    return priv.raw_sign(fdh(message, priv.n))


def verify_message(pub, message, sig):
    return isinstance(sig, int) and pub.raw_verify(fdh(message, pub.n), sig)
