"""PHQ-9 and GAD-7: standard item wording, 0-3 scoring, published severity bands.

PHQ-9 (Kroenke, Spitzer & Williams, J Gen Intern Med 2001) and GAD-7 (Spitzer, Kroenke,
Williams & Lowe, Arch Intern Med 2006) were developed by Drs. Spitzer, Williams, Kroenke
and colleagues with an educational grant from Pfizer Inc.; no permission is required to
reproduce, translate, display or distribute them.

These are *screening* questionnaires. A score describes how often symptoms bothered the
person over the last two weeks; it is not a diagnosis.

Safety rule: if PHQ-9 item 9 ("thoughts that you would be better off dead or of hurting
yourself") is answered above 0, a gentle support screen is shown immediately, regardless
of the total score.
"""

from . import config

OPTIONS = [
    {"value": 0, "label": "Not at all"},
    {"value": 1, "label": "Several days"},
    {"value": 2, "label": "More than half the days"},
    {"value": 3, "label": "Nearly every day"},
]

DIFFICULTY_OPTIONS = ["Not difficult at all", "Somewhat difficult", "Very difficult",
                      "Extremely difficult"]

PHQ9_ITEMS = [
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble falling or staying asleep, or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself — or that you are a failure or have let yourself "
    "or your family down",
    "Trouble concentrating on things, such as reading the newspaper or watching television",
    "Moving or speaking so slowly that other people could have noticed? Or the opposite "
    "— being so fidgety or restless that you have been moving around a lot more "
    "than usual",
    "Thoughts that you would be better off dead or of hurting yourself in some way",
]

GAD7_ITEMS = [
    "Feeling nervous, anxious or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it is hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid as if something awful might happen",
]

# Short tags used in explanations and the counsellor view (never shown as a diagnosis).
PHQ9_TAGS = ["interest", "low mood", "sleep", "energy", "appetite", "self-worth",
             "concentration", "slowed / restless", "thoughts of self-harm"]
GAD7_TAGS = ["nervous", "uncontrollable worry", "worrying a lot", "trouble relaxing",
             "restless", "irritable", "afraid"]

BAND_LABELS = {
    "minimal": "Minimal",
    "mild": "Mild",
    "moderate": "Moderate",
    "moderately_severe": "Moderately severe",
    "severe": "Severe",
}

# Gentle, non-clinical wording for each band. "symptoms" deliberately, never "you have".
PHQ9_MESSAGES = {
    "minimal": "Your answers are in the minimal range. It sounds like low mood hasn't been "
               "getting in your way much lately. Keep doing what helps you.",
    "mild": "Your answers are in the mild range. Some things have been weighing on you. "
            "Small steps like regular sleep, movement and talking to someone you trust "
            "can help. Checking in again in two weeks is a good idea.",
    "moderate": "Your answers are in the moderate range. That's a lot to carry, and you "
                "don't have to carry it alone. Talking with a counsellor could really help.",
    "moderately_severe": "Your answers are in the moderately severe range. These feelings "
                         "seem to be affecting you quite a bit. Please consider talking "
                         "to a counsellor or doctor this week. Reaching out is a strong step.",
    "severe": "Your answers are in the severe range. You've been going through a lot. "
              "Please reach out to a counsellor or doctor soon. If things feel too much "
              "right now, Tele-MANAS (14416) is free and open 24x7.",
}
GAD7_MESSAGES = {
    "minimal": "Your answers are in the minimal range for worry and anxiety. Nice. Keep "
               "using whatever helps you stay steady.",
    "mild": "Your answers are in the mild range. Some worry is normal, especially around "
            "exams. Breathing exercises and a realistic study plan can take the edge off.",
    "moderate": "Your answers are in the moderate range. Worry seems to be taking up a lot "
                "of space. A counsellor can teach skills that make this easier.",
    "severe": "Your answers are in the severe range. Anxiety seems to be affecting you a "
              "lot. Please consider talking to a counsellor or doctor soon. You deserve "
              "support with this.",
}

INSTRUMENTS = {
    "phq9": {
        "id": "phq9",
        "name": "PHQ-9",
        "title": "Mood check-in (PHQ-9)",
        "stem": "Over the last 2 weeks, how often have you been bothered by any of the "
                "following problems?",
        "items": PHQ9_ITEMS,
        "tags": PHQ9_TAGS,
        "bands": config.PHQ9_BANDS,
        "max": 27,
        "messages": PHQ9_MESSAGES,
        "source": "Kroenke, Spitzer & Williams, J Gen Intern Med 2001",
    },
    "gad7": {
        "id": "gad7",
        "name": "GAD-7",
        "title": "Worry check-in (GAD-7)",
        "stem": "Over the last 2 weeks, how often have you been bothered by the following "
                "problems?",
        "items": GAD7_ITEMS,
        "tags": GAD7_TAGS,
        "bands": config.GAD7_BANDS,
        "max": 21,
        "messages": GAD7_MESSAGES,
        "source": "Spitzer, Kroenke, Williams & Lowe, Arch Intern Med 2006",
    },
}

