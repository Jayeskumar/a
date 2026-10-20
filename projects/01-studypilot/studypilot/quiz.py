"""Automatic quiz generation: cloze (fill-in-the-blank) and multiple-choice.

Pipeline
1. Rank sentences by TextRank; keep those with >= MIN_CONTENT_TERMS content words
   that mention at least one key concept.
2. In each chosen sentence blank out its most important concept that has not been
   used yet (so one quiz tests many different concepts).
3. MCQ distractors = other key concepts of the most similar "type" (same word count,
   acronym-ness, word form, shared head word) that do NOT appear in the sentence and
   do not overlap the answer.
4. Grading normalises answers (lower-case, stemmed, stop words removed) and accepts
   one typo per ~6 characters for cloze answers.
"""
import random
import re

from .keyphrases import type_similarity
from .text import tokenize, content_terms

BLANK = "_____"
MIN_CONTENT_TERMS = 5
MCQ_OPTIONS = 4
MAX_SPAN_SHARE = 0.5   # do not blank a concept covering more than half the sentence


def _span_chars(sentence, a, b):
    return sentence.tokens[a].start, sentence.tokens[b - 1].end


def _overlaps(c1, c2):
    s1, s2 = set(c1["stems"]), set(c2["stems"])
    return s1 <= s2 or s2 <= s1


def distractors(answer, concepts, sentence_id, k=MCQ_OPTIONS - 1):
    """Pick k distractor concepts with reasons. Returns list of (concept, why)."""
    pool = []
    seen_phrases = {answer["phrase"].lower()}
    for c in concepts:
        if c["key"] == answer["key"] or _overlaps(c, answer):
            continue
        if sentence_id in c["sentences"]:
            continue  # would be visible in the question itself
        if c["phrase"].lower() in seen_phrases:
            continue
        score, why = type_similarity(answer, c)
        pool.append((score, c["weight"], c, why))
    pool.sort(key=lambda x: (-x[0], -x[1], x[2]["key"]))
    out = []
    for score, _, c, why in pool:
        if c["phrase"].lower() in seen_phrases:
            continue
        seen_phrases.add(c["phrase"].lower())
        out.append((c, why or ["another key concept from your notes"]))
        if len(out) == k:
            break
    return out


def candidate_items(analysis):
    """(sentence_id, [concepts present ordered by weight]) in TextRank order."""
    items = []
    for sid in analysis.rank["order"]:
        if len(analysis.terms[sid]) < MIN_CONTENT_TERMS:
            continue
        present = [c for c in analysis.concepts if sid in c["sentences"] and c["quizzable"]]
        # prefer longer (more specific) phrases, then importance
        present.sort(key=lambda c: (-min(len(c["stems"]), 2), -c["weight"]))
        if present:
            items.append((sid, present))
    return items


def generate(analysis, n=8, seed=0):
    """Return a list of question dicts (including answers; strip before sending)."""
    items = candidate_items(analysis)
    if seed:
        rng = random.Random(seed)
        pool = items[: max(3 * n, n + 6)]
        rng.shuffle(pool)
        items = pool + items[len(pool):]
    used, questions = set(), []
    for sid, present in items:
        if len(questions) >= n:
            break
        s = analysis.sentences[sid]
        chosen = None
        for c in present:
            if c["key"] in used:
                continue
            spans = [(a, b) for (osid, a, b) in c["occ"] if osid == sid]
            a, b = spans[0]
            if (b - a) / max(1, len(s.tokens)) > MAX_SPAN_SHARE:
                continue
            st, en = _span_chars(s, a, b)
            if (st > 0 and s.text[st - 1] in "/-") or s.text[en:en + 1] in ("/", "-"):
                continue  # part of a compound like TCP/IP
            chosen = (c, a, b)
            break
        if not chosen:
            continue
        c, a, b = chosen
        used.add(c["key"])
        start, end = _span_chars(s, a, b)
        prompt = s.text[:start] + BLANK + s.text[end:]
        qid = "q%d" % (len(questions) + 1)
        q = {
            "id": qid, "sentence_id": sid, "concept": c["key"],
            "prompt": prompt, "answer": c["phrase"],
            "answer_surface": s.text[start:end],
            "source": s.text, "answer_span": [start, end],
            "why": {
                "sentence_rank": analysis.rank["ranks"][sid] + 1,
                "sentence_score": round(analysis.rank["scores"][sid] * len(analysis.sentences), 3),
                "concept_weight": c["weight"],
            },
        }
        ds = distractors(c, analysis.concepts, sid)
        want_mcq = len(ds) == MCQ_OPTIONS - 1 and len(questions) % 3 != 2
        if want_mcq:
            options = [c["phrase"]] + [d["phrase"] for d, _ in ds]
            random.Random(seed * 7919 + sid).shuffle(options)
            q["kind"] = "mcq"
            q["options"] = options
            q["distractors"] = [{"phrase": d["phrase"], "why": why} for d, why in ds]
        else:
            q["kind"] = "cloze"
            q["hint"] = "%d word%s, starts with '%s'" % (
                len(c["phrase"].split()), "" if len(c["phrase"].split()) == 1 else "s",
                c["phrase"][0])
        questions.append(q)
    return questions


PUBLIC_FIELDS = ("id", "kind", "prompt", "options", "hint", "concept")


def public(question):
    return {k: question[k] for k in PUBLIC_FIELDS if k in question}


def normalise(answer):
    toks = tokenize(answer or "")
    return " ".join(content_terms(toks)) or " ".join(t.lower for t in toks)


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def grade(question, answer):
    """Return dict(correct, expected, given, feedback)."""
    given = (answer or "").strip()
    if question["kind"] == "mcq":
        correct = given.lower() == question["answer"].lower()
        how = "exact option match"
    else:
        g, e = normalise(given), normalise(question["answer"])
        dist = levenshtein(re.sub(r"\s+", "", g), re.sub(r"\s+", "", e))
        tolerance = max(1, len(e) // 6) if len(e) > 3 else 0
        correct = bool(g) and dist <= tolerance
        how = "exact match" if dist == 0 else (
            "accepted with %d typo%s" % (dist, "" if dist == 1 else "s") if correct else
            "edit distance %d > %d allowed" % (dist, tolerance))
    return {"id": question["id"], "correct": correct, "given": given,
            "expected": question["answer"], "match": how,
            "source": question["source"], "answer_span": question["answer_span"],
            "why": question["why"], "concept": question["concept"],
            "distractors": question.get("distractors", [])}
