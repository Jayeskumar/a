"""Job-description parser: must-have vs nice-to-have skills, experience, education, bias lint."""
import re
from collections import OrderedDict

from . import ontology
from .config import STRONG_CUE_WEIGHT, TITLE_SKILL_WEIGHT
from .extract import DEGREES, FIELDS, LEVEL_LABELS, header_key, match_skills_in_line, segment
from .text import clean

_JD_HEADERS = {
    "about": "about, about the role, about us, about the company, the role, overview, who we are, company, "
             "job summary, role overview, the opportunity",
    "resp": "responsibilities, key responsibilities, what you will do, what you'll do, what youll do, your role, "
            "role and responsibilities, roles and responsibilities, day to day, job description, duties",
    "must": "requirements, must have, must-have, must haves, required skills, required, qualifications, "
            "what you need, what we are looking for, what we're looking for, who you are, you have, "
            "skills required, mandatory skills, key skills, eligibility, requirements & skills, skills, "
            "technical skills, minimum qualifications, basic qualifications",
    "nice": "nice to have, nice-to-have, good to have, preferred, preferred skills, bonus, bonus points, plus, "
            "desirable, preferred qualifications, added advantage, nice to haves",
    "edu": "education, educational qualification, qualification, education & eligibility",
    "benefits": "benefits, perks, what we offer, compensation, why join us",
}
JD_HEADERS = {}
for _sec, _names in _JD_HEADERS.items():
    for _n in _names.split(","):
        JD_HEADERS[header_key(_n)] = _sec

_NICE_CUE = re.compile(r"nice to have|good to have|preferred|\bplus\b|\bbonus\b|\bexposure\b|familiar|"
                       r"desirable|advantage|optional|would be great|ideally", re.I)
_MUST_CUE = re.compile(r"\bmust\b|\brequired\b|\bmandatory\b|\bessential\b", re.I)
_STRONG_CUE = re.compile(r"\bstrong\b|\bexpert\b|\bdeep\b|\badvanced\b|\bproficien|\bsolid\b|\bexcellent\b", re.I)
_ALT_SEP = re.compile(r"^[\s(,]*(?:or|/|or any|and/or|or other)[\s),]*$", re.I)
_YEARS_RE = re.compile(r"(\d{1,2})(?:\.\d)?\s*(?:\+|plus)?\s*(?:(?:-|to)\s*(\d{1,2})\s*)?(?:years?|yrs?)", re.I)
_FRESHER_RE = re.compile(r"\bfreshers?\b|\bentry[- ]level\b|\bno experience required\b|\bgraduates? welcome\b", re.I)

# Bias lint: wording that filters on identity instead of skill. Masculine-coded wording
# follows the well-known Gaucher, Friesen & Kay (2011) word-list idea (small subset here).
BIAS_RULES = [
    ("College prestige", re.compile(r"\b(?:IIT|NIT|IIIT|IIM|BITS)s?\b|premier institut\w*|tier[- ]?1 (?:college|institut)\w*|"
                                    r"top[- ]tier (?:college|institut)\w*|top colleges|reputed (?:college|institut)\w*", re.I),
     "Prestige filters proxy for family income and geography, not skill. Blind mode masks college names."),
    ("Age limit", re.compile(r"\bage\s*(?:limit|below|under|less than|between|bar)?\s*[:\-]?\s*(?:of\s*)?\d{2}|"
                             r"\bbelow \d{2} years of age|\b\d{2}\s*-\s*\d{2} years of age|\byoung(?:er)? (?:and|candidates|team)", re.I),
     "Age filters exclude career-switchers and are discriminatory; ask for skills or experience instead."),
    ("Gendered wording", re.compile(r"\b(?:he|his|him)\b(?! or she)|\bmale candidates?\b|\bfemale candidates? only\b|"
                                    r"\bsalesman\b|\bmanpower\b|\brockstar\b|\bninja\b|\bguru\b|\baggressive\b|\bdominant\b", re.I),
     "Use neutral wording (they/you); masculine-coded words reduce applications from women."),
    ("Personal status", re.compile(r"\bunmarried\b|\bmarital\b|\bgood[- ]looking\b|\bfair complexion\b|\bpresentable\b|"
                                   r"\bnative (?:speaker|of)\b|\blocal candidates only\b", re.I),
     "Marital status, looks and origin are not job requirements."),
]


def bias_lint(text):
    flags = []
    for line in clean(text).split("\n"):
        for cat, rx, why in BIAS_RULES:
            m = rx.search(line)
            if m:
                flags.append({"category": cat, "match": m.group(0).strip(), "line": line.strip()[:160],
                              "suggestion": why})
    return flags


def _education_requirement(lines):
    text = " ".join(lines)
    level = None
    for lv, _label, rx in DEGREES:
        if lv >= 1 and rx.search(text):
            level = lv if level is None else min(level, lv)
    fields = []
    for name, rx in FIELDS:
        if rx.search(text) and name not in fields:
            fields.append(name)
    any_field = bool(re.search(r"any (?:discipline|degree|stream|field|branch)", text, re.I))
    related_ok = bool(re.search(r"related|equivalent|similar|allied", text, re.I))
    equivalent_ok = bool(re.search(r"or equivalent|equivalent (?:practical )?experience", text, re.I))
    if equivalent_ok:
        level = 0
    return {"level": level or 0, "label": LEVEL_LABELS.get(level or 0) if level else "Not required",
            "fields": fields, "any_field": any_field or not fields, "related_ok": related_ok,
            "equivalent_ok": equivalent_ok, "text": text[:240]}


