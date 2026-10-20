"""Bilingual (English + Tamil) scheme search: tokeniser, light stemmers,
concept map and TF-IDF cosine ranking - all from scratch.

Pipeline (same for documents and queries):
  1. tokenise  - Unicode-aware; keeps Tamil vowel signs / virama, which
                 Python's \\w would split on.
  2. stem      - light suffix stripping (English) / case-suffix + sandhi
                 normalisation (Tamil), e.g. காப்பீட்டுத் -> காப்பீட.
  3. concepts  - phrases from data/keywords.json map words in either language
                 to a shared concept token ("@crop", "@insurance"), so a Tamil
                 query can match English text and vice versa.
  4. TF-IDF    - tf = 1 + ln(count), idf = ln((N + 1) / (df + 1)) + 1,
                 L2-normalised vectors, cosine similarity.
"""
import json
import math
import os
import re
import unicodedata

TAMIL_START, TAMIL_END = 0x0B80, 0x0BFF
_ZW = dict.fromkeys([0x200B, 0x200C, 0x200D, 0xFEFF])

EN_STOP = set("""a an the for of to in on and or my our i me we is are am be with from by at as it
this that who what how can get want need any all some do does please about under scheme schemes yojana
yojna plan programme program government govt""".split())
TA_STOP = set(["திட்டம்", "திட்ட", "மற்றும்", "அல்லது", "உள்ள", "என்ன", "எப்படி", "எனக்கு", "ஒரு", "இந்த", "அரசு"])


def _is_word_char(ch):
    cp = ord(ch)
    if TAMIL_START <= cp <= TAMIL_END:
        return True
    return ch.isalnum()


def tokenize(text):
    """Split into lowercase word tokens; Tamil combining marks stay inside words."""
    text = unicodedata.normalize("NFC", text or "").translate(_ZW).lower()
    out, cur = [], []
    for ch in text:
        if _is_word_char(ch):
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out


def is_tamil(tok):
    return any(TAMIL_START <= ord(c) <= TAMIL_END for c in tok)


# Longest first. Case markers, plural and common clitics.
_TA_SUFFIXES = sorted([
    "த்திற்கு", "த்தினால்", "த்தின்", "த்தில்", "த்தை", "த்தால்", "த்து",
    "ங்களுக்கு", "களுக்கு", "களின்", "களில்", "களை", "கள்",
    "ுக்கு", "க்கு", "ிற்கு", "க்கான", "ுக்கான", "ில்", "ின்", "ுடன்", "ோடு", "ையும்", "ும்",
], key=len, reverse=True)
_TA_FINAL = ["த்", "ப்", "க்", "ச்"]  # sandhi doubling consonant at word end


def stem_ta(tok):
    if len(tok) <= 2:
        return tok
    for suf in _TA_SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 2:
            tok = tok[: -len(suf)]
            break
    for fin in _TA_FINAL:
        if tok.endswith(fin) and len(tok) > 3:
            tok = tok[: -len(fin)]
            break
    # gemination in the oblique form: வீட்டு -> வீடு, ஆற்று -> ஆறு
    if tok.endswith("ட்டு"):
        tok = tok[:-4] + "டு"
    elif tok.endswith("ற்று"):
        tok = tok[:-4] + "று"
    # final -ம் / -ை / -ு are dropped so திட்டம் ~ திட்டத்தின், வீடு ~ வீட்டை
    for fin in ("ம்", "ை", "ு"):
        if tok.endswith(fin) and len(tok) > 2:
            tok = tok[: -len(fin)]
            break
    if tok.endswith("ட்ட"):
        tok = tok[:-3] + "ட"
    elif tok.endswith("ற்ற"):
        tok = tok[:-3] + "ற"
    return tok


def stem_en(tok):
    if len(tok) <= 3 or tok.isdigit():
        return tok
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    if tok.endswith("sses"):
        return tok[:-2]
    if tok.endswith("ing") and len(tok) > 5:
        tok = tok[:-3]
        return tok[:-1] if len(tok) > 2 and tok[-1] == tok[-2] else tok
    if tok.endswith("ed") and len(tok) > 4:
        tok = tok[:-2]
        return tok[:-1] if len(tok) > 2 and tok[-1] == tok[-2] else tok
    if tok.endswith("s") and not tok.endswith("ss") and not tok.endswith("us"):
        return tok[:-1]
    return tok


def stem(tok):
    return stem_ta(tok) if is_tamil(tok) else stem_en(tok)


def analyse_pairs(text):
    """tokens -> [(original token, stem)] without stop words."""
    out = []
    for t in tokenize(text):
        if t in EN_STOP or t in TA_STOP:
            continue
        s = stem(t)
        if s in TA_STOP:
            continue
        out.append((t, s))
    return out


