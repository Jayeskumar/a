"""Chaum RSA blind signatures over a full-domain hash.

Voter (secret token t, random r)        Authority (d)
  m  = FDH("CV1-token|eid|t")
  m' = m * r^e mod n          ---- m' --->   checks eligibility, one per voter
                              <--- s' ----   s' = m'^d mod n
  s  = s' * r^-1 mod n  ( = m^d )
  verify s^e == m

Blindness: for ANY issued pair (m', s') and ANY ballot (t, s), the factor r = s' * s^-1
satisfies FDH(t) * r^e == m'. Every pairing is equally consistent, so the authority's
records carry zero information about which ballot belongs to which voter.
"""

import secrets

from .numtheory import gcd, modinv
from .rsa import fdh

_SYSRAND = secrets.SystemRandom()


def token_message(eid, token_hex):
    """The exact bytes whose FDH gets signed. Binding the election id stops cross-election replay."""
    return ("CV1-token|%s|%s" % (eid, token_hex)).encode("utf-8")


def new_token(rng=None):
    return "%064x" % (rng or _SYSRAND).getrandbits(256)


def random_unit(n, rng=None):
    """Uniform r in [2, n-2] with gcd(r, n) == 1 (fails only if r reveals a factor of n)."""
    rng = rng or _SYSRAND
    while True:
        r = 2 + rng.randrange(n - 3)
        if gcd(r, n) == 1:
            return r


def blind(pub, message, rng=None):
    """Returns (blinded m', blinding factor r). Run on the voter's device."""
    m = fdh(message, pub.n)
    r = random_unit(pub.n, rng)
    return (m * pow(r, pub.e, pub.n)) % pub.n, r


def sign_blinded(priv, blinded):
    """Authority side: it signs m' without learning m (or the token)."""
    if not 1 < blinded < priv.n - 1:
        raise ValueError("blinded value out of range")
    return priv.raw_sign(blinded)


def unblind(pub, blind_sig, r):
    return (blind_sig * modinv(r, pub.n)) % pub.n


def verify_token(pub, eid, token_hex, sig):
    return isinstance(sig, int) and pub.raw_verify(fdh(token_message(eid, token_hex), pub.n), sig)


def linking_factor(pub, blinded, blind_sig, eid, token_hex, sig):
    """The blinding factor that WOULD link issuance (m', s') to ballot (t, s).

    Returns (r, consistent). ``consistent`` is True for every valid pairing - which is
    exactly why linking is impossible.
    """
    r = (blind_sig * modinv(sig, pub.n)) % pub.n
    m = fdh(token_message(eid, token_hex), pub.n)
    return r, (m * pow(r, pub.e, pub.n)) % pub.n == blinded
