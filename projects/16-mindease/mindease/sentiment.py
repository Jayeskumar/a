"""From-scratch, explainable lexicon-based sentiment & emotion analyser.

Pipeline for one journal entry:
1. tokenise (words, contractions, emoticons, emoji) and normalise spellings;
2. merge multi-word expressions ("burnt out", "can't sleep", "vera level") greedily;
3. score each valence unit, then apply rules in order:
   intensifier / diminisher (look back 2 units)  -> |v| +/- 0.293
   negation (look back 3 units, stop at punctuation / "but")  -> v * -0.74
   Tamil post-negation ("nalla illa" = not good)  -> v * -0.74
   ALL-CAPS emphasis -> |v| + 0.733
   contrast: clause before "but" x0.5, after x1.5
4. sum, add "!" emphasis, squash with s / sqrt(s^2 + 15) into a compound in (-1, 1).

Every contribution records the rule(s) that changed it, so the UI can show exactly *why*
the app read an entry the way it did. Output is "what the app noticed", never a diagnosis.
"""

import math
import re

from . import config
from . import lexicon as L

_EMOTICON_RE = "|".join(re.escape(e) for e in sorted(L.EMOTICONS, key=len, reverse=True))
_TOKEN_RE = re.compile(
    r"(?P<emoticon>%s)|(?P<word>[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*)"
    r"|(?P<punct>[.,;:!?]+)|(?P<other>\S)" % _EMOTICON_RE,
    re.IGNORECASE,
)
# Variation selectors, ZWJ and skin-tone modifiers become spaces (not removed), so token
# offsets still match the original text for highlighting in the UI.
_STRIP = dict.fromkeys((0xFE0F, 0x200D), " ")
_STRIP.update(dict.fromkeys(range(0x1F3FB, 0x1F400), " "))  # skin-tone modifiers
_BOUNDARY_PUNCT = set(".;!?,:")
_SENTENCE_END = set(".;!?")
_CONTRAST = {"but", "however"}


def tokenize(text):
    """Return a list of token dicts: raw, norm, kind (word/emoji/emoticon/punct)."""
    text = (text or "").translate(_STRIP).replace("\u2019", "'").replace("\u2018", "'")
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        raw = m.group(0)
        if kind == "word":
            norm = raw.lower()
            norm = L.NORMALISE.get(norm, norm)
        elif kind == "emoticon":
            norm = raw.lower()
        elif kind == "punct":
            norm = raw
        else:
            if raw not in L.EMOJI:
                continue
            kind, norm = "emoji", raw
        tokens.append({"raw": raw, "norm": norm, "kind": kind,
                       "start": m.start(), "end": m.end()})
    return tokens


def _lookup(word):
    """Exact lexicon match, then a light suffix-stripping fallback."""
    if word in L.WORDS:
        return word, L.WORDS[word]
    cands = []
    if len(word) > 4:
        if word.endswith("ily"):
            cands.append(word[:-3] + "y")
        if word.endswith("ly"):
            cands.append(word[:-2])
        if word.endswith("ing"):
            cands += [word[:-3], word[:-3] + "e"]
        if word.endswith("ed"):
            cands += [word[:-2], word[:-1]]
        if word.endswith("es"):
            cands.append(word[:-2])
        if word.endswith("s"):
            cands.append(word[:-1])
    for c in cands:
        if len(c) >= 3 and c in L.WORDS:
            return c, L.WORDS[c]
    return None, None


