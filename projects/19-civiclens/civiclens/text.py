"""Unicode-aware text processing for English, Tamil script and Tanglish complaints.

Why not ``re.findall(r"\\w+")``? Tamil vowel signs and the virama (்) are Unicode *marks*
(category Mn/Mc) and are not "word characters", so a regex tokenizer cuts குப்பை into
pieces. We scan characters by Unicode category instead and keep marks attached.
"""

import re
import unicodedata

from . import lexicon as L

ZW = ("‌", "‍")          # zero-width (non-)joiners appear inside Indic words
_REPEAT = re.compile(r"(.)\1{2,}")  # "plsss" -> "plss", "romba romba" untouched


def _is_word_char(ch):
    cat = unicodedata.category(ch)
    return cat[0] in "LMN" or ch in ZW


def is_tamil(ch):
    return "஀" <= ch <= "௿"


def tokenize(text):
    """Lower-cased word tokens; Tamil combining marks stay inside their word."""
    if not text:
        return []
    text = unicodedata.normalize("NFC", str(text))
    out, cur = [], []
    for ch in text:
        if _is_word_char(ch):
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    toks = []
    for t in out:
        t = t.strip("".join(ZW))
        if not t:
            continue
        if not any(is_tamil(c) for c in t):
            t = _REPEAT.sub(r"\1\1", t.casefold())
        toks.append(t)
    return toks


def graphemes(word):
    """Split into user-perceived letters: a base character plus its combining marks.

    'குப்பை' -> ['கு', 'ப்', 'பை'];  'street' -> ['s','t','r','e','e','t'].
    """
    out = []
    for ch in word:
        if out and (unicodedata.category(ch)[0] == "M" or ch in ZW):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def char_ngrams(word, ns=(3, 4)):
    """Grapheme n-grams of a word with boundary markers, e.g. '<st', 'str', ..., 'et>'."""
    units = ["<"] + graphemes(word) + [">"]
    grams = []
    for n in ns:
        for i in range(len(units) - n + 1):
            grams.append("".join(units[i:i + n]))
    return grams


def word_ngrams(tokens, n_max=2):
    grams = list(tokens)
    if n_max >= 2:
        grams += [tokens[i] + " " + tokens[i + 1] for i in range(len(tokens) - 1)]
    return grams


def script_of(text):
    """'ta' if mostly Tamil script, 'tg' if Latin with Tanglish markers, else 'en'."""
    letters = [c for c in str(text) if c.isalpha() or unicodedata.category(c)[0] == "M"]
    if not letters:
        return "en"
    if sum(1 for c in letters if is_tamil(c)) / len(letters) >= 0.3:
        return "ta"
    toks = set(tokenize(text))
    if len(toks & TANGLISH_MARKERS) >= 1:
        return "tg"
    return "en"


TANGLISH_MARKERS = {
    "iruku", "irukku", "illa", "romba", "pannunga", "aagala", "varala", "kitta", "thanni", "kuppai",
    "eriyala", "naai", "edukala", "pakkathula", "aaguthu", "theru", "kovil", "kuzhi", "sakkadai", "maadu",
    "kosu", "vilakku", "saapadu", "nethu", "aachu", "mudiyala", "pora", "poraanga", "thongitu", "naala",
    "vaarama", "kadai", "edunga", "seekiram", "pannala", "varuthu", "adikuthu", "nikuthu", "suthuthu",
}


# ----------------------------------------------------------------------------- concept tokens
def _latin_stem(t):
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


_TAMIL_KEYS = sorted(((graphemes(k), v) for k, v in L.TAMIL.items() if " " not in k),
                     key=lambda kv: -len(kv[0]))
_TG_STEMS = sorted(L.TANGLISH_STEMS.items(), key=lambda kv: -len(kv[0]))


def concept_of(token):
    """Map one token to a list of concepts ([] = filler, [token] = unknown, kept as-is)."""
    if any(is_tamil(c) for c in token):
        g = graphemes(token)
        for key, val in _TAMIL_KEYS:
            if len(key) <= len(g) and g[:len(key)] == key:
                return val.split() if val else []
        return [token]
    if token in L.LATIN:
        v = L.LATIN[token]
        return [v] if v else []
    st = _latin_stem(token)
    if st in L.LATIN:
        v = L.LATIN[st]
        return [v] if v else []
    if len(token) >= 5:
        for stem, val in _TG_STEMS:
            if token.startswith(stem):
                return [val]
    if token.isdigit():
        return []
    fz = fuzzy_lookup(token)
    if fz:
        return [fz]
    return [st]


# Typo tolerance for the words that matter most (safety rules and core issues):
# one insertion, deletion, substitution or adjacent swap is forgiven for words of 6+ letters.
FUZZY_WORDS = ["accident", "manhole", "pothole", "garbage", "drainage", "sewage", "electric", "current",
               "mosquito", "collected", "overflowing", "drinking", "streetlight", "leaking", "hanging",
               "broken", "blocked", "stagnant", "fogging", "loudspeaker", "encroachment", "footpath",
               "pipeline", "dangerous", "children", "elderly", "school", "kuppai", "sakkadai", "thanni"]


def edit_distance_le1(a, b):
    """True if Damerau-Levenshtein distance(a, b) <= 1 (fast, no full DP)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def fuzzy_lookup(token):
    if len(token) < 6 or not token.isalpha():
        return None
    for w in FUZZY_WORDS:
        if w[0] == token[0] and abs(len(w) - len(token)) <= 1 and edit_distance_le1(token, w):
            v = L.LATIN.get(w, w)
            return v or None
    return None


def concepts(text_or_tokens):
    """Language-neutral concept tokens with common bigrams merged (order kept)."""
    toks = tokenize(text_or_tokens) if isinstance(text_or_tokens, str) else text_or_tokens
    seq = []
    for t in toks:
        seq.extend(concept_of(t))
    out, i = [], 0
    while i < len(seq):
        if i + 1 < len(seq) and (seq[i], seq[i + 1]) in L.PHRASES:
            out.append(L.PHRASES[(seq[i], seq[i + 1])])
            i += 2
        else:
            out.append(seq[i])
            i += 1
    return [c for c in out if c]


def shingles(text, bigrams=False):
    """Shingle set for MinHash: the set of concept tokens (optionally plus adjacent bigrams).

    Unigram concepts work better than bigrams here: paraphrases and Tamil word order move
    words around, which breaks bigrams but keeps the concept set.
    """
    c = concepts(text)
    s = set(c)
    if bigrams:
        s.update(c[i] + "_" + c[i + 1] for i in range(len(c) - 1))
    return s


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / float(len(a | b))
