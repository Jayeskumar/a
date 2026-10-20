"""Hash commitment to a voter's choices.

C = SHA-256("CV1-commit|" eid "|" token "|" canonical(choices) "|" nonce)

* Hiding: the 256-bit random nonce makes C look random, so nobody (not even the server)
  can learn choices or running totals from the board while voting is open.
* Binding: changing the opened choices needs a SHA-256 second preimage, so once C is on the
  board neither the voter nor the authority can change the vote.
Mirrored in static/crypto.js (commitBallot).
"""

import hashlib
import hmac
import secrets

from .util import canonical

_SYSRAND = secrets.SystemRandom()


def new_nonce(rng=None):
    return "%064x" % (rng or _SYSRAND).getrandbits(256)


def commit(eid, token_hex, choices, nonce_hex):
    data = ("CV1-commit|%s|%s|" % (eid, token_hex)).encode("utf-8") + canonical(choices) + \
        ("|" + nonce_hex).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_opening(eid, token_hex, choices, nonce_hex, commitment):
    if not isinstance(choices, dict) or not isinstance(nonce_hex, str) or not isinstance(commitment, str):
        return False
    return hmac.compare_digest(commit(eid, token_hex, choices, nonce_hex), commitment)
