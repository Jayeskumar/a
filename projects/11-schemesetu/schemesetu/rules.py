"""A tiny declarative rule language with three-valued (Kleene) logic.

A rule is JSON:

    {"all": [rule, ...]}        every child must pass
    {"any": [rule, ...]}        at least one child must pass
    {"not": rule}               negation
    {"fact": "annual_income", "op": "<=", "value": 250000}
    {"fact": "ration_card", "op": "in", "value": ["AAY", "PHH"]}
    {"fact": "applicant_age", "op": "between", "value": [18, 40]}   # inclusive
    {"fact": "land_ha", "op": "<=", "value": {"param": "SMALL_MARGINAL_MAX_HA"}}

Evaluation over a household profile (dict fact -> value) gives PASS, FAIL or
UNKNOWN. A fact that is absent (or None) makes its leaf UNKNOWN; UNKNOWN then
propagates by Kleene logic, so a scheme is only "possibly eligible" when the
missing answer could actually change the outcome:

    all: any FAIL -> FAIL, else any UNKNOWN -> UNKNOWN, else PASS
    any: any PASS -> PASS, else any UNKNOWN -> UNKNOWN, else FAIL
    not: PASS <-> FAIL, UNKNOWN stays UNKNOWN

Every evaluation returns a full trace (no short-circuit) so the UI can show
which condition passed or failed - the explainability requirement.
"""

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

OPS = ("==", "!=", "<", "<=", ">", ">=", "in", "not_in", "between")
_NUMERIC_OPS = ("<", "<=", ">", ">=", "between")


class RuleError(ValueError):
    """Raised for a malformed rule or an unknown parameter."""


# ---------------------------------------------------------------- validation
def validate(rule, known_facts=None, params=None, path="rule"):
    """Raise RuleError if `rule` is not a well-formed rule. Returns the set of facts used."""
    if not isinstance(rule, dict):
        raise RuleError("%s: must be an object" % path)
    keys = set(rule) - {"label"}
    if "all" in rule or "any" in rule:
        kind = "all" if "all" in rule else "any"
        if keys != {kind}:
            raise RuleError("%s: '%s' node must have no other keys" % (path, kind))
        kids = rule[kind]
        if not isinstance(kids, list) or not kids:
            raise RuleError("%s.%s: must be a non-empty list" % (path, kind))
        facts = set()
        for i, k in enumerate(kids):
            facts |= validate(k, known_facts, params, "%s.%s[%d]" % (path, kind, i))
        return facts
    if "not" in rule:
        if keys != {"not"}:
            raise RuleError("%s: 'not' node must have no other keys" % path)
        return validate(rule["not"], known_facts, params, path + ".not")
    if keys != {"fact", "op", "value"}:
        raise RuleError("%s: leaf needs exactly fact, op, value (got %s)" % (path, sorted(keys)))
    fact, op = rule["fact"], rule["op"]
    if not isinstance(fact, str) or not fact:
        raise RuleError("%s: fact must be a non-empty string" % path)
    if known_facts is not None and fact not in known_facts:
        raise RuleError("%s: unknown fact '%s'" % (path, fact))
    if op not in OPS:
        raise RuleError("%s: unknown op '%s'" % (path, op))
    value = resolve_value(rule["value"], params, path)
    if op in ("in", "not_in") and not isinstance(value, list):
        raise RuleError("%s: '%s' needs a list value" % (path, op))
    if op == "between":
        if not (isinstance(value, list) and len(value) == 2 and all(_is_num(v) for v in value)):
            raise RuleError("%s: 'between' needs [low, high] numbers" % path)
        if value[0] > value[1]:
            raise RuleError("%s: 'between' low > high" % path)
    elif op in _NUMERIC_OPS and not _is_num(value):
        raise RuleError("%s: '%s' needs a number" % (path, op))
    return {fact}


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def resolve_value(value, params=None, path="rule"):
    """Replace {"param": NAME} with the named constant's value."""
    if isinstance(value, dict):
        if set(value) != {"param"}:
            raise RuleError("%s: value object must be {param: NAME}" % path)
        name = value["param"]
        if not params or name not in params:
            raise RuleError("%s: unknown param '%s'" % (path, name))
        p = params[name]
        return p["value"] if isinstance(p, dict) else p
    return value


# ---------------------------------------------------------------- evaluation
def compare(op, actual, expected):
    """Apply one comparison. `actual` is never None here."""
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if not _is_num(actual):
        raise RuleError("numeric op '%s' on non-number %r" % (op, actual))
    if op == "<":
        return actual < expected
    if op == "<=":
        return actual <= expected
    if op == ">":
        return actual > expected
    if op == ">=":
        return actual >= expected
    if op == "between":
        return expected[0] <= actual <= expected[1]
    raise RuleError("unknown op '%s'" % op)