ITEM9_INDEX = 8  # zero-based index of PHQ-9 item 9


def band_for(instrument, total):
    """Return the band id for a total score. Raises ValueError outside the valid range."""
    inst = INSTRUMENTS[instrument]
    for lo, hi, band in inst["bands"]:
        if lo <= total <= hi:
            return band
    raise ValueError("total %r outside 0..%d" % (total, inst["max"]))


def validate(instrument, answers):
    """Return (clean_answers, errors). Answers must be a list of ints 0..3, one per item."""
    if instrument not in INSTRUMENTS:
        return None, {"instrument": "must be 'phq9' or 'gad7'"}
    n = len(INSTRUMENTS[instrument]["items"])
    if not isinstance(answers, list):
        return None, {"answers": "must be a list of %d numbers (0-3)" % n}
    if len(answers) != n:
        return None, {"answers": "expected %d answers, got %d" % (n, len(answers))}
    clean, errors = [], {}
    for i, a in enumerate(answers):
        if isinstance(a, bool) or not isinstance(a, (int, float)) or a != int(a) \
                or not 0 <= a <= 3:
            errors["answers[%d]" % i] = "must be 0, 1, 2 or 3"
        else:
            clean.append(int(a))
    return (clean, None) if not errors else (None, errors)


def item9_positive(answers):
    """The PHQ-9 safety rule: any answer above 0 on item 9."""
    return len(answers) > ITEM9_INDEX and answers[ITEM9_INDEX] > 0


def score(instrument, answers, difficulty=None):
    """Score a validated answer list. Returns a JSON-friendly, explainable result."""
    clean, errors = validate(instrument, answers)
    if errors:
        raise ValueError(errors)
    inst = INSTRUMENTS[instrument]
    total = sum(clean)
    band = band_for(instrument, total)
    lo, hi = next((lo, hi) for lo, hi, b in inst["bands"] if b == band)
    breakdown = [
        {"item": i + 1, "text": inst["items"][i], "tag": inst["tags"][i], "answer": a,
         "answer_label": OPTIONS[a]["label"], "points": a}
        for i, a in enumerate(clean)
    ]
    top = sorted((b for b in breakdown if b["points"] > 0), key=lambda b: -b["points"])[:3]
    support = item9_positive(clean) if instrument == "phq9" else False
    explain = [
        "Each answer scores 0 (not at all) to 3 (nearly every day); total %d of %d."
        % (total, inst["max"]),
        "%s band covers scores %d–%d (%s)." % (BAND_LABELS[band], lo, hi,
                                                  inst["source"]),
    ]
    if top:
        explain.append("Biggest contributors: " + ", ".join(
            "%s (%d)" % (t["tag"], t["points"]) for t in top) + ".")
    if support:
        explain.append("Item 9 was answered above 0, so the support screen is shown "
                       "straight away, whatever the total score.")
    result = {
        "instrument": instrument,
        "name": inst["name"],
        "answers": clean,
        "total": total,
        "max": inst["max"],
        "band": band,
        "band_label": BAND_LABELS[band],
        "band_range": [lo, hi],
        "message": inst["messages"][band],
        "suggest_counsellor": total >= config.REFER_CUTOFF or support,
        "breakdown": breakdown,
        "explain": explain,
        "support": {
            "show": support,
            "reason": "item9" if support else None,
        },
        "disclaimer": "This is a screening check, not a diagnosis. Only a qualified "
                      "professional can diagnose.",
    }
    if instrument == "phq9" and difficulty is not None:
        if isinstance(difficulty, int) and not isinstance(difficulty, bool) \
                and 0 <= difficulty < len(DIFFICULTY_OPTIONS):
            result["difficulty"] = DIFFICULTY_OPTIONS[difficulty]
    return result


def definitions():
    """Questionnaire definitions for the front end."""
    out = {}
    for key, inst in INSTRUMENTS.items():
        out[key] = {
            "id": key, "name": inst["name"], "title": inst["title"], "stem": inst["stem"],
            "items": inst["items"], "options": OPTIONS, "max": inst["max"],
            "bands": [{"band": b, "label": BAND_LABELS[b], "min": lo, "max": hi}
                      for lo, hi, b in inst["bands"]],
            "source": inst["source"],
        }
    out["phq9"]["difficulty"] = {
        "question": "If you checked off any problems, how difficult have these problems "
                    "made it for you to do your work, take care of things at home, or "
                    "get along with other people?",
        "options": DIFFICULTY_OPTIONS,
    }
    out["phq9"]["item9_index"] = ITEM9_INDEX
    return out
