"""The voter's side of the protocol, in Python (the browser runs the same steps in crypto.js).

Used by the demo generator, the "simulate voters" button, the benchmarks and the tests.
"""

import secrets

from . import blind, commitment, seal
from .util import canonical, sha256_hex

_SYSRAND = secrets.SystemRandom()


class VoterDevice(object):
    """Everything here stays on the voter's phone; the server only ever sees `blinded`."""

    def __init__(self, eid, issuer_pub, trustee_pub, rng=None):
        self.eid = eid
        self.issuer = issuer_pub
        self.trustee = trustee_pub
        self.rng = rng or _SYSRAND
        self.token = None
        self.r = None
        self.blinded = None
        self.sig = None
        self.receipt = None

    def prepare_token(self):
        self.token = blind.new_token(self.rng)
        self.blinded, self.r = blind.blind(self.issuer, blind.token_message(self.eid, self.token), self.rng)
        return self.blinded

    def finish_token(self, blind_sig):
        sig = blind.unblind(self.issuer, blind_sig, self.r)
        if not blind.verify_token(self.issuer, self.eid, self.token, sig):
            raise ValueError("authority returned an invalid blind signature")
        self.sig = sig
        self.r = None  # the blinding factor is the only link; forget it
        return sig

    def build_ballot(self, choices):
        nonce = commitment.new_nonce(self.rng)
        c = commitment.commit(self.eid, self.token, choices, nonce)
        sealed = seal.seal(self.trustee, canonical({"choices": choices, "nonce": nonce}), self.token, self.rng)
        self.receipt = {"token_hash": sha256_hex(self.token), "commitment": c, "choices": choices, "nonce": nonce}
        return {"token": self.token, "sig": "%x" % self.sig, "commitment": c, "sealed": sealed}
