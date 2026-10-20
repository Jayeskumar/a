"""Blind mode: find identity fields and mask, strip or swap them.

Identity fields never carry job skill: name, contact details, gendered words, age / date
of birth, photo, marital status, family names, religion, nationality, address/city,
college names and graduation years (an age proxy). Scoring in blind mode only ever sees
the masked text, so identity cannot leak into the score.

The same span finder powers the bias check: `strip()` deletes the fields and
`counterfactual()` swaps them (female <-> male names and pronouns, IIT <-> government
college, age +6 ...). A fair pipeline must give identical scores for all three.
"""
import re
import zlib

from . import ontology
from .extract import segment
from .text import EMAIL_RE, STOPWORDS, clean

PLACEHOLDER = {
    "name": "[CANDIDATE]", "contact": "[CONTACT]", "gender": "[GENDER]", "age": "[AGE]",
    "photo": "[PHOTO REMOVED]", "institution": "[INSTITUTION]", "location": "[LOCATION]",
    "family": "[REDACTED]", "marital": "[REDACTED]", "religion": "[REDACTED]",
    "nationality": "[REDACTED]", "personal": "[REDACTED]", "grad_year": "[YEAR]", "title": "",
}
KIND_LABELS = {
    "name": "Name", "contact": "Contact details", "pronoun": "Gendered pronouns", "title": "Titles (Mr/Ms)",
    "gender": "Gender words", "age": "Age / date of birth", "photo": "Photo", "institution": "College names",
    "location": "City / address", "family": "Family names", "marital": "Marital status",
    "religion": "Religion / caste", "nationality": "Nationality", "personal": "Other personal data",
    "grad_year": "Graduation years",
}

_KEYS = [
    ("family", r"father'?s? name|mother'?s? name|husband'?s? name|spouse(?:'s)? name|guardian(?:'s)? name|s/o|d/o|w/o"),
    ("age", r"date of birth|d\.o\.b\.?|dob|birth ?date|born on|age"),
    ("gender", r"gender|sex"),
    ("marital", r"marital status|martial status|marital"),
    ("religion", r"religion|caste|community"),
    ("nationality", r"nationality|citizenship"),
    ("location", r"permanent address|current address|address|location|hometown|native place|place"),
    ("photo", r"photo(?:graph)?|picture"),
    ("personal", r"blood group|height|weight|passport(?: no\.?| number)?|aadhaar(?: no\.?)?|pan(?: no\.?)?"),
    ("name", r"full name|name"),
]
_KV_RE = re.compile(r"(?im)(?:^|(?<=[\s,;|(]))(?P<key>" + "|".join(k for _, k in _KEYS) +
                    r")[ \t]*[:\-][ \t]*(?P<val>[^,;|\n]*)")
_KEY_KIND = [(kind, re.compile(r"^(?:%s)$" % rx, re.I)) for kind, rx in _KEYS]

_PHOTO_LINE = re.compile(r"(?im)^.*(?:\[(?:image|photo|picture)[^\]]*\]|\S+\.(?:jpe?g|png|gif)\b|"
                         r"\bpassport[- ]size photo\b|\bprofile picture\b|\bheadshot\b).*$")
_PHONE_RE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b|\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}")
_URL_RE = re.compile(r"(?:https?://\S+|www\.\S+|\b(?:linkedin|github|gitlab|behance|dribbble)\.com/\S+|"
                     r"\b[\w-]+\.(?:dev|me|github\.io)\b(?:/\S*)?)", re.I)
_PRONOUN_RE = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.I)
_TITLE_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Shri|Smt|Kumari|Selvi|Thiru)\b\.?\s+")
_GENDER_RE = re.compile(r"\b(?:male|female|man(?!-?hours?)|woman|women|men|boys?|girls?|lady|ladies|gentleman|"
                        r"transgender)\b(?:'s)?", re.I)
_AGE_INLINE = re.compile(r"\b\d{2}\s*(?:years|yrs)\s*old\b|\baged?\s+(?:below|under|less than|between|limit|of\s)?\s*"
                         r"\d{2}(?:\s*(?:-|to)\s*\d{2})?(?:\s*(?:years|yrs))?\b|\bbelow \d{2} years of age\b", re.I)

