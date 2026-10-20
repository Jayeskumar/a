"""Detects concerning language (self-harm, death wishes, hopelessness) in journal text.

Design choices (safety first, but no panic):
* Patterns are specific multi-word phrases ("kill myself", "no reason to live"), so
  everyday hyperbole like "this exam is killing me" or "dead tired" does NOT match.
* Recall matters more than precision: a false alarm costs the student one gentle screen
  they can close; a miss costs much more. So negated self-harm mentions still trigger
  (at the softer "concern" level), and only single-word hopelessness terms are
  suppressed when negated ("I'm not hopeless, just tired").
* Mentions about someone else ("she wants to kill herself") trigger a "worried about a
  friend" support screen with peer-support guidance.
* Matching runs on the original text (lower-cased, same length), so the UI can highlight
  exactly which words were noticed.

This is a keyword safety net, not a risk assessment. It never diagnoses or scores risk.
"""

import re

A = r"'?"  # optional apostrophe, so "cant" and "can't" both match

# (rule id, category, level, regex, human description)
_RULES = [
    # --- self-harm & death-wish language -> "urgent" -----------------------------
    ("harm_self", "self_harm", "urgent",
     r"\b(kill(ing|ed)?|hurt(ing)?|harm(ing|ed)?|cut(ting)?|injur(e|ing|ed)|unaliv(e|ing))"
     r"\s+my\s?self\b", "harming oneself"),
    ("kms", "self_harm", "urgent", r"\bkms\b", "'kms' (slang for kill myself)"),
    ("self_harm_word", "self_harm", "urgent", r"\bself[\s-]?harm(ing)?\b", "self-harm"),
    ("suicide", "self_harm", "urgent",
     r"\bsuicid(e|al)\b(?!\s+(prevention|awareness|helpline|squad))", "suicide"),
    ("end_life", "self_harm", "urgent",
     r"\b(end(ing)?|tak(e|ing))\s+(my|my\s+own)\s+life\b", "ending one's life"),
    ("end_it_all", "self_harm", "urgent",
     r"\b(end(ing)?\s+it\s+all|end\s+everything)\b", "ending it all"),
    ("want_die", "self_harm", "urgent",
     r"\b(want|wants|wanted|wanna|wish|wishes|going|planning|plan|ready|deserve)\s+(to\s+)?die\b"
     r"(?!\s+(of|from|laughing|for))", "wanting to die"),
    ("wish_dead", "self_harm", "urgent",
     r"\bwish\s+i\s+(was|were)\s+(dead|never\s+born)\b|\bwish\s+i\s+(was|were)n" + A +
     r"t\s+(alive|born|here)\b|\bwish\s+i\s+had\s+never\s+been\s+born\b",
     "wishing to be dead"),
    ("better_off", "self_harm", "urgent",
     r"\bbetter\s+off\s+(dead|without\s+me|if\s+i\s+(was|were)\s+(gone|dead)|if\s+i\s+"
     r"(was|were)n" + A + r"t\s+(here|around|alive))\b", "others being better off without me"),
    ("not_live", "self_harm", "urgent",
     r"\b(don" + A + r"t|do\s+not|no\s+longer|never)\s+want\s+to\s+(live|be\s+alive|exist|"
     r"wake\s+up|be\s+here\s+anymore)\b", "not wanting to live"),
    ("no_reason_live", "self_harm", "urgent",
     r"\b(no|not\s+any|nothing\s+to)\s+(reason|reasons)\s+to\s+(live|go\s+on)\b|"
     r"\bnot\s+worth\s+living\b|\bpoint\s+(of|in)\s+(living|being\s+alive)\b|"
     r"\bpointless\s+to\s+live\b", "no reason to live"),
    ("never_wake", "self_harm", "urgent",
     r"\b(sleep|close\s+my\s+eyes)\s+and\s+never\s+wake\s+up\b|\bnever\s+wake\s+up\s+again\b",
     "wishing not to wake up"),
    ("overdose", "self_harm", "urgent", r"\boverdos(e|ing)\b", "overdose"),
    ("jump_off", "self_harm", "urgent",
     r"\bjump\s+(off|from)\s+(a|the|my)\s+(building|bridge|terrace|roof|hostel)\b",
     "jumping from a height"),
    ("disappear", "self_harm", "urgent",
     r"\b(disappear(ing)?|vanish(ing)?)\s+(forever|for\s+good|from\s+(this|the)\s+world)\b",
     "disappearing forever"),
    ("not_around", "self_harm", "urgent",
     r"\b(won" + A + r"t|will\s+not)\s+be\s+(here|around)\s+(much\s+longer|anymore|tomorrow)\b",
     "not being around anymore"),
    ("tanglish_die", "self_harm", "urgent",
     r"\bsaa?g(a|ah)?(num|noum|nu|poren|poran)\b|\bsaa?ga\s+(poren|poran|ponum|poganum)\b|"
     r"\bseth?thu\s+(poga\w*|poi\w*|poy\w*)\b|\bsethud(a|u)l?am\b|\bsethuruven\b",
     "wanting to die (Tamil)"),
    ("tanglish_live", "self_harm", "urgent",
     r"\bvaazh(a|ave|avae|ave)\s+pidi(kk|k)?ala\b|\buyir(oda)?\s+irukk?a\s+pidi(kk|k)?ala\b",
     "not wanting to live (Tamil)"),
    ("others_better", "self_harm", "urgent",
     r"\b(everyone|everybody|they|my\s+(family|parents))\s+(would|will)\s+be\s+better\s+off\b",
     "others being better off without me"),
    ("goodbye_note", "self_harm", "urgent",
     r"\b(goodbye|good-bye|farewell|suicide)\s+(letter|note|message)s?\b",
     "writing a goodbye note (warning sign)"),
    ("giving_away", "self_harm", "urgent",
     r"\bgiv(e|ing|en)\s+away\s+(all\s+)?(my|of\s+my)\s+(things|stuff|belongings|possessions)\b",
     "giving away belongings (warning sign)"),
    ("pills", "self_harm", "urgent",
     r"\b(took|take|taking|swallowed|have\s+taken)\s+(extra|too\s+many|lots\s+of|a\s+lot\s+of|"
     r"all\s+the|a\s+bunch\s+of)\s+(sleeping\s+)?(pills|tablets)\b",
     "taking extra pills (warning sign)"),
    # --- someone else -----------------------------------------------------------------
    ("harm_other_self", "someone_else", "concern",
     r"\b(kill(ing|ed)?|hurt(ing)?|harm(ing)?|cut(ting)?)\s+(him|her|them)sel(f|ves)\b",
     "someone else harming themselves"),
    # --- hopelessness -> "concern" -------------------------------------------------------
    ("hopeless", "hopelessness", "concern", r"\bhopeless(ness)?\b(?!\s+at\b)", "hopelessness"),
    ("no_hope", "hopelessness", "concern",
     r"\bno\s+hope\b|\blost\s+(all\s+)?hope\b|\bgiv(e|en|ing)\s+up\s+(all\s+)?hope\b",
     "losing hope"),
    ("never_better", "hopelessness", "concern",
     r"\bnothing\s+(will|would|is\s+going\s+to|is\s+ever\s+going\s+to)\s+(ever\s+)?(get|be|feel)"
     r"\s+better\b|\b(it|things|life)\s*(" + A + r"s|\s+is|\s+are|\s+will)?\s+never\s+"
     r"(going\s+to\s+)?(get|be)\s+better\b", "believing nothing will get better"),
    ("whats_point", "hopelessness", "concern",
     r"\bwhat" + A + r"?s\s+the\s+point\b(?!\s+of\s+(this|that|the|these|studying|doing)\b)|"
     r"\bwhat\s+is\s+the\s+point\b(?!\s+of\s+(this|that|the|these|studying|doing)\b)",
     "asking what the point is"),
    ("no_point", "hopelessness", "concern",
     r"\b(no|there" + A + r"s\s+no|there\s+is\s+no)\s+point\s+(in\s+)?(anything|living|trying|"
     r"going\s+on|life|carrying\s+on|any\s+of\s+this|in\s+anything)\b", "seeing no point"),
    ("cant_go_on", "hopelessness", "concern",
     r"\bcan(" + A + r"t|not|\s+not)\s+(go\s+on|carry\s+on|keep\s+going)\b|"
     r"\bcan(" + A + r"t|not|\s+not)\s+(take|handle|bear|do)\s+(it|this)\s+any\s?more\b",
     "not being able to go on"),
    ("give_up_life", "hopelessness", "concern",
     r"\b(give|giving|gave|given)\s+up\s+on\s+(everything|life|myself|living)\b",
     "giving up on everything"),
    ("burden", "hopelessness", "concern",
     r"\b(i" + A + r"m|i\s+am|feel\s+like)\s+(just\s+|such\s+|only\s+)?a\s+burden\b|"
     r"\bburden\s+(to|on|for)\s+(everyone|my\s+family|my\s+parents|others|people)\b",
     "feeling like a burden"),
    ("no_way_out", "hopelessness", "concern",
     r"\bno\s+way\s+out\b|\b(feel|feeling|felt)\s+(so\s+)?trapped\b", "feeling trapped"),
    ("worthless", "hopelessness", "concern", r"\bworthless\b", "feeling worthless"),
    ("nobody_notice", "hopelessness", "concern",
     r"\b(nobody|no\s+one|no-one)\s+(would|will)\s+(even\s+)?(care|miss\s+me|notice)\b|"
     r"\bwouldn" + A + r"t\s+(even\s+)?(notice|care)\s+if\s+i\s+(was|were)\s+gone\b",
     "feeling nobody would notice"),
    ("life_pointless", "hopelessness", "concern",
     r"\blife\s+(is|feels|seems)\s+(so\s+|completely\s+|totally\s+)?(pointless|meaningless|"
     r"empty|hopeless|worthless)\b", "life feeling pointless"),
    ("dead_inside", "hopelessness", "concern", r"\bdead\s+inside\b", "feeling dead inside"),
    ("nothing_matters", "hopelessness", "concern",
     r"\bnothing\s+matters(\s+any\s?more)?\b", "feeling nothing matters"),
    ("done_with_life", "hopelessness", "concern",
     r"\bdone\s+with\s+(life|living|everything|it\s+all)\b", "being done with life"),
    ("no_meaning", "hopelessness", "concern",
     r"\b(life|it)\s+(has|holds)\s+no\s+(meaning|purpose|point)\b|"
     r"\blife\s+is\s+(a\s+)?(waste|meaningless|pointless)\b", "life feeling meaningless"),
    ("no_way_better", "hopelessness", "concern",
     r"\b(can" + A + r"t|cannot|don" + A + r"t)\s+see\s+(any|a)\s+(way\s+out|way\s+(this|it|things)"
     r"\s+(gets?|will\s+get|could\s+get)\s+better|future|point)\b", "seeing no way forward"),
    ("tanglish_over", "hopelessness", "concern",
     r"\bellam(e)?\s+mudi\w*\b|\bvaazhkai(ye)?\s+(waste|veenu|mudinjiduchu|veruthu\s+\w+)\b",
     "everything feels over (Tamil)"),
]
RULES = [(rid, cat, lvl, re.compile(rx), desc) for rid, cat, lvl, rx, desc in _RULES]

