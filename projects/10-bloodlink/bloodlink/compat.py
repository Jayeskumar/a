"""ABO/Rh compatibility, derived from antigens/antibodies rather than a lookup table.

Red cells (packed RBC / whole blood for red-cell replacement)
    The donor's red cells must not carry an antigen the recipient's plasma attacks:
    donor ABO antigens must be a subset of the recipient's, and RhD-positive cells
    only go to RhD-positive recipients.

Plasma (FFP)
    The donor's plasma antibodies must not attack the recipient's red cells: donor ABO
    antigens must be a SUPERSET of the recipient's (AB plasma is the universal plasma).
    RhD is not considered for plasma here (plasma carries no meaningful red cells).

Platelets and cryoprecipitate have their own nuanced rules and are out of scope.
"""
from .config import BLOOD_GROUPS, COMPAT_PENALTY_ABO, COMPAT_PENALTY_RH

ABO_ANTIGENS = {"O": frozenset(), "A": frozenset("A"), "B": frozenset("B"), "AB": frozenset("AB")}


class GroupError(ValueError):
    pass


def parse_group(group):
    """'AB+' -> ('AB', True). Accepts a few spellings: 'ab pos', 'O neg', 'B+ve'."""
    if not isinstance(group, str):
        raise GroupError("blood group must be a string like 'A+'")
    g = group.strip().upper().replace(" ", "").replace("VE", "")
    g = g.replace("POS", "+").replace("NEG", "-").replace("−", "-")
    if g.endswith("+") or g.endswith("-"):
        abo, rh = g[:-1], g[-1] == "+"
        if abo in ABO_ANTIGENS:
            return abo, rh
    raise GroupError("unknown blood group %r (use one of %s)" % (group, ", ".join(BLOOD_GROUPS)))


def normalize(group):
    abo, rh = parse_group(group)
    return abo + ("+" if rh else "-")


def red_cell_compatible(donor, recipient):
    """True if the donor's red cells can be given to the recipient."""
    d_abo, d_rh = parse_group(donor)
    r_abo, r_rh = parse_group(recipient)
    return ABO_ANTIGENS[d_abo] <= ABO_ANTIGENS[r_abo] and (r_rh or not d_rh)


def plasma_compatible(donor, recipient):
    """True if the donor's plasma can be given to the recipient (ABO only)."""
    d_abo, _ = parse_group(donor)
    r_abo, _ = parse_group(recipient)
    return ABO_ANTIGENS[d_abo] >= ABO_ANTIGENS[r_abo]


def red_cell_donors_for(recipient):
    """Acceptable red-cell donor groups for a recipient, exact match first."""
    rec = normalize(recipient)
    groups = [g for g in BLOOD_GROUPS if red_cell_compatible(g, rec)]
    return sorted(groups, key=lambda g: (-compat_score(g, rec), BLOOD_GROUPS.index(g)))


def red_cell_recipients_of(donor):
    return [g for g in BLOOD_GROUPS if red_cell_compatible(donor, g)]


def compat_score(donor, recipient):
    """1.0 for an exact match; lower when a scarcer group is used for a patient who could
    take a commoner one. 0.0 if incompatible."""
    if not red_cell_compatible(donor, recipient):
        return 0.0
    d_abo, d_rh = parse_group(donor)
    r_abo, r_rh = parse_group(recipient)
    score = 1.0
    if d_rh != r_rh:
        score -= COMPAT_PENALTY_RH
    if d_abo != r_abo:
        score -= COMPAT_PENALTY_ABO
    return round(score, 4)


def compat_reason(donor, recipient):
    """Human-readable reason for compatible / incompatible."""
    d, r = normalize(donor), normalize(recipient)
    d_abo, d_rh = parse_group(d)
    r_abo, r_rh = parse_group(r)
    if d == r:
        return "Exact match %s" % d
    missing = sorted(ABO_ANTIGENS[d_abo] - ABO_ANTIGENS[r_abo])
    if missing:
        return "%s red cells carry %s antigen; %s plasma has anti-%s" % (
            d, "/".join(missing), r, "/anti-".join(missing))
    if d_rh and not r_rh:
        return "%s cells are RhD-positive; %s patient may form anti-D" % (d, r)
    parts = []
    if d_abo != r_abo:
        parts.append("group %s cells suit %s" % (d_abo, r_abo))
    if d_rh != r_rh:
        parts.append("Rh-negative cells suit Rh-positive")
    return "Compatible (%s) - uses scarcer %s stock" % ("; ".join(parts), d)


def matrix(product="red"):
    """{recipient: {donor: bool}} for all 8x8 pairs."""
    fn = red_cell_compatible if product == "red" else plasma_compatible
    return {r: {d: fn(d, r) for d in BLOOD_GROUPS} for r in BLOOD_GROUPS}
