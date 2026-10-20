"""Tunable constants, kept in one place with the reasoning behind each value."""

import os

PRODUCT = "CampusVote"
TAGLINE = "Verifiable, anonymous e-voting for student elections"
DOMAIN = "Cybersecurity & Blockchain Technology"
DEFAULT_PORT = 8017
PROTOCOL = "CampusVote-v1 (RSA-FDH blind signatures + SHA-256 commitments + RSA-KEM sealed openings)"

# --- cryptography ---------------------------------------------------------
# 2048-bit RSA is NIST SP 800-57's minimum for ~112-bit security (acceptable to 2030).
RSA_BITS = 2048
# 65537 is the standard public exponent: fast verification, no known small-e attacks with FDH.
PUBLIC_EXPONENT = 65537
# Miller-Rabin rounds. Error <= 4^-40 even for adversarially chosen inputs.
MR_ROUNDS = 40
# Trial division bound before Miller-Rabin (removes ~88% of random odd candidates cheaply).
TRIAL_DIVISION_BOUND = 2000
# Domain-separation prefixes: every hash/sign context gets its own label so a value
# produced in one context can never be replayed as another.
FDH_DOMAIN = b"CV1-FDH"
KEM_DOMAIN = b"CV1-KEM"

# --- bulletin board -----------------------------------------------------
# A signed checkpoint is appended after this many entries. Lower = finer tamper
# localisation, higher = less signing work. 25 keeps checkpoints ~4% of entries.
CHECKPOINT_EVERY = 25

# --- simulated anonymous channel (mix) -----------------------------------
# Ballots wait in a pool and are posted to the board in shuffled batches, so arrival
# time and order do not reveal which voter (who just got a token) sent which ballot.
MIX_BATCH = 4          # flush when this many ballots are waiting...
MIX_MAX_WAIT_S = 12    # ...or when the oldest has waited this long (demo-friendly)

# --- voter authentication -------------------------------------------------
OTP_DIGITS = 6
OTP_MAX_ATTEMPTS = 5          # lockout after 5 wrong codes: 5 / 10^6 = 0.0005% guess success
OTP_PBKDF2_ITERS = 10000      # slows offline guessing of stored code hashes (codes are low-entropy)
SESSION_TTL_S = 600           # a login session lives 10 min and is used for one token request

# --- server / input limits ------------------------------------------------
MAX_BODY_BYTES = 512 * 1024
MAX_ROSTER = 5000
MAX_POSTS = 8
MAX_CANDIDATES = 10
MAX_SIMULATE = 500

# Admin key protecting admin endpoints. DEMO default; override with an env var.
ADMIN_KEY = os.environ.get("CAMPUSVOTE_ADMIN_KEY", "ksrce-admin-2026")

# --- deterministic demo data ---------------------------------------------
DEMO_SEED = 2026
DEMO_EID = "KSRCE-SC-2026"
DEMO_STUDENTS = 200
DEMO_TOKENS = 168      # students who obtained a ballot token (84% - a plausible campus turnout)
DEMO_BALLOTS = 152     # of those, how many already cast a ballot when the demo opens
DEMO_WINDOW_DAYS = 30  # voting window stays open this long after the demo data is generated