def _groups_in_line(content):
    """Skill mentions in one line, merged into either-or groups ("Django or Flask")."""
    groups = []
    prev_end = None
    for targets, _surface, start, end in match_skills_in_line(content, "skills", lenient=True):
        if groups and prev_end is not None and _ALT_SEP.match(content[prev_end:start]):
            for sid in targets:
                if sid not in groups[-1]:
                    groups[-1].append(sid)
        else:
            groups.append(list(targets))
        prev_end = end
    return groups


def _resolve(mentions):
    """Merge raw mentions into requirements.

    Identical keys merge (must beats nice, max weight). A single skill that also appears in
    an either-or group is absorbed by the group, unless the single is a must and the group
    only nice - then the single wins and the group is dropped.
    """
    merged = OrderedDict()
    for m in mentions:
        key = tuple(sorted(m["skills"]))
        r = merged.get(key)
        if r is None:
            merged[key] = dict(m)
            continue
        if m["kind"] == "must":
            r["kind"] = "must"
            if r.get("_from_nice"):
                r["line"] = m["line"]
                r["_from_nice"] = False
        r["weight"] = max(r["weight"], m["weight"])
        r["core"] = r["core"] or m["core"]
    groups = [k for k in merged if len(k) > 1]
    for g in groups:
        if g not in merged:
            continue
        gr = merged[g]
        for sid in g:
            single = merged.get((sid,))
            if single is None:
                continue
            if single["kind"] == "must" and gr["kind"] == "nice":
                merged.pop(g, None)
                break
            if single["kind"] == "must":
                gr["kind"] = "must"
            gr["weight"] = max(gr["weight"], single["weight"])
            gr["core"] = gr["core"] or single["core"]
            merged.pop((sid,))
    return list(merged.values())


def parse_jd(text):
    text = clean(text)
    seg = segment(text, JD_HEADERS)
    lines = [(s, c) for s, c, h in seg if c and not h]
    title = lines[0][1] if lines else ""
    has_must_section = any(s == "must" for s, _ in lines)
    mentions = []
    soft = []
    edu_lines = []
    years = None
    years_text = ""
    fresher = False
    for idx, (sec, content) in enumerate(lines):
        if sec == "edu":
            edu_lines.append(content)
            continue
        if sec in ("about", "benefits") and idx != 0:
            continue
        if idx > 0 and sec != "resp" and any(rx.search(content) for lv, _l, rx in DEGREES if lv >= 2) and \
                re.search(r"degree|graduate|b\.?\s?e\b|b\.?\s?tech", content, re.I):
            edu_lines.append(content)
        if idx > 0 and not re.search(r"\bage\b|\bold\b", content, re.I):
            for m in _YEARS_RE.finditer(content):
                lo = int(m.group(1))
                if years is None or lo < years:
                    years, years_text = float(lo), content.strip()
        if _FRESHER_RE.search(content):
            fresher = True
        line_kind = "must"
        if idx == 0:
            line_kind = "title"
        elif _NICE_CUE.search(content) and not _MUST_CUE.search(content):
            line_kind = "nice"
        elif sec == "nice":
            line_kind = "nice"
        elif sec == "resp" and has_must_section:
            line_kind = "nice"
        strong = bool(_STRONG_CUE.search(content))
        for ids in _groups_in_line(content):
            for s in ids:
                if ontology.is_soft(s) and s not in soft:
                    soft.append(s)
            ids = [s for s in ids if not ontology.is_soft(s)]
            if not ids:
                continue
            kind = "nice" if line_kind == "nice" else "must"
            if line_kind == "title":
                weight = TITLE_SKILL_WEIGHT
            else:
                weight = STRONG_CUE_WEIGHT if (strong and kind == "must") else 1.0
            mentions.append({"skills": ids, "kind": kind, "weight": weight, "core": line_kind == "title",
                             "line": content[:160], "_from_nice": kind == "nice"})
    requirements = _resolve(mentions)
    for i, r in enumerate(requirements):
        r.pop("_from_nice", None)
        r["id"] = "r%d" % (i + 1)
        r["label"] = " / ".join(ontology.name_of(s) for s in r["skills"])
    must = [r for r in requirements if r["kind"] == "must"]
    nice = [r for r in requirements if r["kind"] == "nice"]
    if fresher and years is None:
        years, years_text = 0.0, "freshers welcome"
    return {
        "title": title[:120],
        "requirements": requirements,
        "must": must,
        "nice": nice,
        "soft": soft,
        "soft_names": [ontology.name_of(s) for s in soft],
        "min_years": years or 0.0,
        "years_text": years_text,
        "education": _education_requirement(edu_lines),
        "bias_flags": bias_lint(text),
        "skill_ids": sorted({s for r in requirements for s in r["skills"]}),
        "text": text,
    }


def public_jd(jd):
    out = {k: v for k, v in jd.items() if k not in ("text",)}
    out["requirements"] = [{k: v for k, v in r.items()} for r in jd["requirements"]]
    out["must"] = [r["id"] for r in jd["must"]]
    out["nice"] = [r["id"] for r in jd["nice"]]
    return out