# Single-word hopelessness terms are dropped if negated just before ("not hopeless").
_NEGATABLE = {"hopeless", "worthless"}
_NEG_BEFORE = re.compile(r"\b(not|never|no|isn" + A + r"t|wasn" + A + r"t|am\s+not|"
                         r"i" + A + r"m\s+not)\s+(\w+\s+)?$")
_OTHER_BEFORE = re.compile(r"\b(he|she|they|my\s+(friend|roommate|room-mate|brother|sister|"
                           r"classmate|cousin)|someone|somebody)\b[^.!?]{0,40}$")

# --- Co-occurrence layer -------------------------------------------------------------
# Fixed phrases miss indirect wording ("I'm tired of being alive"). This layer flags a
# sentence that has all three cues: first person + a death/absence cue + a wish/hopeless
# cue, and none of the everyday-context guards ("battery", "lol", "a good book").
_FIRST_PERSON = re.compile(r"\b(i|i" + A + r"m|im|i" + A + r"ve|i" + A + r"d|me|my|myself)\b")
_D_STRONG = re.compile(
    r"\b(die|died|dying|dead|death|alive|exist|existing|existence|born|kill|end\s+it|"
    r"end\s+(this|everything)|pills)\b")
_D_SOFT = re.compile(
    r"\b(disappear\w*|vanish\w*|forever|permanently|future|gone|"
    r"(was|were)n" + A + r"t\s+(around|here)|not\s+(be\s+)?(around|here)|keep\s+living|"
    r"go\s+on\s+living)\b")
