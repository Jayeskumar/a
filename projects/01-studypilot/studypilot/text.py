"""Text processing primitives written from scratch: tokenizer, sentence splitter,
stop-word list and a light suffix-stripping stemmer.

Nothing here depends on third-party libraries, so it runs on any Python 3.9+ install.
"""
import re
from collections import namedtuple

# ---------------------------------------------------------------------------
# Stop words: a compact English list (function words + question words).
# ---------------------------------------------------------------------------
STOP_WORDS = frozenset("""
a about above after again against all almost also am an and any are aren't as at
be because been before being below between both but by can cannot could couldn't
did didn't do does doesn't doing don't down during each either else even ever every
few for from further had hadn't has hasn't have haven't having he her here hers
herself him himself his how however i if in into is isn't it it's its itself just
let's may me might more most much must my myself no nor not now of off often on once
only or other others otherwise our ours ourselves out over own per rather same shall
she should shouldn't since so some such than that that's the their theirs them
themselves then there there's therefore these they this those though through thus to
too under until up upon us very via was wasn't we were weren't what what's when
where whereas whether which while who whom whose why will with within without won't
would wouldn't yet you your yours yourself yourselves
""".split())

# Extra words ignored only in questions typed into "Ask your notes".
QUERY_STOP_WORDS = frozenset(
    "explain describe define tell give list name mean meaning means difference "
    "please example examples work works happen happens purpose role".split())

Token = namedtuple("Token", "text lower stem start end is_stop")

# A word is letters/digits, optionally with an apostrophe suffix (banker's) and
# hyphen-joined parts (wait-for, k-means, SYN-ACK, 48-bit).
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?(?:-[A-Za-z0-9]+)*")


def normalize_word(word):
    """Lower-case and drop a possessive / contraction suffix ("Banker's" -> "banker")."""
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    elif w.endswith("'"):
        w = w[:-1]
    return w


_VOWEL = re.compile(r"[aeiouy]")


def stem(word):
    """A light, conservative suffix stripper (inspired by Porter step 1 + a few
    derivational rules). Goal: map inflections of the same word to one key,
    e.g. process/processes, schedule/scheduled/scheduling, allocate/allocation."""
    w = normalize_word(word)
    if len(w) <= 3 or not w.isalpha():
        return w
    # plurals
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    # -ing / -ed
    for suf in ("ingly", "edly", "ing", "ed"):
        if w.endswith(suf):
            base = w[: -len(suf)]
            if len(base) >= 3 and _VOWEL.search(base):
                w = base
                if w[-1] == w[-2] and w[-1] not in "lsz":
                    w = w[:-1]  # running -> run
            break
    if w.endswith("ly") and len(w) > 5:
        w = w[:-2]
    for suf, rep in (("isation", "ize"), ("ization", "ize"), ("ational", "ate"),
                     ("ation", "ate"), ("fulness", "ful"), ("ness", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + rep
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    if w.endswith("y") and len(w) > 3:
        w = w[:-1] + "i"
    return w


def is_stop(word):
    return normalize_word(word) in STOP_WORDS


def tokenize(text):
    """Return Token tuples with character offsets into ``text``."""
    out = []
    for m in WORD_RE.finditer(text):
        t = m.group(0)
        low = normalize_word(t)
        out.append(Token(t, low, stem(t), m.start(), m.end(), low in STOP_WORDS))
    return out


def content_terms(tokens, expand_hyphens=False):
    """Stems of the non-stop tokens. With ``expand_hyphens`` a hyphenated word also
    contributes its parts (k-means -> k-means, mean), which helps retrieval."""
    terms = []
    for t in tokens:
        if t.is_stop or (len(t.lower) < 2 and not t.lower.isdigit()):
            continue
        terms.append(t.stem)
        if expand_hyphens and "-" in t.lower:
            for part in t.lower.split("-"):
                if len(part) > 1 and part not in STOP_WORDS:
                    terms.append(stem(part))
    return terms


def query_terms(text):
    toks = [t for t in tokenize(text) if t.lower not in QUERY_STOP_WORDS]
    return content_terms(toks, expand_hyphens=True)


# ---------------------------------------------------------------------------
# Sentence splitter (markdown aware)
# ---------------------------------------------------------------------------
ABBREVIATIONS = frozenset(
    "e.g i.e etc vs dr mr mrs ms prof fig eq no approx al cf sec ch st jr sr inc ltd".split())

Sentence = namedtuple("Sentence", "id text section para tokens")

_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")
_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*\s+")
_MD_NOISE = re.compile(r"(\*\*|__|`)")


def _split_block(block):
    """Split a paragraph into sentences on . ! ? followed by an upper-case start,
    skipping abbreviations (e.g., i.e.) and decimals (3.14 never has a space)."""
    parts, start = [], 0
    for m in _BOUNDARY.finditer(block):
        end = m.end()
        nxt = block[end:end + 1]
        if not nxt or not (nxt.isupper() or nxt.isdigit() or nxt in "\"'(["):
            continue
        before = block[start:m.start() + 1]
        last_word = re.findall(r"([A-Za-z.]+)\.$", before)
        if last_word and last_word[0].lower().rstrip(".") in ABBREVIATIONS:
            continue
        if re.search(r"\b[A-Z]\.$", before):  # initials like "E. Dijkstra"
            continue
        parts.append(block[start:m.end()].strip())
        start = end
    tail = block[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def split_sentences(text):
    """Return Sentence tuples. Markdown headings become section names (not sentences);
    bullet items and blank-line separated paragraphs become separate blocks."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks, section, buf = [], "", []

    def flush():
        if buf:
            blocks.append((section, " ".join(buf)))
            buf.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        h = _HEADING.match(line)
        if not line:
            flush()
        elif h:
            flush()
            section = _MD_NOISE.sub("", h.group(1)).strip()
        elif _BULLET.match(line):
            flush()
            buf.append(_BULLET.sub("", line))
            flush()
        else:
            buf.append(line)
    flush()

    sentences = []
    for para, (sec, block) in enumerate(blocks):
        block = _MD_NOISE.sub("", block)
        for s in _split_block(block):
            toks = tokenize(s)
            if not toks:
                continue
            sentences.append(Sentence(len(sentences), s, sec, para, toks))
    return sentences


def word_count(text):
    return len(WORD_RE.findall(text or ""))
