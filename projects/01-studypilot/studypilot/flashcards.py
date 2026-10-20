"""Flashcard generation from notes.

* Definition cards: a sentence that opens with a key concept ("Gradient descent is
  ...", "The Banker's algorithm, proposed by ...") becomes  Q: "What is X?"  A: sentence.
* Cloze cards: for remaining top concepts, their best (highest TextRank) sentence with
  the concept blanked.
"""
import hashlib

from .quiz import BLANK, MIN_CONTENT_TERMS

MAX_CARDS = 18
DEF_VERBS = {"is": "What is %s?", "are": "What are %s?", "means": "What does %s mean?",
             "refers": "What does %s refer to?", "describes": "What does %s describe?",
             "happens": "When does %s happen?", "occurs": "When does %s occur?"}


def _card_id(front):
    return hashlib.sha1(front.encode("utf-8")).hexdigest()[:10]


def _starts_with(sentence, a):
    return all(t.lower in ("a", "an", "the") for t in sentence.tokens[:a])


def build(analysis, max_cards=MAX_CARDS):
    cards, used = [], set()
    concepts = analysis.concepts
    # 1) definition cards
    for c in concepts:
        if not c["quizzable"]:
            continue
        for sid, a, b in c["occ"]:
            s = analysis.sentences[sid]
            if not _starts_with(s, a) or len(s.tokens) - b < 4:
                continue
            nxt = s.tokens[b].lower if b < len(s.tokens) else ""
            template = DEF_VERBS.get(nxt, "Explain: %s")
            article = " ".join(t.lower for t in s.tokens[:a])
            phrase = (article + " " + c["phrase"]).strip()
            front = template % phrase
            if front.startswith("Explain"):
                front = "Explain: " + phrase
            cards.append({"id": _card_id(front), "kind": "definition", "concept": c["key"],
                          "front": front, "back": s.text, "answer": phrase,
                          "sentence_id": sid,
                          "highlight": [s.tokens[a].start, s.tokens[b - 1].end]})
            used.add(c["key"])
            break
    # 2) cloze cards for important concepts without a definition
    for c in concepts:
        if len(cards) >= max_cards:
            break
        if c["key"] in used or not c["quizzable"]:
            continue
        best = None
        for sid, a, b in c["occ"]:
            if len(analysis.terms[sid]) < MIN_CONTENT_TERMS:
                continue
            score = analysis.rank["scores"][sid]
            if best is None or score > best[0]:
                best = (score, sid, a, b)
        if not best:
            continue
        _, sid, a, b = best
        s = analysis.sentences[sid]
        start, end = s.tokens[a].start, s.tokens[b - 1].end
        front = s.text[:start] + BLANK + s.text[end:]
        cards.append({"id": _card_id(front), "kind": "cloze", "concept": c["key"],
                      "front": front, "back": s.text, "answer": c["phrase"],
                      "sentence_id": sid, "highlight": [start, end]})
        used.add(c["key"])
    # keep importance order (concept order), cap size
    order = {c["key"]: i for i, c in enumerate(concepts)}
    cards.sort(key=lambda x: order.get(x["concept"], 999))
    return cards[:max_cards]
