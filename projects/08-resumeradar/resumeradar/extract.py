"""Plain-text resume parser: sections, skills, experience, education, projects, certs.

Everything is rule-based and explainable: each extracted fact keeps the line it came from.
"""
import re
from collections import OrderedDict

from . import ontology
from .config import AS_OF_MONTH, AS_OF_YEAR, INTERNSHIP_WEIGHT
from .text import BULLET_RE, EMAIL_RE, TOKEN_RE, URL_RE, _norm_token, clean, word_count

# --------------------------------------------------------------------------- sections
_HEADERS = {
    "summary": "summary, professional summary, profile, profile summary, professional profile, "
               "objective, career objective, about, about me, career summary, overview",
    "experience": "experience, work experience, professional experience, employment, employment history, "
                  "work history, internship, internships, internship experience, experience & internships, "
                  "experience and internships, relevant experience, industrial experience, work",
    "projects": "projects, academic projects, personal projects, key projects, project work, selected projects, "
                "project experience, side projects, project",
    "skills": "skills, technical skills, key skills, skill set, skillset, core competencies, competencies, "
              "technologies, tech stack, tools & technologies, tools and technologies, technical proficiency, "
              "skills & tools, skills and tools, programming languages, it skills, computer skills, technical expertise",
    "education": "education, academic background, academics, qualifications, educational qualification, "
                 "educational qualifications, academic qualifications, education & training, education and training",
    "certifications": "certifications, certification, certificates, courses, licenses & certifications, "
                      "licenses and certifications, certifications & courses, certifications and courses, "
                      "training, trainings, online courses",
    "achievements": "achievements, awards, accomplishments, honors, honours, awards & achievements, "
                    "awards and achievements, extracurricular, extra curricular activities, "
                    "extracurricular activities, activities, positions of responsibility, publications",
    "personal": "personal details, personal information, personal profile, personal data, declaration, "
                "languages, languages known, hobbies, interests, hobbies & interests, hobbies and interests, strengths",
    "contact": "contact, contact information, contact details",
}
HEADERS = {}
for _sec, _names in _HEADERS.items():
    for _n in _names.split(","):
        HEADERS[_n.strip()] = _sec

SECTION_NAMES = ["header", "summary", "experience", "projects", "skills", "education",
                 "certifications", "achievements", "personal", "contact"]
EVIDENCE_SECTIONS = frozenset(["experience", "projects", "certifications", "achievements"])

_INLINE_HDR = re.compile(r"^([A-Za-z][A-Za-z &/']{1,38}?)\s*(?::|\|)\s*(\S.*)$")