_CAP = r"(?:[A-Z][A-Za-z.&'-]*|[A-Z]\.)"
_SKIP_PREFIX = (r"(?!(?:B\.?E|B\.?Tech|M\.?Tech|M\.?E|B\.?Sc|M\.?Sc|BCA|MCA|MBA|BBA|B\.?Com|Bachelor|Master|Diploma|"
                r"Computer|Science|Engineering|Information|Technology|Electronics|Mechanical|Civil|Electrical|"
                r"Statistics|Mathematics|Commerce|Data|CGPA|GPA|Intern|Research)\b)")
_INST_WORD = r"(?:College|University|Institute|Polytechnic|School|Academy|Vidyalaya|Vidyapeeth|Vidyapith)"
_INST_RE = re.compile(
    r"(?:\b(?:" + _SKIP_PREFIX + _CAP + r"\s+){0,6}" + _INST_WORD +
    r"(?:\s+(?:of|for|and|&)(?:\s+(?:" + _CAP + r"|and|&|for))+)*)"
    r"|\b(?:IIT|NIT|IIIT|IIM|BITS|IISc|VIT|SRM)\b(?:[\s-]+(?:" + _CAP + r"))?")
_TOP_INST = re.compile(r"\b(?:IIT|NIT|IIIT|IIM|BITS|IISc)\b|Indian Institute|National Institute", re.I)

CITIES = ["Chennai", "Coimbatore", "Bengaluru", "Bangalore", "Hyderabad", "Salem", "Madurai", "Tiruchengode",
          "Erode", "Pune", "Kochi", "Mumbai", "Delhi", "New Delhi", "Kolkata", "Trichy", "Tiruchirappalli",
          "Tirunelveli", "Vellore", "Namakkal", "Karur", "Thanjavur", "Mysuru", "Mysore", "Mangaluru",
          "Visakhapatnam", "Vijayawada", "Ahmedabad", "Jaipur", "Lucknow", "Patna", "Bhopal", "Indore",
          "Nagpur", "Noida", "Gurugram", "Gurgaon", "Chandigarh", "Thiruvananthapuram", "Kozhikode",
          "Puducherry", "Pondicherry", "Hosur", "Tiruppur", "Bhubaneswar", "Guwahati", "Ranchi", "Madras",
          "Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana", "Maharashtra", "Bihar",
          "Uttar Pradesh", "West Bengal", "Pilani", "Bombay"]
_CITY_RE = re.compile(r"\b(?:" + "|".join(re.escape(c) for c in sorted(CITIES, key=len, reverse=True)) + r")\b")

_NAME_LINE = re.compile(r"^\s*([A-Z][A-Za-z'-]*\.?(?:\s+[A-Z][A-Za-z'-]*\.?){1,3})\s*$")
_NOT_NAME_WORDS = frozenset("""developer engineer analyst resume curriculum vitae cv manager intern student designer
consultant scientist executive officer data software backend frontend full stack staff senior junior lead web ui ux
summary profile objective skills experience education projects contact career machine learning site associate
final year graduate fresher professional technical""".split())

FEMALE_NAMES = ["Priya", "Divya", "Lakshmi", "Ananya", "Kavya", "Meera", "Sneha", "Fathima", "Harini", "Nandhini",
                "Aishwarya", "Swathi", "Pooja", "Sowmya", "Ritika", "Janani", "Keerthana", "Ayesha", "Deepa", "Shruti"]
MALE_NAMES = ["Arun", "Karthik", "Rahul", "Vignesh", "Mohammed", "Sanjay", "Pranav", "Harish", "Aditya", "Surya",
              "Rohit", "Gokul", "Naveen", "Ajay", "Dinesh", "Imran", "Varun", "Siddharth", "Manoj", "Ashwin"]
_SWAP_PRONOUN = {"he": "she", "she": "he", "him": "her", "his": "her", "hers": "his", "himself": "herself",
                 "herself": "himself"}
_SWAP_GENDER = {"male": "female", "female": "male", "man": "woman", "woman": "man", "women": "men", "men": "women",
                "boy": "girl", "girl": "boy", "boys": "girls", "girls": "boys", "lady": "gentleman",
                "gentleman": "lady", "ladies": "gentlemen"}