def _units(tokens):
    """Merge phrases and classify each unit's role."""
    units, i, n = [], 0, len(tokens)
    max_len = 4
    while i < n:
        tok = tokens[i]
        if tok["kind"] == "word":
            matched = None
            for size in range(max_len, 1, -1):
                if i + size > n:
                    continue
                window = tokens[i:i + size]
                if any(t["kind"] != "word" for t in window):
                    continue
                key = tuple(t["norm"] for t in window)
                if key in L.PHRASES or key in L.MODIFIER_PHRASES:
                    matched = (size, key)
                    break
            if matched:
                size, key = matched
                raw = " ".join(t["raw"] for t in tokens[i:i + size])
                unit = {"raw": raw, "norm": " ".join(key), "kind": "phrase",
                        "start": tokens[i]["start"], "end": tokens[i + size - 1]["end"]}
                if key in L.PHRASES:
                    unit["valence"], unit["emotion"] = L.PHRASES[key]
                else:
                    unit["role"] = L.MODIFIER_PHRASES[key]
                units.append(unit)
                i += size
                continue
        units.append(dict(tok))
        i += 1

    for u in units:
        norm, kind = u["norm"], u["kind"]
        u.setdefault("role", None)
        if kind == "punct":
            u["role"] = "boundary" if any(c in _BOUNDARY_PUNCT for c in norm) else None
            u["sentence_end"] = any(c in _SENTENCE_END for c in norm)
            continue
        if kind == "emoji":
            u["valence"], u["emotion"] = L.EMOJI[norm]
            continue
        if kind == "emoticon":
            u["valence"], u["emotion"] = L.EMOTICONS[norm]
            continue
        if kind == "phrase":
            continue
        if norm in _CONTRAST:
            u["role"] = "contrast"
        elif norm in L.NEGATORS:
            u["role"] = "neg"
        elif norm in L.POST_NEGATORS:
            u["role"] = "postneg"
        elif norm in L.DIMINISHERS:
            u["role"] = "dim"
        elif norm in L.INTENSIFIERS and norm not in L.WORDS:
            u["role"] = "int"
        else:
            lemma, entry = _lookup(norm)
            if entry:
                u["valence"], u["emotion"] = entry
                if lemma != norm:
                    u["lemma"] = lemma

    # Dual words ("semma", "super", "too much"): an intensifier if a valence unit follows.
    for idx, u in enumerate(units):
        if u["norm"] in L.DUAL_INTENSIFIERS and idx + 1 < len(units) \
                and units[idx + 1].get("valence"):
            u.pop("valence", None)
            u.pop("emotion", None)
            u["role"] = "int"
    return units


def analyse(text, with_tokens=True):
    """Analyse one entry. Returns compound score, label, emotions and the reasons."""
    tokens = tokenize(text)
    units = _units(tokens)
    all_caps_text = text.isupper() if text else False
    contributions = []

    for idx, u in enumerate(units):
        v = u.get("valence")
        if not v:
            continue
        score, rules = v, []
        # intensifiers / diminishers just before the word
        for dist in (1, 2):
            j = idx - dist
            if j < 0 or units[j].get("role") == "boundary":
                break
            role = units[j].get("role")
            if role in ("int", "dim"):
                delta = (config.INTENSIFIER_BOOST if role == "int"
                         else config.DIMINISHER_DROP) * (1.0 if dist == 1 else 0.95)
                score = math.copysign(max(abs(score) + delta, 0.0), score)
                rules.append(("intensified by" if role == "int" else "softened by",
                              units[j]["raw"]))
                break
        # negation before the word
        for dist in range(1, config.NEGATION_WINDOW + 1):
            j = idx - dist
            if j < 0:
                break
            role = units[j].get("role")
            if role in ("boundary", "contrast"):
                break
            if role == "neg":
                score *= config.NEGATION_SCALAR
                rules.append(("negated by", units[j]["raw"]))
                u["negated"] = True
                break
        # Tamil post-negation after the word ("nalla illa")
        if not u.get("negated"):
            for dist in (1, 2):
                j = idx + dist
                if j >= len(units) or units[j].get("role") in ("boundary", "contrast"):
                    break
                if units[j].get("role") == "postneg":
                    score *= config.NEGATION_SCALAR
                    rules.append(("negated by", units[j]["raw"] + " (Tamil)"))
                    u["negated"] = True
                    break
                if units[j].get("valence"):
                    break
        # emphasis by capitals
        raw = u["raw"]
        if u["kind"] in ("word", "phrase") and raw.isupper() and len(raw) > 1 \
                and not all_caps_text:
            score = math.copysign(abs(score) + config.CAPS_BOOST, score)
            rules.append(("emphasised by", "CAPITALS"))
        u["score"] = score
        u["rules"] = rules
        contributions.append(u)

    # contrast weighting, sentence by sentence
    sentence, sentences = [], []
    for u in units:
        sentence.append(u)
        if u.get("sentence_end"):
            sentences.append(sentence)
            sentence = []
    if sentence:
        sentences.append(sentence)
    contrast_used = False
    for sent in sentences:
        cut = next((i for i, u in enumerate(sent) if u.get("role") == "contrast"), None)
        if cut is None:
            continue
        contrast_used = True
        word = sent[cut]["raw"]
        for i, u in enumerate(sent):
            if "score" not in u:
                continue
            if i < cut:
                u["score"] *= config.BUT_BEFORE_WEIGHT
                u["rules"].append(("down-weighted before", word))
            else:
                u["score"] *= config.BUT_AFTER_WEIGHT
                u["rules"].append(("up-weighted after", word))

    total = sum(u["score"] for u in contributions)
    exclaims = min((text or "").count("!"), 3)
    emphasis = 0.0
    if exclaims and total:
        emphasis = math.copysign(exclaims * config.EXCLAIM_BOOST, total)
        total += emphasis
    compound = total / math.sqrt(total * total + config.NORMALISE_ALPHA) if total else 0.0
    compound = max(-1.0, min(1.0, compound))
    if compound >= config.POSITIVE_THRESHOLD:
        label = "positive"
    elif compound <= config.NEGATIVE_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    # VADER-style proportions over all content units
    pos = sum(u["score"] + 1 for u in contributions if u["score"] > 0)
    neg = sum(abs(u["score"]) + 1 for u in contributions if u["score"] < 0)
    neu = sum(1 for u in units if u["kind"] in ("word", "phrase", "emoji", "emoticon")
              and "score" not in u and u.get("role") is None)
    denom = pos + neg + neu or 1.0

    emotions = {}
    for u in contributions:
        emo = u.get("emotion")
        if not emo or u.get("negated"):
            continue
        e = emotions.setdefault(emo, {"emotion": emo, "label": L.EMOTION_LABELS[emo],
                                      "score": 0.0, "words": []})
        e["score"] += abs(u["score"])
        if u["raw"] not in e["words"]:
            e["words"].append(u["raw"])
    emo_total = sum(e["score"] for e in emotions.values()) or 1.0
    emo_list = sorted(emotions.values(), key=lambda e: -e["score"])
    for e in emo_list:
        e["share"] = round(e["score"] / emo_total, 3)
        e["score"] = round(e["score"], 3)

    tanglish = sorted({u["norm"] for u in units if u["norm"] in L.TANGLISH})
    result = {
        "compound": round(compound, 3),
        "label": label,
        "proportions": {"pos": round(pos / denom, 3), "neg": round(neg / denom, 3),
                        "neu": round(neu / denom, 3)},
        "emotions": emo_list,
        "rules_fired": _rules_summary(contributions, contrast_used, exclaims, tanglish),
        "summary": _summary(label, compound, emo_list),
        "word_count": sum(1 for t in tokens if t["kind"] == "word"),
    }
    if with_tokens:
        result["tokens"] = [
            {"text": u["raw"], "start": u["start"], "end": u["end"],
             "base": round(u["valence"], 2), "score": round(u["score"], 3),
             "emotion": u.get("emotion"), "negated": bool(u.get("negated")),
             "rules": ["%s '%s'" % r for r in u["rules"]]}
            for u in contributions
        ]
        result["exclamation_boost"] = round(emphasis, 3)
    return result