_WISH = re.compile(
    r"\b(want|wanna|wish|wished|should|tired\s+of|sick\s+of|done\s+with|easier|better\s+off|"
    r"ways?\s+to|how\s+to|plan(ning)?\s+to|can" + A + r"t\s+(keep|see|go)|cannot\s+(keep|see|go)|"
    r"don" + A + r"t\s+(see|think\s+i\s+can)|no\s+(point|future|reason|meaning)|"
    r"never\s+(wake|come\s+back)|stop\s+existing|just\s+end)\b")
_GUARD = re.compile(
    r"\b(laugh\w*|lol|haha\w*|lmao|book|movie|film|show|series|game|match|battery|phone|"
    r"laptop|charger|plant|semester|holidays?|vacation|trip|exam\s+week|joke|kidding)\b")
_SENT_SPLIT = re.compile(r"[.!?;\n]+")


def _cooccurrence(low, taken):
    out = []
    pos = 0
    for part in _SENT_SPLIT.split(low):
        start = low.find(part, pos)
        end = start + len(part)
        pos = end
        if not part.strip() or any(s < end and start < e for s, e in taken):
            continue
        if not _FIRST_PERSON.search(part) or _GUARD.search(part):
            continue
        strong, soft, wish = _D_STRONG.search(part), _D_SOFT.search(part), _WISH.search(part)
        death = strong or soft
        if not (death and wish):
            continue
        lo = start + min(death.start(), wish.start())
        hi = start + max(death.end(), wish.end())
        out.append((lo, hi, "urgent" if strong else "concern",
                    "'%s' together with '%s'" % (wish.group(0), death.group(0))))
    return out