def tri_all(statuses):
    statuses = list(statuses)
    if FAIL in statuses:
        return FAIL
    if UNKNOWN in statuses:
        return UNKNOWN
    return PASS


def tri_any(statuses):
    statuses = list(statuses)
    if PASS in statuses:
        return PASS
    if UNKNOWN in statuses:
        return UNKNOWN
    return FAIL


def tri_not(status):
    return {PASS: FAIL, FAIL: PASS}.get(status, UNKNOWN)


def evaluate(rule, profile, params=None):
    """Evaluate `rule` over `profile`; returns a trace tree.

    Trace node: {"kind": "all"|"any"|"not"|"cond", "status": PASS|FAIL|UNKNOWN,
                 "children": [...]} or for leaves
                {"kind": "cond", "fact", "op", "value", "actual", "status", "label"?}
    """
    if "all" in rule or "any" in rule:
        kind = "all" if "all" in rule else "any"
        kids = [evaluate(k, profile, params) for k in rule[kind]]
        combine = tri_all if kind == "all" else tri_any
        node = {"kind": kind, "status": combine(k["status"] for k in kids), "children": kids}
    elif "not" in rule:
        kid = evaluate(rule["not"], profile, params)
        node = {"kind": "not", "status": tri_not(kid["status"]), "children": [kid]}
    else:
        fact, op = rule["fact"], rule["op"]
        expected = resolve_value(rule["value"], params)
        actual = profile.get(fact) if profile else None
        if actual is None:
            status = UNKNOWN
        else:
            status = PASS if compare(op, actual, expected) else FAIL
        node = {"kind": "cond", "fact": fact, "op": op, "value": expected,
                "actual": actual, "status": status}
    if "label" in rule:
        node["label"] = rule["label"]
    return node


def status_of(rule, profile, params=None):
    """Fast path: only the PASS/FAIL/UNKNOWN status (no trace)."""
    if "all" in rule:
        return tri_all(status_of(k, profile, params) for k in rule["all"])
    if "any" in rule:
        return tri_any(status_of(k, profile, params) for k in rule["any"])
    if "not" in rule:
        return tri_not(status_of(rule["not"], profile, params))
    actual = profile.get(rule["fact"])
    if actual is None:
        return UNKNOWN
    return PASS if compare(rule["op"], actual, resolve_value(rule["value"], params)) else FAIL


def facts_in(rule):
    """All facts referenced by a rule (ordered by first appearance)."""
    out = []

    def walk(r):
        if "all" in r or "any" in r:
            for k in r.get("all") or r.get("any"):
                walk(k)
        elif "not" in r:
            walk(r["not"])
        elif r["fact"] not in out:
            out.append(r["fact"])
    walk(rule)
    return out


def needed_facts(trace):
    """Facts whose answer could still change an UNKNOWN result (ordered, unique).

    A decided node (PASS/FAIL) needs nothing. Inside an UNKNOWN all/any, only
    UNKNOWN children matter - a FAIL child of an UNKNOWN 'any' cannot help, and an
    UNKNOWN 'all' has no FAIL children by construction.
    """
    out = []

    def walk(n):
        if n["status"] != UNKNOWN:
            return
        if n["kind"] == "cond":
            if n["fact"] not in out:
                out.append(n["fact"])
            return
        for k in n["children"]:
            walk(k)
    walk(trace)
    return out


def leaves(trace):
    """Flatten a trace into its leaf conditions (for compact explanations)."""
    if trace["kind"] == "cond":
        return [trace]
    out = []
    for k in trace["children"]:
        out.extend(leaves(k))
    return out


def prob_pass(rule, profile, priors, params=None):
    """P(rule == PASS) when unknown facts are drawn independently from `priors`.

    priors: fact -> list of (value, probability). Known facts are fixed. This is
    the analytic approximation used by the question selector (it assumes the
    sub-conditions are independent, which is exact when no fact repeats).
    """
    if "all" in rule:
        p = 1.0
        for k in rule["all"]:
            p *= prob_pass(k, profile, priors, params)
            if p == 0.0:
                break
        return p
    if "any" in rule:
        q = 1.0
        for k in rule["any"]:
            q *= 1.0 - prob_pass(k, profile, priors, params)
            if q == 0.0:
                break
        return 1.0 - q
    if "not" in rule:
        return 1.0 - prob_pass(rule["not"], profile, priors, params)
    fact = rule["fact"]
    expected = resolve_value(rule["value"], params)
    actual = profile.get(fact)
    if actual is not None:
        return 1.0 if compare(rule["op"], actual, expected) else 0.0
    dist = priors.get(fact) or []
    return sum(p for v, p in dist if compare(rule["op"], v, expected))
