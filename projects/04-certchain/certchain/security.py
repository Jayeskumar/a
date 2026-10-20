"""Threat model shown in the UI (/api/security) and in REPORT.md."""

THREATS = [
    {
        "threat": "Forgery",
        "attack": "A fake certificate printed with a real college's name, logo and seal.",
        "defence": "Certificate ID must exist on-chain and the block must carry a valid Ed25519 "
                   "signature from the college's registered key. Without the private key a "
                   "forger cannot produce one.",
        "mechanism": "Ed25519 signature + on-chain lookup",
    },
    {
        "threat": "Tampering with a genuine certificate",
        "attack": "Editing the CGPA or programme on a real certificate (paper, PDF or JSON).",
        "defence": "The record hash changes, so the Merkle proof no longer reaches the signed "
                   "Merkle root. The printed verification code also stops matching.",
        "mechanism": "SHA-256 record hash + Merkle proof",
    },
    {
        "threat": "Database attacker",
        "attack": "Someone with write access to the ledger file edits a stored record, and may "
                  "even recompute the Merkle root and re-mine the block.",
        "defence": "Full-chain validation detects the changed Merkle root; a re-mined block "
                   "has a new hash that no longer matches the issuer's signature or the next "
                   "block's prev_hash. Nodes refuse to extend a broken chain.",
        "mechanism": "Hash links + PoW + block signatures",
    },
    {
        "threat": "Insider at a college",
        "attack": "A staff member issues a certificate for someone who never graduated, or "
                  "back-dates one.",
        "defence": "Cannot be prevented cryptographically, but every issuance is permanent, "
                   "timestamped and attributable to the signing institution; it can be audited "
                   "and revoked with a signed, public revocation entry.",
        "mechanism": "Append-only audit trail + signed revocation",
    },
    {
        "threat": "Key theft",
        "attack": "An attacker steals a college's signing key and issues fake certificates.",
        "defence": "Keys belong in an HSM / smart card (demo keeps them in data/keys.json). "
                   "The consortium can register a new key; certificates in blocks after the "
                   "compromise can be revoked in bulk. Per-block PoW slows mass issuance.",
        "mechanism": "Permissioned registry + revocation (key rotation is future work)",
    },
    {
        "threat": "Rogue institution / fake university",
        "attack": "A diploma mill sets up its own node and signs certificates.",
        "defence": "Only institutions registered by the consortium root key in an on-chain "
                   "authority record can sign blocks (permissioned chain).",
        "mechanism": "Consortium-signed authority registry",
    },
    {
        "threat": "Privacy leak",
        "attack": "Guessing a student's details from public hashes.",
        "defence": "Every record carries a 128-bit random salt, so hashes cannot be brute-forced "
                   "from name + register number.",
        "mechanism": "Salted record hashes",
    },
]

LIMITS = [
    "Pure-Python Ed25519 is correct (RFC 8032 vectors) but not constant-time.",
    "Single-node prototype: consensus between multiple college nodes is future work.",
    "Issuer endpoints have no login in the demo; production needs SSO + per-staff accounts.",
]