def header_key(s):
    s = s.strip().strip(":-=#*|_ ").lower()
    s = re.sub(r"[^a-z&/ ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def segment(text, header_map=None):
    """Return [(section, content, is_header)] for each line of cleaned text."""
    hmap = header_map or HEADERS
    out = []
    cur = "header"
    for ln in text.split("\n"):
        st = ln.strip()
        if not st:
            out.append((cur, "", False))
            continue
        if len(st) <= 45 and not BULLET_RE.match(st):
            k = header_key(st)
            if k in hmap:
                cur = hmap[k]
                out.append((cur, "", True))
                continue
        m = _INLINE_HDR.match(st)
        if m and not BULLET_RE.match(st):
            k = header_key(m.group(1))
            if k in hmap:
                sec = hmap[k]
                if not (cur == "skills" and sec in ("personal", "contact")):
                    cur = sec
                out.append((cur, m.group(2).strip(), False))
                continue
        out.append((cur, st, False))
    return out


# --------------------------------------------------------------------------- skills
def _blank(m):
    return " " * len(m.group(0))


def match_skills_in_line(line, section, lenient=False):
    """Longest-match alias lookup over one line.

    Returns [(skill_ids, surface, start_char, end_char)]. lenient=True (Skills section or
    a JD) lets ambiguous words such as "react" or "excel" match in any case.
    """
    line = URL_RE.sub(_blank, EMAIL_RE.sub(_blank, line))
    spans = []
    for m in TOKEN_RE.finditer(line):
        t = _norm_token(m.group(0))
        if t:
            spans.append((t, m.start(), m.start() + len(t)))
    toks = [t for t, _, _ in spans]
    low = [t.lower() for t in toks]
    found = []
    i, n = 0, len(toks)
    allow_amb = lenient or section == "skills"
    while i < n:
        maxlen = ontology.FIRST_TOKEN_MAXLEN.get(low[i], 0)
        hit = None
        for L in range(min(maxlen, n - i), 0, -1):
            entries = ontology.ALIAS_INDEX.get(tuple(low[i:i + L]))
            if not entries:
                continue
            orig = tuple(toks[i:i + L])
            for targets, mode, surface in entries:
                if mode == "any" or (mode == "amb" and allow_amb) or orig == surface:
                    hit = (targets, line[spans[i][1]:spans[i + L - 1][2]], spans[i][1], spans[i + L - 1][2], L)
                    break
            if hit:
                break
        if hit:
            found.append(hit[:4])
            i += hit[4]
        else:
            i += 1
    return found


def extract_skills(seg_lines, lenient=False):
    """{skill_id: info} plus per-line skill ids (same order as seg_lines)."""
    skills = OrderedDict()
    per_line = []
    for idx, (sec, content, is_hdr) in enumerate(seg_lines):
        ids = []
        if content and not is_hdr:
            for targets, surface, _s, _e in match_skills_in_line(content, sec, lenient):
                for sid in targets:
                    ids.append(sid)
                    info = skills.get(sid)
                    if info is None:
                        sk = ontology.get(sid)
                        info = skills[sid] = {"id": sid, "name": sk.name, "category": sk.category,
                                              "count": 0, "sections": [], "surfaces": [], "contexts": []}
                    info["count"] += 1
                    if sec not in info["sections"]:
                        info["sections"].append(sec)
                    if surface not in info["surfaces"]:
                        info["surfaces"].append(surface)
                    if len(info["contexts"]) < 2 and sec in EVIDENCE_SECTIONS:
                        info["contexts"].append(content[:160])
        per_line.append(ids)
    for info in skills.values():
        info["evidence"] = any(s in EVIDENCE_SECTIONS for s in info["sections"])
    return skills, per_line


# --------------------------------------------------------------------------- dates / experience
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
           "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_DATE_TOKEN = re.compile(
    r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec)[a-z]*\.?\s*[',]?\s*(?P<y1>(?:19|20)\d{2})"
    r"|(?P<mm>\d{1,2})\s*[/.-]\s*(?P<y2>(?:19|20)\d{2})"
    r"|(?P<y3>(?:19|20)\d{2})"
    r"|(?P<now>present|current|now|ongoing|till date|to date|today)", re.I)
_RANGE_SEP = re.compile(r"^\s*(?:-|to|till|until|through)\s*$", re.I)
_CLAIM_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+[\w/&-]+){0,3}?\s+(?:experience|exp)\b"
    r"|(?:experience|exp)\s+of\s+(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)"
    r"|\((\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\)", re.I)
_MONTHS_RE = re.compile(r"\b(\d{1,2})\s*(?:\+\s*)?months?\b", re.I)
AS_OF_INDEX = AS_OF_YEAR * 12 + (AS_OF_MONTH - 1)


def _date_index(m):
    if m.group("now"):
        return AS_OF_INDEX, True
    if m.group("mon"):
        return int(m.group("y1")) * 12 + _MONTHS[m.group("mon").lower()[:3]] - 1, True
    if m.group("mm"):
        mm = int(m.group("mm"))
        if 1 <= mm <= 12:
            return int(m.group("y2")) * 12 + mm - 1, True
        return None, False
    y = int(m.group("y3"))
    return y * 12 + 5, False  # year-only: assume mid-year


def find_date_ranges(line):
    """[(start_idx, end_idx, months, text)] for every "<date> - <date>" in a line."""
    ms = list(_DATE_TOKEN.finditer(line))
    out = []
    i = 0
    while i < len(ms) - 1:
        a, b = ms[i], ms[i + 1]
        if _RANGE_SEP.match(line[a.end():b.start()]) and not a.group("now"):
            s, _ = _date_index(a)
            e, _ = _date_index(b)
            if s is not None and e is not None and e >= s:
                e = min(e, AS_OF_INDEX)
                out.append((s, e, max(0, e - s + 1), line[a.start():b.end()]))
                i += 2
                continue
        i += 1
    return out


def _union_months(intervals):
    if not intervals:
        return 0
    iv = sorted(intervals)
    total = 0
    cs, ce = iv[0]
    for s, e in iv[1:]:
        if s <= ce + 1:
            ce = max(ce, e)
        else:
            total += ce - cs + 1
            cs, ce = s, e
    return total + ce - cs + 1


