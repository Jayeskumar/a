"""Urgency: transparent safety rules + a learned P1..P4 model, combined with an explanation.

Rules match on language-neutral *concepts*, so "live wire hanging", "மின் கம்பி அறுந்து
தொங்குகிறது" and "current wire thongitu iruku" all fire the same rule.

* critical rule  -> priority forced to P1 (a person could get hurt; never wait for a model)
* high rule      -> priority at least P2
* soft rule      -> only a feature the model weighs (school nearby, elderly, a week pending ...)
"""

import re

from .text import concepts

# id, label, kind, any-of concept sets
RULES = [
    ("live_wire", "Live / fallen electric wire", "critical",
     [{"live", "wire"}, {"wire", "hanging"}, {"wire", "fallen"}, {"wire", "snapped"}, {"current", "leak"}, {"shock"}]),
    ("sewage_drinking", "Sewage in drinking water", "critical",
     [{"sewage", "drinkingwater"}, {"sewage", "drinking"}]),
    ("open_manhole", "Open manhole", "critical",
     [{"manhole", "open"}, {"manhole", "cover"}, {"manhole", "missing"}]),
    ("accident", "Accident reported", "critical", [{"accident"}, {"bike", "fallen"}]),
    ("dog_bite", "Dog bite", "critical", [{"dog", "bite"}]),
    ("tree_fall", "Fallen / falling tree", "high", [{"tree", "fallen"}, {"tree", "block"}, {"tree", "tilted"}, {"branch", "fallen"}]),
    ("pole_tilt", "Tilted electric pole", "high", [{"pole", "tilted"}, {"pole", "fallen"}]),
    ("burning", "Burning / smoke", "soft", [{"burning"}, {"smoke"}]),
    ("children", "Children / school nearby", "soft", [{"children"}, {"school"}]),
    ("elderly", "Elderly affected", "soft", [{"elderly"}]),
    ("sick", "Illness reported", "soft", [{"sick"}, {"fever"}, {"dengue"}]),
    ("long_wait", "Pending a week or more", "soft", [{"week"}]),
    ("danger", "Citizen says dangerous", "soft", [{"danger"}]),
    ("no_water", "No water supply", "soft", [{"nowater"}, {"water", "notcoming"}, {"supply", "no"}]),
    ("dark", "Dark at night", "soft", [{"dark"}]),
]
RULE_IDS = [r[0] for r in RULES]
RULE_LABEL = {r[0]: r[1] for r in RULES}
RULE_KIND = {r[0]: r[2] for r in RULES}


_DAYS = re.compile(r"(\d+)\s*(?:days?|naala|naal|நாட்க|நாள்)", re.I)


def long_wait_days(text):
    """Largest 'N days' mentioned in the text (English, Tanglish or Tamil), else 0."""
    return max([int(m.group(1)) for m in _DAYS.finditer(str(text)) if len(m.group(1)) <= 3] or [0])


def fired_rules(text, cons=None):
    """Rules that fire on a complaint text (concepts can be passed in if already computed)."""
    cs = set(cons if cons is not None else concepts(text))
    if long_wait_days(text) >= 7:
        cs.add("week")
    out = []
    for rid, label, kind, alts in RULES:
        for alt in alts:
            if alt <= cs:
                out.append({"id": rid, "label": label, "kind": kind, "matched": sorted(alt)})
                break
    return out


def rule_features(fired, offset):
    """Sparse (index, 1.0) pairs for the rules that fired, placed after the text vocabulary."""
    return [(offset + RULE_IDS.index(f["id"]), 1.0) for f in fired]


def rules_only_priority(fired):
    kinds = {f["kind"] for f in fired}
    if "critical" in kinds:
        return 1
    if "high" in kinds:
        return 2
    soft = sum(1 for f in fired if f["kind"] == "soft")
    return 2 if soft >= 2 else 3


def combine(probs, fired):
    """probs: [p(P1), p(P2), p(P3), p(P4)] from the model. Returns (priority, reason)."""
    model_p = max(range(4), key=probs.__getitem__) + 1
    crit = [f for f in fired if f["kind"] == "critical"]
    high = [f for f in fired if f["kind"] == "high"]
    if crit:
        return 1, "Safety rule '%s' forces P1" % crit[0]["label"]
    if high and model_p > 2:
        return 2, "Rule '%s' lifts the model's P%d to P2" % (high[0]["label"], model_p)
    return model_p, "Model: P%d with %.0f%% probability" % (model_p, 100 * probs[model_p - 1])
