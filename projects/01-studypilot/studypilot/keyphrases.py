"""Key-concept extraction with RAKE (Rose et al., 2010) + an occurrence boost.

RAKE: split text into candidate phrases at stop words and punctuation. For each
word w, freq(w) = number of candidate phrases containing w and deg(w) = sum of
the lengths of those phrases. word_score(w) = deg(w) / freq(w);
phrase_score = Σ word_score(w).

Plain RAKE ignores how often a phrase is repeated, which under-rates the main
topic word (e.g. "deadlock"). We therefore multiply by log2(1 + occurrences),
where occurrences counts the phrase anywhere in the text (also inside longer
phrases). Phrases that only ever occur inside one longer phrase are merged into it.
"""
import math
import re
from collections import Counter, defaultdict

from .text import STOP_WORDS

MAX_WORDS = 3   # longest candidate phrase kept (RAKE papers commonly use 3)
# Ranking multipliers on top of RAKE's mean word score (tuned by eye on the samples;
# technical terms are often compounds and are usually what sentences are "about").
LENGTH_BONUS = {1: 0.9, 2: 1.6, 3: 1.8}
SUBJECT_BONUS = 2.0     # phrase opens a sentence (definition-like position)
ACRONYM_BONUS = 1.3     # TCP, UDP, DNS ...
GENERIC_SPREAD = 0.3    # single words in >30% of sentences are topic words, not quiz answers

# Generic words that rarely make good study concepts; they also break phrases.
RAKE_EXTRA_STOP = frozenset("""
called known used uses using use usually typically commonly common simple simply new
first second third one two three four five several many various different each every
example examples important instead given makes make made way ways part parts set lot
largely mainly mostly simultaneously exactly sometimes practice possible necessary
sufficient well better best good bad high low large small long short whole same
directly independently automatically normally especially despite like still
kept keeps keep take takes taken another certain particular whether general
""".split())

# Common English verbs (3rd person / base forms). Without a POS tagger, verbs are
# the main source of junk RAKE phrases ("subnet mask divides"), so they break phrases.
VERBS = frozenset("""
means mean refers refer describes describe contains contain provides provide requires
require allows allow uses use sends send adds add becomes become reaches reach carries
carry assigns assign translates translate transfers divides divide splits
partitions removes remove takes take gives give gets get keeps causes cause reduces
reduce shrinks shrink drives trains learns estimates classifies classify passes
performs perform works tries try produces produce makes make holds waits releases
requests grants runs maintains maintain finds find enters aborts ensures ensure imposes
impose leads leave leaves ignores ignore occurs occur happens happen exists exist stays
delivers deliver establishes establish retransmits retransmit detects detect expires
adjusts adjust overload overloads overwhelm overwhelms tolerate tolerates handles rely
relies guarantee guarantees identified identify identifies decremented written built
described assigned obtained proposed chosen fitted advertised called based applied
given computed preferred defined known required tabulates compute computes discover
discovers maximise maximises maximize maximizes minimise minimises minimize minimizes
generalises generalizes validates validate repeating repeats averaging recomputing
assigning reducing grouping imposing requiring selecting rolling ensuring changing
making using having being getting lets let begins begin completed emits returns
represents represent increases decreases depends depend involves involve consists
consist includes include shows show helps help prevents prevent plus held woken
begun done seen taken shown
""".split())

# Words after which a trailing "-s" word is most likely a verb ("mask divides AN ...").
_DETERMINERS = frozenset("a an the its their this these those it each every whether".split())

DEFINITION_VERBS = frozenset("is are means refers describes happens occurs".split())

_PUNCT_GAP = re.compile(r"[^\s]")


def _breaks(tok):
    w = tok.lower
    return (tok.is_stop or w in RAKE_EXTRA_STOP or w in VERBS or w.isdigit()
            or len(w) < 2)


