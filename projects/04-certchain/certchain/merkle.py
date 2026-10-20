"""Merkle tree with domain separation and inclusion proofs.

leaf  = SHA256(0x00 || record_hash)
node  = SHA256(0x01 || left || right)

Odd node counts: the last node is *promoted* unchanged to the next level
(it is NOT duplicated). Duplicating the last node, as Bitcoin does, lets
two different record lists share one root (CVE-2012-2459); promotion plus
the 0x00/0x01 prefixes avoids that and also blocks "a leaf posing as an
inner node" second-preimage tricks.

A proof is a list of {"side": "L"|"R", "hash": hex} steps from leaf to root.
"""

import hashlib

EMPTY_ROOT = hashlib.sha256(b"CertChain-empty-merkle").hexdigest()


def leaf_hash(record_hash_hex):
    return hashlib.sha256(b"\x00" + bytes.fromhex(record_hash_hex)).digest()


def node_hash(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def build_levels(record_hashes):
    """All tree levels, level[0] = leaves, level[-1] = [root] (raw bytes)."""
    if not record_hashes:
        return []
    level = [leaf_hash(h) for h in record_hashes]
    levels = [level]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(node_hash(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])            # promote the odd node
        level = nxt
        levels.append(level)
    return levels


def merkle_root(record_hashes):
    if not record_hashes:
        return EMPTY_ROOT
    return build_levels(record_hashes)[-1][0].hex()


def merkle_proof(record_hashes, index):
    """Inclusion proof for record_hashes[index]."""
    if not 0 <= index < len(record_hashes):
        raise IndexError("leaf index out of range")
    levels = build_levels(record_hashes)
    proof = []
    for level in levels[:-1]:
        if index % 2 == 1:
            proof.append({"side": "L", "hash": level[index - 1].hex()})
        elif index + 1 < len(level):
            proof.append({"side": "R", "hash": level[index + 1].hex()})
        # else: odd node promoted, no sibling at this level
        index //= 2
    return proof


def verify_proof(record_hash_hex, proof, root_hex):
    """Recompute the root from a leaf and its proof; compare to root_hex."""
    try:
        cur = leaf_hash(record_hash_hex)
        for step in proof:
            sib = bytes.fromhex(step["hash"])
            if len(sib) != 32:
                return False
            if step["side"] == "L":
                cur = node_hash(sib, cur)
            elif step["side"] == "R":
                cur = node_hash(cur, sib)
            else:
                return False
        return cur.hex() == root_hex
    except (ValueError, KeyError, TypeError):
        return False
