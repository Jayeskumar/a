"""'Prepare to talk to someone': turns a few taps into words the student can say or show.

Template-based and deterministic, so nothing the student types leaves the device and the
output is predictable. If the student says they have had thoughts of hurting themselves,
the script includes a clear, safe sentence for that and the support screen is shown.
"""

AUDIENCES = {
    "friend": "a friend",
    "parent": "a parent or family member",
    "counsellor": "a college counsellor",
    "mentor": "a teacher or class mentor",
    "doctor": "a doctor",
}
FEELINGS = {
    "stressed": "stressed", "anxious": "anxious and on edge", "low": "low",
    "tired": "tired all the time", "lonely": "lonely", "overwhelmed": "overwhelmed",
    "irritable": "irritable", "numb": "numb, like I don't feel much",
    "not_myself": "not like myself", "hopeless": "hopeless",
    "thoughts_harm": "thoughts_harm",
}
DURATIONS = {
    "few_days": "the past few days", "two_weeks": "the last couple of weeks",
    "month": "about a month", "longer": "longer than a month",
}
CAUSES = {
    "exams": "exams and marks", "sleep": "not sleeping well", "family": "things at home",
    "friends": "friendships or relationships", "money": "money worries",
    "future": "worrying about my future and placements", "health": "my health",
    "homesick": "being away from home", "unknown": None,
}
IMPACTS = {
    "sleep": "sleep", "studies": "studies", "eating": "eating", "enjoyment":
    "enjoying things I usually like", "motivation": "motivation", "friends": "friendships",
}
NEEDS = {
    "listen": "I don't need you to fix it. It would really help if you could just listen.",
    "advice": "I'd really value your advice on what I could do next.",
    "study_help": "Could you help me work out how to manage my studies and deadlines?",
    "professional": "I think talking to a counsellor or doctor might help. Could you help "
                    "me take that step?",
    "check_in": "Could you check in on me over the next few days?",
    "company": "Could we spend a bit more time together, even just studying side by side?",
}

OPENERS = {
    "friend": "Hey{name}, do you have a few minutes? There's something I've been wanting "
              "to talk to you about.",
    "parent": "{name_or_amma}, can we talk for a bit? There's something I want to share, "
              "and it's a little hard to say.",
    "counsellor": "Hi{name}, thank you for making time. I wasn't sure where to start, so "
                  "I wrote a few things down.",
    "mentor": "{name_or_sir}, could I speak with you for a few minutes? It's about how "
              "I've been coping lately.",
    "doctor": "Hi{name}, I've come because I haven't been feeling like myself, and I "
              "wrote down what's been happening.",
}
CLOSERS = {
    "friend": "Thanks for listening. It honestly means a lot.",
    "parent": "I'm telling you because I trust you, and I don't want to handle this alone.",
    "counsellor": "What do you think could help?",
    "mentor": "Thank you for listening. I wanted you to know what's been going on.",
    "doctor": "What do you think could help?",
}
SHORT = {
    "friend": "Hey, are you free to talk sometime today? Nothing urgent, I could just use "
              "a friend right now.",
    "parent": "Can we talk tonight? I've been having a tough time and I'd like to share it "
              "with you.",
    "counsellor": "Hello, I'm a student and I'd like to book a time to talk with a "
                  "counsellor about {topic}. When would be a good time?",
    "mentor": "Good evening, could I meet you for ten minutes this week? I'd like to talk "
              "about how I'm managing {topic}.",
    "doctor": "Hello, I'd like to book an appointment. I've been feeling {feeling} for "
              "{duration} and would like some advice.",
}
TIPS = {
    "friend": ["Pick a calm moment, maybe over tea or a walk.",
               "It's okay to say \"this is hard to say\" first."],
    "parent": ["Choose a quiet time when nobody is rushing.",
               "If they worry about marks first, gently say: \"I want to talk about how I "
               "feel, not just the marks.\""],
    "counsellor": ["Counsellors hear this every day; you're not wasting their time.",
                   "You can read straight from your phone."],
    "mentor": ["Ask if there is a private place to talk.",
               "You only need to share what you're comfortable with."],
    "doctor": ["Mention how long it's been and how it affects sleep, food and study.",
               "Bring this note; it's fine to read it out."],
}
COMMON_TIPS = [
    "If the first person doesn't respond well, try someone else. You deserve to be heard.",
    "Reaching out is a strength, not a weakness.",
]