def parse_experience(seg, per_line):
    entries = []
    cur = None
    prev_plain = None
    for idx, (sec, content, is_hdr) in enumerate(seg):
        if sec != "experience" or is_hdr or not content:
            continue
        is_bullet = bool(BULLET_RE.match(content))
        ranges = [] if is_bullet else find_date_ranges(content)
        months_only = None
        if not ranges and not is_bullet:
            mm = _MONTHS_RE.search(content)
            if mm:
                months_only = int(mm.group(1))
        if ranges or months_only:
            title = content
            for r in ranges:
                title = title.replace(r[3], " ")
            title = re.sub(r"[\s|,()\-]+$", "", re.sub(r"\s{2,}", " ", title)).strip(" -|,")
            if not title and prev_plain is not None:
                title = seg[prev_plain][1]
            low = (title + " " + (seg[prev_plain][1] if prev_plain is not None else "")).lower()
            cur = {"title": title[:140], "line": idx, "lines": [idx],
                   "intern": bool(re.search(r"\bintern(ship)?\b|\btrainee\b", low)),
                   "start": ranges[0][0] if ranges else None,
                   "end": ranges[0][1] if ranges else None,
                   "months": ranges[0][2] if ranges else months_only,
                   "dated": bool(ranges), "skills": set(per_line[idx])}
            if prev_plain is not None and prev_plain == idx - 1:
                cur["lines"].append(prev_plain)
                cur["skills"].update(per_line[prev_plain])
            entries.append(cur)
            prev_plain = None
        elif is_bullet or (cur is not None and len(content.split()) >= 6):
            if cur is None:
                cur = {"title": "(untitled role)", "line": idx, "lines": [], "intern": False, "start": None,
                       "end": None, "months": 0, "dated": False, "skills": set()}
                entries.append(cur)
            cur["lines"].append(idx)
            cur["skills"].update(per_line[idx])
        else:
            prev_plain = idx
    return entries


def summarize_experience(entries, claims, relevant_filter=None):
    ft, it = [], []
    undated_ft = undated_it = 0
    for e in entries:
        if relevant_filter is not None and not relevant_filter(e):
            continue
        if e["dated"]:
            (it if e["intern"] else ft).append((e["start"], e["end"]))
        elif e["months"]:
            if e["intern"]:
                undated_it += e["months"]
            else:
                undated_ft += e["months"]
    ft_m = _union_months(ft) + undated_ft
    it_m = _union_months(it) + undated_it
    years = (ft_m + INTERNSHIP_WEIGHT * it_m) / 12.0
    source = "computed from dated roles" if (ft or it) else ("stated durations" if (undated_ft or undated_it) else "")
    if not entries and claims:
        years = max(claims)
        source = "stated in resume (no dated roles)"
    return {"years": round(years, 2), "fulltime_months": ft_m, "intern_months": it_m, "source": source or "none found"}


