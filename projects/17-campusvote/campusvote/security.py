"""Threat model shown in the UI (Attack lab) and in REPORT.md. Honest about what is NOT solved."""

THREATS = [
    {"threat": "Double voting (second token)", "attacker": "Student",
     "defence": "Authority serves each register number once; re-sending the same blinded value returns the same signature",
     "status": "Prevented", "demo": "double_token"},
    {"threat": "Double voting / replay (same token twice)", "attacker": "Student or network",
     "defence": "A token may appear on the board once; checked at cast time and by every auditor",
     "status": "Prevented", "demo": "replay"},
    {"threat": "Forged ballot token", "attacker": "Anyone",
     "defence": "RSA-FDH signature s^e = FDH(token) mod n with a 2048-bit key; FDH blocks multiplicative forgery",
     "status": "Prevented", "demo": "forge_multiply"},
    {"threat": "Cross-election replay", "attacker": "Anyone",
     "defence": "The election id is inside the signed message",
     "status": "Prevented", "demo": "cross_election"},
    {"threat": "Guessing a student's one-time code", "attacker": "Classmate",
     "defence": "Lockout after 5 tries; salted PBKDF2 hashes at rest",
     "status": "Prevented", "demo": "otp_bruteforce"},
    {"threat": "Authority links a voter to their vote", "attacker": "Admin / authority",
     "defence": "Chaum blind signatures: every issuance record is equally consistent with every ballot",
     "status": "Prevented (information-theoretic)", "demo": "link_attempt"},
    {"threat": "Timing / network linkage of a ballot to its sender", "attacker": "Admin watching the server",
     "defence": "Ballots carry no login; shuffled batches in a mix pool with one batch time; no IPs logged on /api/ballot",
     "status": "Mitigated (simulated mix; one server)", "demo": None},
    {"threat": "Admin edits or deletes a stored ballot", "attacker": "Insider with DB/file access",
     "defence": "Hash chain pinpoints the entry; signed checkpoints catch re-hashing; voter receipts hold entry hashes",
     "status": "Detected", "demo": "tamper_edit"},
    {"threat": "Admin peeks at running totals", "attacker": "Admin",
     "defence": "Board holds only hiding commitments; openings are sealed to a separate trustee key",
     "status": "Mitigated (trustee key holder could open early)", "demo": None},
    {"threat": "Trustee changes or drops votes when opening", "attacker": "Trustee",
     "defence": "Binding commitments: a false opening cannot match; spoiled ballots are listed by token for voters to contest",
     "status": "Detected", "demo": None},
    {"threat": "Ballot stuffing by the signing-key holder", "attacker": "Corrupt authority",
     "defence": "Public issuance log: ballots must not exceed tokens issued",
     "status": "Partly detected (up to issued-minus-cast is invisible)", "demo": "stuffing"},
    {"threat": "Coercion / vote buying", "attacker": "Coercer",
     "defence": "None cryptographic: a voter can reveal token + opening to prove their vote",
     "status": "NOT solved (receipts are not coercion-resistant)", "demo": None},
    {"threat": "Malware on the voter's phone", "attacker": "Malware",
     "defence": "Out of scope; voter can re-check their opened choice after the tally",
     "status": "Out of scope", "demo": None},
]

LIMITS = [
    "Receipts give individual verifiability, so they also let a voter PROVE how they voted to a buyer or coercer. "
    "CampusVote is not receipt-free; for student elections we accept this, and supervised polling booths "
    "(phones handed in, kiosk voting) reduce the risk.",
    "One trustee key opens the sealed choices. Whoever holds it could compute interim totals (still without knowing "
    "who voted what). Splitting it with Shamir secret sharing among 3 faculty is the next step.",
    "The anonymous channel is simulated by a mix pool on the same server. A real deployment should use a separate "
    "mix operator or Tor-style relay so the server never sees ballot IPs.",
    "Keys in data/keys.json are DEMO keys committed to the repo. A real election generates fresh keys offline "
    "and publishes only the fingerprints.",
    "A low-turnout batch (1 ballot after the timeout) gives little timing cover; real mixes wait for larger batches.",
]