def analyse(text):
    """tokens -> stemmed tokens without stop words."""
    return [s for _, s in analyse_pairs(text)]


class ConceptMap(object):
    """Bilingual phrase -> concept lookup over stemmed token sequences."""

    def __init__(self, concepts):
        self.phrases = []  # (tuple of stems, concept)
        for concept, words in concepts.items():
            for w in [concept.replace("_", " ")] + list(words):
                toks = tuple(stem(t) for t in tokenize(w))
                if toks:
                    self.phrases.append((toks, concept))
        self.phrases.sort(key=lambda p: -len(p[0]))
        self.max_len = max(len(p[0]) for p in self.phrases) if self.phrases else 1
        self.index = {}
        for toks, c in self.phrases:
            self.index.setdefault(toks, set()).add(c)

    def concepts(self, stems, originals=None):
        """Return [(concept, matched_phrase_text)] found in a stem sequence."""
        found = []
        n = len(stems)
        words = originals or stems
        for i in range(n):
            for L in range(min(self.max_len, n - i), 0, -1):
                key = tuple(stems[i:i + L])
                for c in sorted(self.index.get(key, ())):
                    found.append((c, " ".join(words[i:i + L])))
        return found


class TfidfIndex(object):
    CONCEPT_WEIGHT = 2  # a concept hit counts like two word hits

    def __init__(self, docs, concept_map):
        """docs: list of (doc_id, text)."""
        self.cmap = concept_map
        self.ids = [d for d, _ in docs]
        bags = [self._bag(text)[0] for _, text in docs]
        self.N = len(bags)
        df = {}
        for bag in bags:
            for t in bag:
                df[t] = df.get(t, 0) + 1
        self.idf = dict((t, math.log((self.N + 1.0) / (c + 1.0)) + 1.0) for t, c in df.items())
        self.vectors = [self._vector(b) for b in bags]

    def _bag(self, text):
        pairs = analyse_pairs(text)
        stems = [s for _, s in pairs]
        bag = {}
        for s in stems:
            bag[s] = bag.get(s, 0) + 1
        hits = self.cmap.concepts(stems, [o for o, _ in pairs])
        for c, _ in hits:
            key = "@" + c
            bag[key] = bag.get(key, 0) + self.CONCEPT_WEIGHT
        return bag, hits

    def _vector(self, bag):
        vec = {}
        for t, c in bag.items():
            w = (1.0 + math.log(c)) * self.idf.get(t, 0.0)
            if w > 0:
                vec[t] = w
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return dict((t, w / norm) for t, w in vec.items())

    def search(self, query, k=5, min_score=0.02):
        bag, hits = self._bag(query)
        qv = self._vector(bag)
        orig = dict((s, o) for o, s in analyse_pairs(query))
        if not qv:
            return {"query": query, "terms": [], "concepts": [], "results": []}
        scored = []
        for i, dv in enumerate(self.vectors):
            contrib = dict((t, w * dv[t]) for t, w in qv.items() if t in dv)
            s = sum(contrib.values())
            if s >= min_score:
                top = sorted(contrib.items(), key=lambda kv: -kv[1])[:4]
                shown = []
                for t, _ in top:
                    w = t[1:] if t.startswith("@") else orig.get(t, t)
                    if w not in shown:
                        shown.append(w)
                scored.append((s, self.ids[i], shown))
        scored.sort(key=lambda x: (-x[0], x[1]))
        concepts = []
        for c, phrase in hits:
            if not any(c == x["concept"] for x in concepts):
                concepts.append({"concept": c, "matched": phrase})
        return {
            "query": query,
            "terms": sorted(orig.get(t, t) for t in qv if not t.startswith("@")),
            "concepts": concepts,
            "results": [{"id": d, "score": round(s, 4), "matched": m} for s, d, m in scored[:k]],
        }


def scheme_text(s, documents=None):
    parts = [s["short"], s["name"]["en"], s["name"]["ta"], s["summary"]["en"], s["summary"]["ta"],
             s["description"]["en"], s["description"]["ta"], " ".join(s.get("keywords", []))]
    return " . ".join(parts)


def load_concepts(data_dir):
    with open(os.path.join(data_dir, "keywords.json"), encoding="utf-8") as f:
        return json.load(f)["concepts"]


def build_index(catalogue, data_dir):
    cmap = ConceptMap(load_concepts(data_dir))
    return TfidfIndex([(s["id"], scheme_text(s)) for s in catalogue.schemes], cmap)
