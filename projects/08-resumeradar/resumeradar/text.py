"""Text normalisation, tokenisation, stop words and a light stemmer."""
import re
import unicodedata

# A token is a run of letters/digits, optionally followed by "+"/"#" (C++, C#) or by
# dotted parts (node.js, asp.net, b.tech). A leading dot keeps ".net" together.
TOKEN_RE = re.compile(r"\.?[A-Za-z0-9]+(?:[+#]+|(?:\.[A-Za-z0-9]+)+)?")

URL_RE = re.compile(
    r"(?:https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|in|io|dev|me|org|net|co|ai|app)(?:/[\w./?=&%#-]*)?)",
    re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z ]{1,24}\]")
BULLET_RE = re.compile(r"^\s*(?:[-*>]|\d{1,2}[.)])\s+")

_REPL = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ", "•": "-",
}
_BULLET_GLYPHS = re.compile(r"(?m)^[ \t]*[▪●◦‣∙·■□➢➤►✓✔❖]\s*")

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each etc few for
from further had has have having here how i if in into is it its itself just me more most my
myself no nor not now of off on once only or other our ours out over own per same she should
so some such than that the their them then there these they this those through to too under
until up upon us using very via was we were what when where which while who whom why will
with within without would you your yours e.g i.e eg ie
""".split())


def clean(text):
    """Normalise unicode quirks, line endings and bullet glyphs. Idempotent."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    for a, b in _REPL.items():
        text = text.replace(a, b)
    text = _BULLET_GLYPHS.sub("- ", text)
    text = re.sub(r"\bR&D\b", "research and development", text)
    return text


def _norm_token(tok):
    low = tok.lower()
    if low.endswith("+") and low not in ("c++", "g++"):
        tok = tok.rstrip("+")
    return tok


def tokens_with_case(text):
    """List of original-case tokens (used where case matters, e.g. "Go" vs "go")."""
    out = []
    for m in TOKEN_RE.finditer(text):
        t = _norm_token(m.group(0))
        if t:
            out.append(t)
    return out


def tokenize(text):
    return [t.lower() for t in tokens_with_case(text)]


def stem(word):
    """Conservative suffix stripper: plurals, -ing, -ed, -ment, -ation, trailing e."""
    if len(word) <= 3 or not word.isalpha():
        return word
    w = word
    for suf, rep in (("isation", "ize"), ("ization", "ize"), ("ational", "ate"), ("ation", "ate")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + rep
            break
    if w.endswith("ies") and len(w) > 5:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "as", "os")) and not (w.endswith("is") and len(w) > 4):
        w = w[:-1]
    for suf in ("ments", "ment", "ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def content_terms(text):
    """Tokens for TF-IDF: placeholders/URLs/emails removed, stop words and numbers dropped."""
    text = PLACEHOLDER_RE.sub(" ", text)
    text = EMAIL_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    out = []
    for t in tokenize(text):
        t = t.strip(".")
        if len(t) < 2 or t in STOPWORDS:
            continue
        if t.replace(".", "").isdigit():
            continue
        out.append(stem(t))
    return out


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'+#.-]*", text or ""))


def surface_forms(text, stems):
    """{stem: first original word in text with that stem} - to display stemmed terms nicely."""
    want = set(stems)
    out = {}
    for t in tokenize(text):
        t = t.strip(".")
        st = stem(t)
        if st in want and st not in out:
            out[st] = t
    return out
