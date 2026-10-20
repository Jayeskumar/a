"""Load and validate the scheme catalogue and question bank; normalise profiles.

Pure data logic, no HTTP. Everything bilingual is a {"en": ..., "ta": ...} dict.
"""
import json
import os

from . import rules

LANGS = ("en", "ta")
REQUIRED_SCHEME_KEYS = ("id", "short", "name", "category", "summary", "description",
                        "benefit", "rule", "documents", "apply", "portal", "verify_note")
BENEFIT_KINDS = ("annual", "one_time", "cover", "future", "varies")
YES = {"en": "Yes", "ta": "ஆம்"}
NO = {"en": "No", "ta": "இல்லை"}


class CatalogueError(ValueError):
    pass


class ProfileError(ValueError):
    pass


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Catalogue(object):
    """Schemes + questions + documents, validated at load time."""

    def __init__(self, data_dir):
        sch = _load_json(os.path.join(data_dir, "schemes.json"))
        qs = _load_json(os.path.join(data_dir, "questions.json"))
        self.version = sch.get("version", "")
        self.params = sch.get("params", {})
        self.categories = sch.get("categories", {})
        self.documents = sch.get("documents", {})
        self.verify_note = sch.get("verify_note")
        self.questions = qs["questions"]
        self.q_by_id = {q["id"]: q for q in self.questions}
        self.atomic = [q for q in self.questions if "gate" not in q]   # the "full form"
        self.gates = [q for q in self.questions if "gate" in q]       # optional shortcuts
        self.inferences = qs.get("inferences", [])
        self.schemes = sch["schemes"]
        self.by_id = {}
        self._validate()

    # ------------------------------------------------------------ validation
    def _validate(self):
        if len(self.q_by_id) != len(self.questions):
            raise CatalogueError("duplicate question id")
        for q in self.questions:
            if q["type"] not in ("bool", "choice", "number"):
                raise CatalogueError("question %s: bad type" % q["id"])
            if q["type"] in ("choice", "number") and not q.get("options"):
                raise CatalogueError("question %s: needs options" % q["id"])
        facts = set(q["id"] for q in self.atomic)
        for g in self.gates:
            if g["type"] != "bool" or not g["gate"].get("sets"):
                raise CatalogueError("gate %s: must be bool with sets" % g["id"])
            for f, v in g["gate"]["sets"].items():
                if f not in facts:
                    raise CatalogueError("gate %s: unknown fact %s" % (g["id"], f))
                self.coerce(self.q_by_id[f], v)
        for inf in self.inferences:
            try:
                rules.validate(inf["if"], facts, self.params)
            except rules.RuleError as e:
                raise CatalogueError("inference: %s" % e)
            for f, v in inf["then"].items():
                if f not in facts:
                    raise CatalogueError("inference: unknown fact %s" % f)
        for s in self.schemes:
            for k in REQUIRED_SCHEME_KEYS:
                if k not in s:
                    if k == "verify_note" and self.verify_note:
                        s["verify_note"] = self.verify_note
                        continue
                    raise CatalogueError("scheme %s: missing %s" % (s.get("id"), k))
            if s["id"] in self.by_id:
                raise CatalogueError("duplicate scheme id %s" % s["id"])
            if s["category"] not in self.categories:
                raise CatalogueError("scheme %s: unknown category" % s["id"])
            try:
                rules.validate(s["rule"], facts, self.params)
                for t in s["benefit"].get("tiers", []):
                    rules.validate(t["when"], facts, self.params)
            except rules.RuleError as e:
                raise CatalogueError("scheme %s: %s" % (s["id"], e))
            if s["benefit"]["kind"] not in BENEFIT_KINDS:
                raise CatalogueError("scheme %s: bad benefit kind" % s["id"])
            for d in s["documents"]:
                if d not in self.documents:
                    raise CatalogueError("scheme %s: unknown document %s" % (s["id"], d))
            s["facts"] = rules.facts_in(s["rule"])
            self.by_id[s["id"]] = s

    # --------------------------------------------------------------- profile
    def normalise_profile(self, raw):
        """Coerce a client profile to typed facts. Unknown/blank answers are dropped.

        Raises ProfileError on unknown facts or values that cannot be parsed.
        """
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ProfileError("profile must be an object")
        out = {}
        for key, val in raw.items():
            q = self.q_by_id.get(key)
            if q is None:
                raise ProfileError("unknown field '%s'" % key)
            if val is None or val == "" or val == "unknown":
                continue
            out[key] = self.coerce(q, val)
        return out

    def coerce(self, q, val):
        t = q["type"]
        if t == "bool":
            if isinstance(val, bool):
                return val
            s = str(val).strip().lower()
            if s in ("yes", "true", "1", "y", "ஆம்"):
                return True
            if s in ("no", "false", "0", "n", "இல்லை"):
                return False
            raise ProfileError("'%s' must be yes/no" % q["id"])
        if t == "choice":
            allowed = [o["value"] for o in q["options"]]
            if val not in allowed:
                raise ProfileError("'%s' must be one of %s" % (q["id"], ", ".join(allowed)))
            return val
        # number
        if isinstance(val, bool):
            raise ProfileError("'%s' must be a number" % q["id"])
        try:
            num = float(val)
        except (TypeError, ValueError):
            raise ProfileError("'%s' must be a number" % q["id"])
        if num != num or num < 0 or num > 1e9:
            raise ProfileError("'%s' out of range" % q["id"])
        return int(num) if num == int(num) else num

    # ------------------------------------------------------------ inference
    def close(self, profile):
        """Apply gate shortcuts and logical inferences until nothing changes.

        Returns (closed_profile, inferred) where inferred maps each filled fact to
        the question id it was derived from. Explicit answers are never overwritten.
        """
        closed = dict(profile)
        inferred = {}
        for g in self.gates:
            v = profile.get(g["id"])
            if v is not None and v == g["gate"]["on"]:
                for f, val in g["gate"]["sets"].items():
                    if closed.get(f) is None:
                        closed[f] = val
                        inferred[f] = g["id"]
        changed = True
        while changed:
            changed = False
            for inf in self.inferences:
                if rules.status_of(inf["if"], closed, self.params) != rules.PASS:
                    continue
                for f, val in inf["then"].items():
                    if closed.get(f) is None:
                        closed[f] = val
                        inferred[f] = inf["if"]["fact"]
                        changed = True
        return closed, inferred

    def gate_value(self, gate, truth):
        """What a gate question's honest answer is for a complete profile."""
        g = gate["gate"]
        match = all(truth.get(f) == v for f, v in g["sets"].items())
        return g["on"] if match else (not g["on"])

    def truth_answer(self, qid, truth):
        q = self.q_by_id[qid]
        if "gate" in q:
            return self.gate_value(q, truth)
        return truth.get(qid)

    def bucket(self, qid, value):
        """Map a value to its preset option (the band whose upper bound covers it)."""
        q = self.q_by_id[qid]
        if q["type"] == "bool":
            return value
        if q["type"] == "choice":
            return value
        opts = sorted(o["value"] for o in q["options"])
        for v in opts:
            if value <= v:
                return v
        return opts[-1]

    # ----------------------------------------------------------- explanation
    def answer_label(self, qid, value):
        q = self.q_by_id.get(qid)
        if value is None:
            return {"en": "Not answered", "ta": "பதில் இல்லை"}
        if q is None:
            return {"en": str(value), "ta": str(value)}
        if q["type"] == "bool":
            return dict(YES) if value else dict(NO)
        for o in q.get("options", []):
            if o["value"] == value:
                return o["label"]
        return {"en": fmt_value(value, q.get("unit"), "en"), "ta": fmt_value(value, q.get("unit"), "ta")}

    def condition_text(self, leaf):
        """Bilingual description of what a leaf condition requires."""
        if leaf.get("label"):
            return leaf["label"]
        q = self.q_by_id[leaf["fact"]]
        out = {}
        for lang in LANGS:
            short = q["short"][lang]
            op, val, unit = leaf["op"], leaf["value"], q.get("unit")
            if q["type"] == "bool" and op in ("==", "!="):
                want = val if op == "==" else (not val)
                if want:
                    out[lang] = short
                elif q.get("short_no"):
                    out[lang] = q["short_no"][lang]
                else:
                    out[lang] = "%s: %s" % (short, NO[lang])
            elif op in ("in", "not_in"):
                labels = [self.answer_label(q["id"], v)[lang] for v in val]
                prefix = "" if op == "in" else ("not " if lang == "en" else "அல்ல: ")
                out[lang] = "%s: %s%s" % (short, prefix, " / ".join(labels))
            elif op == "between":
                out[lang] = "%s: %s – %s" % (short, fmt_value(val[0], unit, lang), fmt_value(val[1], unit, lang))
            else:
                sym = {"==": "=", "!=": "≠", "<": "<", "<=": "≤", ">": ">", ">=": "≥"}[op]
                out[lang] = "%s %s %s" % (short, sym, fmt_value(val, unit, lang))
        return out

    def explain(self, trace, inferred=None):
        """Decorate a rule trace with bilingual text for every node (a copy)."""
        node = {"kind": trace["kind"], "status": trace["status"]}
        if trace["kind"] == "cond":
            node["fact"] = trace["fact"]
            node["text"] = self.condition_text(trace)
            node["answer"] = self.answer_label(trace["fact"], trace["actual"])
            if inferred and trace["fact"] in inferred:
                node["inferred_from"] = inferred[trace["fact"]]
        else:
            node["text"] = {
                "all": {"en": "All of these", "ta": "இவை அனைத்தும்"},
                "any": {"en": "Any one of these", "ta": "இவற்றில் ஏதேனும் ஒன்று"},
                "not": {"en": "None of this", "ta": "இது இருக்கக் கூடாது"},
            }[trace["kind"]]
            if trace.get("label"):
                node["text"] = trace["label"]
            node["children"] = [self.explain(k, inferred) for k in trace["children"]]
        return node

    def public_scheme(self, s):
        """Scheme record as served by the API (no internal fields)."""
        keep = ("id", "short", "level", "category", "name", "summary", "description", "benefit",
                "documents", "apply", "portal", "caveats", "verify_note", "exclusive_group",
                "conditional")
        out = {k: s[k] for k in keep if k in s}
        out["facts"] = list(s["facts"])
        out["rule"] = s["rule"]
        return out


def fmt_inr(n):
    """Indian digit grouping: 250000 -> '2,50,000'."""
    n = int(round(n))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + s


def fmt_value(v, unit, lang="en"):
    if unit == "inr":
        return "₹" + fmt_inr(v)
    if unit == "ha":
        return "%s %s" % (_num(v), "ha" if lang == "en" else "ஹெக்டேர்")
    if unit == "years":
        return "%s %s" % (_num(v), "yrs" if lang == "en" else "வயது")
    return _num(v)


def _num(v):
    return str(int(v)) if float(v) == int(v) else ("%g" % v)