def _looks_like_verb(tokens, idx, in_phrase):
    """Heuristic POS guess: a non-initial '-s' word followed by a determiner, or a
    phrase-final '-ed' participle ("window advertised by")."""
    w = tokens[idx].lower
    nxt = tokens[idx + 1].lower if idx + 1 < len(tokens) else ""
    if in_phrase and w.endswith("s") and not w.endswith(("ss", "us", "is")) \
            and nxt in _DETERMINERS:
        return True
    if in_phrase and w.endswith("ed") and len(w) > 4 and (
            nxt in ("by", "to", "from", "with", "for", "in", "on", "at") or not nxt):
        return True
    return False


def candidates(sentences):
    """Yield (sentence_id, token_start, token_end) spans of candidate phrases."""
    for s in sentences:
        cur = []
        prev_end = None
        for idx, tok in enumerate(s.tokens):
            gap = s.text[prev_end:tok.start] if prev_end is not None else ""
            brk = _breaks(tok) or _looks_like_verb(s.tokens, idx, bool(cur))
            if brk or _PUNCT_GAP.search(gap):
                if cur:
                    yield s.id, cur[0], cur[-1] + 1
                cur = []
            if not brk:
                cur.append(idx)
            prev_end = tok.end
        if cur:
            yield s.id, cur[0], cur[-1] + 1


def _stem_index(sentences):
    """first-stem -> [(sentence_id, position)] so phrase lookups are fast."""
    index = defaultdict(list)
    for s in sentences:
        for i, t in enumerate(s.tokens):
            index[t.stem].append((s.id, i))
    return index


def _find_occurrences(sentences, stems, index=None):
    """All (sentence_id, start, end) where the stem sequence occurs contiguously."""
    n = len(stems)
    occ = []
    if index is None:
        index = _stem_index(sentences)
    for sid, i in index.get(stems[0], ()):
        toks = sentences[sid].tokens
        if i + n <= len(toks) and all(toks[i + k].stem == stems[k] for k in range(1, n)):
            occ.append((sid, i, i + n))
    return occ


def _surface(sentences, spans):
    """Pick a display form: lower-case unless the word is always capitalised
    mid-sentence (acronyms like TCP or names like Dijkstra keep their case)."""
    n = spans[0][2] - spans[0][1]
    out = []
    for pos in range(n):
        variants = []
        for sid, a, b in spans:
            variants.append((sentences[sid].tokens[a + pos].text, a + pos == 0))
        lower = [v for v, _ in variants if v.islower()]
        mid = [v for v, start in variants if not start]
        if lower:
            out.append(lower[0])
        elif mid:
            out.append(mid[0])
        else:
            v = variants[0][0]
            out.append(v if (v.isupper() and len(v) > 1) else v.lower())
    return " ".join(out).replace("\u2019", "'")


def concept_type(phrase):
    """Coarse 'type' features used to pick MCQ distractors of a similar kind."""
    words = phrase.split()
    head = words[-1].lower()
    is_acronym = all(w.isupper() and len(w) > 1 for w in words if w.isalpha()) and \
        any(w.isalpha() for w in words)
    suffix = "other"
    for suf, label in (("tion", "process-noun"), ("sion", "process-noun"),
                       ("ing", "activity"), ("ment", "process-noun"),
                       ("ity", "property"), ("ness", "property"), ("ism", "concept"),
                       ("er", "agent"), ("or", "agent"), ("ure", "thing"),
                       ("ol", "protocol"), ("thm", "algorithm"), ("ix", "structure"),
                       ("graph", "structure"), ("ss", "process-noun")):
        if head.endswith(suf):
            suffix = label
            break
    return {"words": len(words), "acronym": is_acronym, "suffix": suffix, "head": head}


def _is_subject(tokens, a, b):
    """True if the phrase is the grammatical subject at the start of a sentence
    ("Gradient descent is ...", "The Banker's algorithm, proposed by ...")."""
    if not all(t.lower in ("a", "an", "the") for t in tokens[:a]):
        return False
    if b - a > 1:
        return True
    nxt = tokens[b].lower if b < len(tokens) else ""
    word = tokens[a].text
    return nxt in DEFINITION_VERBS or (word.isupper() and len(word) > 1)  # single words need a definition-like verb