MESSAGES = {
    "urgent": "It sounds like you might be going through something really painful right "
              "now. You don't have to face it alone. Support is available right now.",
    "concern": "Some of what you wrote sounds really heavy. It's okay to not be okay, and "
               "talking to someone can help.",
    "someone_else": "It sounds like you're worried about someone. Here's how you can help, "
                    "and who you can call together.",
}


def detect(text, cooccurrence=True):
    """Return {"flagged", "level", "category", "matches", "message"} for a text.

    cooccurrence=False disables the second layer (used only for the ablation in
    evaluation.py)."""
    original = text or ""
    low = original.lower().replace("’", "'").replace("‘", "'")
    matches = []
    taken = []
    for rid, cat, lvl, rx, desc in RULES:
        for m in rx.finditer(low):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in taken):
                continue  # already covered by an earlier (more serious) rule
            before = low[max(0, m.start() - 40):m.start()]
            negated = bool(_NEG_BEFORE.search(before))
            if negated and m.group(0).strip() in _NEGATABLE:
                continue
            about_other = cat != "someone_else" and bool(_OTHER_BEFORE.search(before)) \
                and not re.search(r"\b(i|me|my|myself)\b", m.group(0))
            category, level = cat, lvl
            if about_other:
                category, level = "someone_else", "concern"
            elif negated and lvl == "urgent":
                level = "concern"  # "I would never kill myself": still check in, gently
            taken.append(span)
            matches.append({
                "rule": rid, "category": category, "level": level, "description": desc,
                "phrase": original[span[0]:span[1]], "start": span[0], "end": span[1],
                "negated": negated, "about_other": about_other,
            })
    for lo, hi, level, why in (_cooccurrence(low, taken) if cooccurrence else []):
        before = low[max(0, lo - 40):lo]
        about_other = bool(_OTHER_BEFORE.search(before)) and \
            not _FIRST_PERSON.search(low[lo:hi])
        matches.append({
            "rule": "cooccurrence", "category": "someone_else" if about_other else
            ("self_harm" if level == "urgent" else "hopelessness"),
            "level": "concern" if about_other else level,
            "description": "wish/hopeless cue near a death or absence cue (" + why + ")",
            "phrase": original[lo:hi], "start": lo, "end": hi,
            "negated": False, "about_other": about_other,
        })
    matches.sort(key=lambda x: x["start"])
    if not matches:
        return {"flagged": False, "level": None, "category": None, "matches": [],
                "message": None}
    level = "urgent" if any(x["level"] == "urgent" for x in matches) else "concern"
    own = [x for x in matches if x["category"] != "someone_else"]
    if not own:
        category = "someone_else"
    elif any(x["category"] == "self_harm" for x in own):
        category = "self_harm"
    else:
        category = "hopelessness"
    message = MESSAGES["someone_else"] if category == "someone_else" else MESSAGES[level]
    return {"flagged": True, "level": level, "category": category, "matches": matches,
            "message": message}