# --------------------------------------------------------------------------- education
DEGREES = [
    (4, "PhD", re.compile(r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctor of philosophy\b", re.I)),
    (3, "M.Tech", re.compile(r"\bm\.?\s?tech\b", re.I)),
    (3, "M.E.", re.compile(r"\bM\.\s?E\b\.?|\bME\b(?=[\s,(])")),
    (3, "M.Sc", re.compile(r"\bm\.?\s?sc\b", re.I)),
    (3, "MCA", re.compile(r"\bmca\b", re.I)),
    (3, "MBA", re.compile(r"\bmba\b|\bpgdm\b", re.I)),
    (3, "M.S.", re.compile(r"\bM\.S\.?(?=[\s,(])|\bMS\b(?= in\b)")),
    (3, "Master's", re.compile(r"\bmasters?\b|\bmaster's\b|\bpost[- ]?graduat", re.I)),
    (2, "B.Tech", re.compile(r"\bb\.?\s?tech\b", re.I)),
    (2, "B.E.", re.compile(r"\bB\.\s?E\b\.?|\bBE\b(?=[\s,(])")),
    (2, "B.Sc", re.compile(r"\bb\.?\s?sc\b", re.I)),
    (2, "BCA", re.compile(r"\bbca\b", re.I)),
    (2, "B.Com", re.compile(r"\bb\.?\s?com\b", re.I)),
    (2, "BBA", re.compile(r"\bbba\b", re.I)),
    (2, "B.A.", re.compile(r"\bB\.A\.?(?=[\s,(])|\bBA\b(?= in\b)")),
    (2, "B.S.", re.compile(r"\bB\.S\.?(?=[\s,(])|\bBS\b(?= in\b)")),
    (2, "Bachelor's", re.compile(r"\bbachelors?\b|\bbachelor's\b|\bundergraduate\b|\bgraduat(?:e|ion) degree\b", re.I)),
    (1, "Diploma", re.compile(r"\bdiploma\b|\bpolytechnic\b", re.I)),
    (0, "Higher secondary", re.compile(r"\bhsc\b|\b12th\b|\bclass xii\b|\bhigher secondary\b|\bsslc\b|\b10th\b", re.I)),
]
LEVEL_LABELS = {0: "School", 1: "Diploma", 2: "Bachelor's", 3: "Master's", 4: "PhD"}

FIELDS = [
    ("Computer Science", re.compile(r"computer science|\bcse\b|computer engineering|computer applications|\bbca\b|\bmca\b|software engineering", re.I)),
    ("Information Technology", re.compile(r"information technology|\bIT\b")),
    ("Data Science / AI", re.compile(r"data science|artificial intelligence|machine learning|\bai\s*(?:&|and)\s*ds\b", re.I)),
    ("Electronics / Electrical", re.compile(r"electronics|\bece\b|\beee\b|electrical|communication engineering", re.I)),
    ("Statistics / Mathematics", re.compile(r"statistics|mathematics|\bmaths?\b|applied math", re.I)),
    ("Mechanical", re.compile(r"mechanical|\bmech\b", re.I)),
    ("Civil", re.compile(r"\bcivil\b", re.I)),
    ("Commerce / Business", re.compile(r"commerce|\bb\.?\s?com\b|business administration|\bbba\b|\bmba\b|economics|finance", re.I)),
]
TECH_FIELDS = frozenset(["Computer Science", "Information Technology", "Data Science / AI",
                         "Electronics / Electrical", "Statistics / Mathematics"])

_CGPA_RE = re.compile(r"(?:cgpa|gpa|cpi)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)(?:\s*/\s*(10|4))?"
                      r"|(\d(?:\.\d{1,2})?)\s*/\s*10\b|(\d(?:\.\d{1,2})?)\s*cgpa", re.I)
_PCT_RE = re.compile(r"(\d{2}(?:\.\d{1,2})?)\s*%")
_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def detect_degree(line):
    for level, label, rx in DEGREES:
        if rx.search(line):
            return level, label
    return None


def detect_field(line):
    for name, rx in FIELDS:
        if rx.search(line):
            return name
    if re.search(r"engineering", line, re.I):
        return "Other Engineering"
    return None


def parse_education(seg):
    lines = [(i, c) for i, (s, c, h) in enumerate(seg) if s == "education" and c and not h]
    if not lines:
        lines = [(i, c) for i, (s, c, h) in enumerate(seg) if c and not h and s in ("header", "summary")
                 and detect_degree(c)]
    entries = []
    for i, c in lines:
        d = detect_degree(c)
        if not d:
            if entries and not entries[-1].get("field"):
                entries[-1]["field"] = detect_field(c)
            continue
        level, label = d
        cg = _CGPA_RE.search(c)
        score = None
        if cg:
            val = cg.group(1) or cg.group(3) or cg.group(4)
            try:
                v = float(val)
                if cg.group(2) == "4":
                    v = v * 2.5
                if 0 < v <= 10:
                    score = "CGPA %.1f/10" % v
            except (TypeError, ValueError):
                pass
        if score is None:
            pm = _PCT_RE.search(c)
            if pm:
                score = "%s%%" % pm.group(1)
        years = [int(y) for y in _YEAR_RE.findall(c)]
        entries.append({"level": level, "degree": label, "field": detect_field(c), "score": score,
                        "year": max(years) if years else None,
                        "expected": bool(re.search(r"expected|pursuing|ongoing|final[- ]year", c, re.I)),
                        "line": c[:160]})
    best = max(entries, key=lambda e: e["level"]) if entries else None
    return {"entries": entries,
            "level": best["level"] if best else None,
            "level_label": LEVEL_LABELS.get(best["level"]) if best else "Not found",
            "degree": best["degree"] if best else None,
            "field": best["field"] if best else None}


# --------------------------------------------------------------------------- projects / certs / contact
def parse_projects(seg, per_line):
    projects = []
    cur = None
    for idx, (sec, content, is_hdr) in enumerate(seg):
        if sec != "projects" or is_hdr or not content:
            continue
        if BULLET_RE.match(content):
            if cur is None:
                cur = {"title": BULLET_RE.sub("", content)[:80], "skills": set(), "bullets": []}
                projects.append(cur)
            cur["bullets"].append(BULLET_RE.sub("", content))
            cur["skills"].update(per_line[idx])
        else:
            title = re.split(r"\s[-|(]\s?|\(", content)[0].strip() or content[:60]
            cur = {"title": title[:80], "skills": set(per_line[idx]), "bullets": []}
            projects.append(cur)
    for p in projects:
        p["skills"] = sorted(p["skills"])
    return projects


_CERT_HINT = re.compile(r"\bcertifi(?:ed|cate|cation)\b|\bnptel\b|\bcoursera\b|\budemy\b|\bedx\b", re.I)


def parse_certifications(seg):
    certs = []
    for sec, content, is_hdr in seg:
        if is_hdr or not content:
            continue
        if sec == "certifications" or (_CERT_HINT.search(content) and sec not in ("education", "personal")):
            c = BULLET_RE.sub("", content).strip()
            if c and c not in certs and len(c) < 200:
                certs.append(c)
    return certs[:12]


_PHONE_RE = re.compile(r"(?:\+91[\s-]?|\b0)?\b[6-9]\d{4}[\s-]?\d{5}\b|\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}")


def parse_contact(text):
    return {
        "email": bool(EMAIL_RE.search(text)),
        "phone": bool(_PHONE_RE.search(text)),
        "linkedin": bool(re.search(r"linkedin\.com/", text, re.I)),
        "github": bool(re.search(r"github\.com/|gitlab\.com/", text, re.I)),
        "portfolio": bool(re.search(r"\b[\w-]+\.(?:dev|me|io|github\.io)\b|https?://", text, re.I)),
    }


def collect_bullets(seg):
    """Achievement-style lines from experience/projects (explicit bullets, else long sentences)."""
    out = []
    for sec in ("experience", "projects", "achievements"):
        rows = [(i, c) for i, (s, c, h) in enumerate(seg) if s == sec and c and not h]
        has_markers = any(BULLET_RE.match(c) for _, c in rows)
        for i, c in rows:
            if BULLET_RE.match(c):
                out.append({"line": i, "section": sec, "text": BULLET_RE.sub("", c).strip()})
            elif not has_markers and len(c.split()) >= 6 and not find_date_ranges(c) and not _MONTHS_RE.search(c):
                out.append({"line": i, "section": sec, "text": c.strip()})
    return out


# --------------------------------------------------------------------------- main entry
def parse_resume(text):
    text = clean(text)
    seg = segment(text)
    skills, per_line = extract_skills(seg)
    entries = parse_experience(seg, per_line)
    claims = []
    for sec, content, is_hdr in seg:
        if content and sec in ("header", "summary", "experience"):
            for m in _CLAIM_RE.finditer(content):
                v = m.group(1) or m.group(2) or m.group(3)
                if v and not re.search(r"\bold\b|\bage\b", content[m.end():m.end() + 6], re.I):
                    claims.append(float(v))
    exp = summarize_experience(entries, claims)
    exp["claimed_years"] = max(claims) if claims else None
    exp["entries"] = [dict(e, skills=sorted(e["skills"])) for e in entries]
    sections = OrderedDict()
    for sec, content, is_hdr in seg:
        if is_hdr or content:
            sections[sec] = sections.get(sec, 0) + (0 if is_hdr else 1)
    return {
        "text": text,
        "seg": seg,
        "per_line": per_line,
        "skills": skills,
        "experience": exp,
        "education": parse_education(seg),
        "projects": parse_projects(seg, per_line),
        "certifications": parse_certifications(seg),
        "contact": parse_contact(text),
        "bullets": collect_bullets(seg),
        "sections": sections,
        "headers_found": sorted({s for s, c, h in seg if h}),
        "word_count": word_count(text),
        "claims": claims,
    }


def public_profile(p):
    """JSON-friendly summary of a parsed resume (drops internal line tables)."""
    by_cat = OrderedDict()
    for info in sorted(p["skills"].values(), key=lambda x: (x["category"], x["name"])):
        by_cat.setdefault(info["category"], []).append(info["name"])
    return {
        "skills": [dict(v) for v in p["skills"].values()],
        "skills_by_category": by_cat,
        "skill_count": len(p["skills"]),
        "experience": {k: v for k, v in p["experience"].items() if k != "entries"},
        "roles": [{"title": e["title"], "months": e["months"], "intern": e["intern"], "dated": e["dated"],
                   "skills": [ontology.name_of(s) for s in e["skills"]]} for e in p["experience"]["entries"]],
        "education": p["education"],
        "projects": [{"title": x["title"], "skills": [ontology.name_of(s) for s in x["skills"]],
                      "bullets": len(x["bullets"])} for x in p["projects"]],
        "certifications": p["certifications"],
        "contact": p["contact"],
        "sections": list(p["sections"].keys()),
        "word_count": p["word_count"],
    }