_SWAP_TITLE = {"mr": "Ms. ", "mrs": "Mr. ", "ms": "Mr. ", "miss": "Mr. ", "smt": "Shri ", "shri": "Smt "}
_NEUTRAL = {"he": "they", "she": "they", "him": "them", "his": "their", "hers": "theirs", "himself": "themselves",
            "herself": "themselves"}
_OBJ_FOLLOW = frozenset("to for with and in on at by from . , ; : ) as".split())


def _keep_case(src, repl):
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _is_skill_word(word):
    return (word.lower(),) in ontology.ALIAS_INDEX or word.lower() in STOPWORDS


def find_name(text):
    """Name tokens from the first plausible name line (or a "Name:" field)."""
    m = re.search(r"(?im)^\s*(?:full\s+)?name\s*[:\-]\s*([A-Za-z .'-]{3,60})$", text)
    if m:
        cand = m.group(1).strip()
    else:
        cand = None
        for line in text.split("\n"):
            if not line.strip():
                continue
            nm = _NAME_LINE.match(line)
            if nm:
                words = [w.strip(".").lower() for w in nm.group(1).split()]
                if not any(w in _NOT_NAME_WORDS for w in words):
                    cand = nm.group(1)
            break
    if not cand:
        return []
    return [w.strip(".") for w in cand.split() if len(w.strip(".")) >= 2 and not _is_skill_word(w.strip("."))]


def find_spans(text):
    """[(start, end, kind, original)] identity spans in cleaned text, non-overlapping."""
    spans = []

    def add(s, e, kind):
        if e > s:
            spans.append((s, e, kind, text[s:e]))

    for m in _KV_RE.finditer(text):
        key = m.group("key")
        kind = next((k for k, rx in _KEY_KIND if rx.match(key)), "personal")
        if kind == "location" and m.group("key").lower() in ("address", "permanent address", "current address"):
            end = text.find("\n", m.start("val"))
            add(m.start("val"), end if end >= 0 else len(text), kind)
        elif kind == "name":
            continue  # handled by find_name so every occurrence of the name is masked
        else:
            val_end = m.end("val")
            while val_end > m.start("val") and text[val_end - 1] in " .":
                val_end -= 1
            add(m.start("val"), val_end, kind)
    for m in _PHOTO_LINE.finditer(text):
        add(m.start(), m.end(), "photo")
    for m in EMAIL_RE.finditer(text):
        add(m.start(), m.end(), "contact")
    for m in _PHONE_RE.finditer(text):
        add(m.start(), m.end(), "contact")
    for m in _URL_RE.finditer(text):
        add(m.start(), m.end(), "contact")
    for tok in find_name(text):
        for m in re.finditer(r"\b%s\b" % re.escape(tok), text, re.I):
            add(m.start(), m.end(), "name")
    for m in _PRONOUN_RE.finditer(text):
        add(m.start(), m.end(), "pronoun")
    for m in _TITLE_RE.finditer(text):
        add(m.start(), m.end(), "title")
    for m in _GENDER_RE.finditer(text):
        add(m.start(), m.end(), "gender")
    for m in _AGE_INLINE.finditer(text):
        add(m.start(), m.end(), "age")
    for m in _INST_RE.finditer(text):
        s, e = m.start(), m.end()
        while e > s and text[e - 1] in " ,.-":
            e -= 1
        if e - s >= 3:
            add(s, e, "institution")
    for m in _CITY_RE.finditer(text):
        add(m.start(), m.end(), "location")
    # graduation years inside the education section (an age proxy)
    offset = 0
    for line, (sec, _c, _h) in zip(text.split("\n"), segment(text)):
        if sec == "education":
            for m in re.finditer(r"\b(?:19[89]\d|20[0-4]\d)\b", line):
                add(offset + m.start(), offset + m.end(), "grad_year")
        offset += len(line) + 1
    # resolve overlaps: earliest start, then longest
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    last_end = -1
    for sp in spans:
        if sp[0] >= last_end:
            out.append(sp)
            last_end = sp[1]
    return out


def _render(text, spans, repl_fn):
    parts = []
    pos = 0
    for s, e, kind, orig in spans:
        parts.append(text[pos:s])
        parts.append(repl_fn(kind, orig, text, e))
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


