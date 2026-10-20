"""Tunable constants, kept in one place.

None of these are real-world statistics; they are engineering choices.
"""

# Proof-of-work difficulty = number of leading hex zeros in the block hash.
# 4 hex zeros = 16 bits = ~65,536 SHA-256 attempts on average, i.e. roughly
# 0.1-0.3 s in CPython on a laptop. In a *permissioned* chain PoW is not the
# consensus mechanism (the issuer signature is); it is a rate-limit / cost
# that makes mass rewriting of history slower. Keep it small for live demos.
POW_DIFFICULTY = 4
MIN_DIFFICULTY = 3          # blocks below this are rejected during validation

GENESIS_PREV_HASH = "0" * 64
CHAIN_VERSION = 1

# Domain-separation prefixes so a signature for one purpose can never be
# replayed as a signature for another.
BLOCK_SIG_PREFIX = b"CertChain-block-v1:"
REVOCATION_SIG_PREFIX = b"CertChain-revocation-v1:"

CONSORTIUM_ID = "consortium"

CERT_TYPES = [
    "Degree Certificate",
    "Provisional Certificate",
    "Consolidated Marksheet",
    "Internship Certificate",
    "Course Completion Certificate",
]
# Certificate types where CGPA may be left blank (stored as "N/A").
CGPA_OPTIONAL_TYPES = {"Internship Certificate", "Course Completion Certificate"}

MAX_BULK_ROWS = 500
MAX_BODY_BYTES = 2 * 1024 * 1024