def _join(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _pick(values, allowed, field, errors, required=False):
    if values is None:
        values = []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or any(v not in allowed for v in values):
        errors[field] = "choose from: " + ", ".join(allowed)
        return []
    if required and not values:
        errors[field] = "choose at least one"
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def generate(body):
    errors = {}
    audience = body.get("audience", "friend")
    if audience not in AUDIENCES:
        errors["audience"] = "choose from: " + ", ".join(AUDIENCES)
    feelings = _pick(body.get("feelings"), FEELINGS, "feelings", errors, required=True)
    duration = body.get("duration", "two_weeks")
    if duration not in DURATIONS:
        errors["duration"] = "choose from: " + ", ".join(DURATIONS)
    causes = _pick(body.get("causes"), CAUSES, "causes", errors)
    impacts = _pick(body.get("impacts"), IMPACTS, "impacts", errors)
    needs = _pick(body.get("needs"), NEEDS, "needs", errors)
    name = body.get("name") or ""
    note = body.get("note") or ""
    if not isinstance(name, str) or len(name) > 30:
        errors["name"] = "up to 30 characters"
    if not isinstance(note, str) or len(note) > 300:
        errors["note"] = "up to 300 characters"
    if errors:
        raise ValueError(errors)
    name = " ".join(name.split())
    note = " ".join(note.split())

    harm = "thoughts_harm" in feelings
    feel_words = [FEELINGS[f] for f in feelings if f != "thoughts_harm"]
    opener = OPENERS[audience].format(
        name=(" " + name) if name else "",
        name_or_amma=name or "Amma / Appa",
        name_or_sir=name or "Sir / Ma'am")
    body_lines = []
    if feel_words:
        body_lines.append("For %s, I've been feeling %s." % (DURATIONS[duration],
                                                              _join(feel_words)))
    named = [CAUSES[c] for c in causes if CAUSES[c]]
    if named:
        body_lines.append("I think a lot of it is about %s." % _join(named))
    if "unknown" in causes or not causes:
        body_lines.append("I'm not completely sure why, and that's part of what makes it "
                          "hard." if not named else
                          "Part of it I can't fully explain yet.")
    if impacts:
        body_lines.append("It's been affecting my %s." % _join([IMPACTS[i] for i in impacts]))
    if harm:
        body_lines.append("Sometimes I've had thoughts of hurting myself or not wanting to "
                          "be here, and that scares me. I want to stay safe, and I need "
                          "help with this.")
    if note:
        body_lines.append("One thing I really want you to know: " + note.rstrip(".") + ".")
    asks = [NEEDS[n] for n in needs]
    if harm and "professional" not in needs:
        asks.append(NEEDS["professional"])
    closer = CLOSERS[audience]
    full = "\n\n".join([opener, " ".join(body_lines), " ".join(asks), closer]).strip()
    while "\n\n\n" in full:
        full = full.replace("\n\n\n", "\n\n")
    short = SHORT[audience].format(
        topic=named[0] if named else "how I've been feeling",
        feeling=feel_words[0] if feel_words else "low",
        duration=DURATIONS[duration])
    return {
        "audience": audience, "audience_label": AUDIENCES[audience],
        "opening": opener, "body": body_lines, "asks": asks, "closing": closer,
        "full_text": full, "short_message": short,
        "tips": TIPS[audience] + COMMON_TIPS,
        "support": {"show": harm, "reason": "script_harm" if harm else None},
    }


def options():
    return {"audiences": AUDIENCES, "feelings": {k: ("thoughts of hurting myself"
                                                     if k == "thoughts_harm" else v)
                                                 for k, v in FEELINGS.items()},
            "durations": DURATIONS, "causes": {k: (v or "I'm not sure")
                                               for k, v in CAUSES.items()},
            "impacts": IMPACTS, "needs": {
                "listen": "Just listen", "advice": "Give advice",
                "study_help": "Help with studies", "professional": "Help me find a "
                "counsellor", "check_in": "Check in on me", "company": "Spend time with me"}}