def _rules_summary(contribs, contrast_used, exclaims, tanglish):
    fired = []
    negs = [u["raw"] for u in contribs if u.get("negated")]
    if negs:
        fired.append("Negation flipped: " + ", ".join("'%s'" % w for w in negs))
    ints = [u["raw"] for u in contribs
            if any(r[0] in ("intensified by", "softened by") for r in u["rules"])]
    if ints:
        fired.append("Intensity adjusted: " + ", ".join("'%s'" % w for w in ints))
    if contrast_used:
        fired.append("Contrast: the part after 'but' counts more")
    emo = [u["raw"] for u in contribs if u["kind"] in ("emoji", "emoticon")]
    if emo:
        fired.append("Emoji read: " + " ".join(emo))
    if exclaims:
        fired.append("Exclamation marks add emphasis")
    if tanglish:
        fired.append("Tanglish words understood: " + ", ".join(tanglish))
    return fired


def _summary(label, compound, emotions):
    top = [e["label"] for e in emotions[:2]]
    if label == "neutral":
        base = "The entry reads fairly neutral"
    elif label == "positive":
        base = "The entry reads mostly positive" if compound < 0.6 else \
            "The entry reads clearly positive"
    else:
        base = "The entry sounds a bit heavy" if compound > -0.6 else \
            "The entry sounds quite heavy"
    if top:
        base += ", with hints of " + " and ".join(top)
    return base + "."


def baseline_label(text):
    """Ablation baseline: plain word counting with the same lexicon and no rules."""
    total = 0.0
    for t in tokenize(text):
        if t["kind"] == "emoji":
            total += L.EMOJI[t["norm"]][0]
        elif t["kind"] == "emoticon":
            total += L.EMOTICONS[t["norm"]][0]
        elif t["kind"] == "word":
            _, entry = _lookup(t["norm"])
            if entry:
                total += entry[0]
    compound = total / math.sqrt(total * total + config.NORMALISE_ALPHA) if total else 0.0
    if compound >= config.POSITIVE_THRESHOLD:
        return "positive"
    if compound <= config.NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"