def extract(sentences, top_k=30, max_words=MAX_WORDS):
    spans = [c for c in candidates(sentences) if c[2] - c[1] <= max_words]
    by_key = defaultdict(list)
    for sid, a, b in spans:
        key = tuple(t.stem for t in sentences[sid].tokens[a:b])
        by_key[key].append((sid, a, b))

    freq, deg = Counter(), Counter()
    for key, occ in by_key.items():
        for w in key:
            freq[w] += len(occ)
            deg[w] += len(occ) * len(key)
    word_score = {w: deg[w] / freq[w] for w in freq}

    concepts = []
    index = _stem_index(sentences)
    for key, cand_spans in by_key.items():
        surface = _surface(sentences, cand_spans)
        if len(surface.replace(" ", "")) < 3:
            continue
        occ = _find_occurrences(sentences, key, index)
        rake = sum(word_score[w] for w in key)
        subject = any(_is_subject(sentences[sid].tokens, a, b) for sid, a, b in cand_spans)
        if len(key) == 1:
            if surface.endswith("ed") or (surface.endswith("ing") and not subject):
                continue  # lone participles ("held", "waiting") are rarely concepts
        acronym = any(sentences[sid].tokens[a].text.isupper() for sid, a, b in cand_spans)
        score = (rake / len(key)) * LENGTH_BONUS.get(len(key), 1.8) \
            * (1 + math.log2(len(occ) or 1)) \
            * (SUBJECT_BONUS if subject else 1.0) * (ACRONYM_BONUS if acronym else 1.0)
        concepts.append({
            "key": " ".join(key), "stems": list(key), "phrase": surface,
            "rake": round(rake, 3), "occurrences": len(occ), "subject": subject,
            "score": score, "occ": occ,
            "word_scores": {w: round(word_score[w], 3) for w in key},
        })

    # merge sub-phrases that never appear on their own
    keys = {c["key"]: c for c in concepts}
    drop = set()
    for c in concepts:
        if len(c["stems"]) < 2:
            continue
        for n in range(1, len(c["stems"])):
            for i in range(len(c["stems"]) - n + 1):
                sub = " ".join(c["stems"][i:i + n])
                if sub in keys and keys[sub]["occurrences"] <= c["occurrences"]:
                    drop.add(sub)
    concepts = [c for c in concepts if c["key"] not in drop]
    # single words seen once are almost always noise
    concepts = [c for c in concepts if not (len(c["stems"]) == 1 and c["occurrences"] < 2)]

    concepts.sort(key=lambda c: (-c["score"], c["key"]))
    concepts = concepts[:top_k]
    top = concepts[0]["score"] if concepts else 1.0
    for c in concepts:
        c["weight"] = round(c["score"] / top, 4)
        c["score"] = round(c["score"], 4)
        c["type"] = concept_type(c["phrase"])
        c["sentences"] = sorted({o[0] for o in c["occ"]})
        # good quiz/flashcard answers: compounds, defined terms or acronyms, and not
        # the ubiquitous topic word (blanking "deadlock" in deadlock notes is trivial)
        single = len(c["stems"]) == 1
        spread = len(c["sentences"]) / max(1, len(sentences))
        c["quizzable"] = (not single or c["subject"] or c["type"]["acronym"]) and \
            not (single and spread > GENERIC_SPREAD)
    return concepts


def type_similarity(a, b):
    """Score how alike two concepts are in 'kind', with human-readable reasons."""
    ta, tb = a["type"], b["type"]
    score, why = 0.0, []
    if ta["words"] == tb["words"]:
        score += 2
        why.append("same length (%d word%s)" % (ta["words"], "" if ta["words"] == 1 else "s"))
    if ta["acronym"] == tb["acronym"]:
        score += 2 if ta["acronym"] else 0.5
        if ta["acronym"]:
            why.append("both acronyms")
    if ta["suffix"] == tb["suffix"] and ta["suffix"] != "other":
        score += 1.5
        why.append("same word form (%s)" % ta["suffix"])
    shared = set(a["stems"]) & set(b["stems"])
    if shared:
        score += 2.5
        why.append("shares the word '%s'" % sorted(shared)[0])
    if ta["head"] == tb["head"]:
        score += 1
    score += 1 - abs(a["weight"] - b["weight"])  # similar importance
    return score, why