def _neutral_pronoun(orig, text, end):
    low = orig.lower()
    if low == "her":
        nxt = re.match(r"\s*([A-Za-z.,;:)]+)", text[end:])
        follow = nxt.group(1).lower() if nxt else "."
        repl = "them" if (follow in _OBJ_FOLLOW or follow[:1] in ".,;:)") else "their"
    else:
        repl = _NEUTRAL.get(low, "they")
    return _keep_case(orig, repl)


def mask(text):
    """Blind-mode text plus an audit trail of what was hidden."""
    text = clean(text)
    spans = find_spans(text)

    def repl(kind, orig, full, end):
        if kind == "pronoun":
            return _neutral_pronoun(orig, full, end)
        return PLACEHOLDER.get(kind, "[REDACTED]")

    masked = _render(text, spans, repl)
    counts = {}
    for _s, _e, kind, _o in spans:
        counts[kind] = counts.get(kind, 0) + 1
    return {"text": masked,
            "redactions": [{"kind": k, "label": KIND_LABELS.get(k, k), "original": o} for _s, _e, k, o in spans],
            "counts": counts,
            "total": len(spans)}


def strip(text):
    """Identity fields deleted outright (pronouns neutralised so sentences still parse)."""
    text = clean(text)
    spans = find_spans(text)

    def repl(kind, orig, full, end):
        if kind == "pronoun":
            return _neutral_pronoun(orig, full, end)
        return ""

    return _render(text, spans, repl)


def counterfactual(text, salt=""):
    """Same resume, opposite identity: gender, name, college tier, age and city swapped."""
    text = clean(text)
    spans = find_spans(text)
    h = zlib.crc32((salt + text[:200]).encode("utf-8"))
    name_tokens = find_name(text)
    first = name_tokens[0] if name_tokens else ""
    if first.capitalize() in FEMALE_NAMES:
        new_first = MALE_NAMES[h % len(MALE_NAMES)]
    elif first.capitalize() in MALE_NAMES:
        new_first = FEMALE_NAMES[h % len(FEMALE_NAMES)]
    else:
        new_first = (FEMALE_NAMES + MALE_NAMES)[h % 40]
    other_cities = [c for c in CITIES[:12]]

    def repl(kind, orig, full, end):
        low = orig.lower()
        if kind == "name":
            if first and low == first.lower():
                return _keep_case(orig, new_first)
            return _keep_case(orig, "Varghese" if low != "varghese" else "Nadar")
        if kind == "pronoun":
            if low == "her":
                nxt = re.match(r"\s*([A-Za-z.,;:)]+)", full[end:])
                follow = nxt.group(1).lower() if nxt else "."
                return _keep_case(orig, "him" if follow in _OBJ_FOLLOW else "his")
            return _keep_case(orig, _SWAP_PRONOUN.get(low, low))
        if kind == "title":
            return _SWAP_TITLE.get(low.strip(" .").lower(), "")
        if kind == "gender":
            base = low[:-2] if low.endswith("'s") else low
            return _keep_case(orig, _SWAP_GENDER.get(base, base)) + ("'s" if low.endswith("'s") else "")
        if kind == "age":
            return re.sub(r"\d{2}", lambda m: str(int(m.group(0)) + 6), orig)
        if kind == "institution":
            return "Government Arts College" if _TOP_INST.search(orig) else "IIT Bombay"
        if kind == "location":
            if orig in CITIES:
                return other_cities[(other_cities.index(orig) + 3) % len(other_cities)] if orig in other_cities \
                    else other_cities[h % len(other_cities)]
            return "Salem"
        if kind == "contact":
            if "@" in orig:
                return "candidate%d@mail.example" % (h % 97)
            if re.search(r"\d{5}", orig):
                return "+91 90000 %05d" % (h % 99999)
            return "github.com/candidate%d" % (h % 97)
        if kind == "grad_year":
            return str(int(orig) - 3)
        if kind == "family":
            return "Ramesh Varghese"
        if kind == "marital":
            return "Married" if "single" in low or "unmarried" in low else "Single"
        if kind == "religion":
            return "Christian" if "hindu" in low else "Hindu"
        return orig

    return _render(text, spans, repl)
