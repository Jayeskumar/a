"""Help resources, peer-support guidance and offline self-help content.

Only two phone numbers appear anywhere in MindEase: Tele-MANAS (14416 / 1-800-891-4416)
and emergency services (112). Everything else is general, widely accepted guidance.
"""

from . import config

PEER_SUPPORT = {
    "intro": "Friends are often the first to notice. You don't need to be an expert to "
             "help; you need to listen and help them connect to support.",
    "steps": [
        {"title": "Notice and reach out",
         "text": "If a friend seems withdrawn, isn't sleeping or eating, or says things "
                 "like 'what's the point', check in privately: \"I've noticed you seem "
                 "low lately. How are you really doing?\""},
        {"title": "Listen without judging",
         "text": "Let them talk. Avoid \"just think positive\" or comparing. \"That sounds "
                 "really hard\" is often enough."},
        {"title": "Ask directly if you're worried",
         "text": "It's okay to ask, \"Are you having thoughts of hurting yourself or of "
                 "suicide?\" Asking clearly and calmly does not put the idea in their "
                 "head, and it often brings relief."},
        {"title": "Don't keep it a secret if they're unsafe",
         "text": "You can be a good friend and still tell a counsellor or trusted adult. "
                 "Their safety comes first."},
        {"title": "Help them connect",
         "text": "Offer to sit with them while they call Tele-MANAS (14416) or to walk "
                 "with them to the counselling cell. If they are in immediate danger, call "
                 "112 and stay with them."},
        {"title": "Look after yourself too",
         "text": "Supporting someone is heavy. Talk to someone about how you're feeling, "
                 "too."},
    ],
    "ideas": [
        "Exam-week buddy: pair up and check on each other once a day.",
        "Study circles that end with five minutes of 'how are we actually doing?'.",
        "A peer listening circle run by trained student volunteers, with a counsellor "
        "as backup (ask your counselling cell to start one).",
        "Hostel-floor tea breaks during exams: no phones, no marks talk.",
    ],
}

WHEN_TO_GET_HELP = [
    "Thoughts of hurting yourself, or that others would be better off without you.",
    "Feeling low or anxious most days for two weeks or more.",
    "Not able to sleep, eat, attend class or look after yourself for several days.",
    "Using alcohol or other substances to cope.",
    "Feeling numb or disconnected, or like nothing will get better.",
]

SLEEP_TIPS = [
    {"title": "Same time, every day", "text": "Keep a regular sleep and wake time, even "
     "around exams. Your body clock likes routine."},
    {"title": "Aim for 7-9 hours", "text": "Young adults are generally advised 7-9 hours. "
     "Memory consolidation happens during sleep, so an all-nighter costs recall."},
    {"title": "Screens off 30-60 min before bed", "text": "Swap scrolling for a short "
     "walk, light stretching or the breathing exercise."},
    {"title": "Caffeine before 3 pm", "text": "Tea, coffee and energy drinks can keep you "
     "alert for hours after you drink them."},
    {"title": "The 20-minute rule", "text": "If you can't fall asleep after about 20 "
     "minutes, get up, do something calm in dim light, and go back when sleepy."},
    {"title": "Short naps only", "text": "Keep naps under 30 minutes and before late "
     "afternoon so night sleep isn't affected."},
    {"title": "Park your worries", "text": "Write tomorrow's to-do list and any worries on "
     "paper before bed, so your mind doesn't have to hold them."},
]

GROUNDING_STEPS = [
    {"count": 5, "sense": "see", "prompt": "Name 5 things you can see around you."},
    {"count": 4, "sense": "touch", "prompt": "Notice 4 things you can touch or feel."},
    {"count": 3, "sense": "hear", "prompt": "Listen for 3 things you can hear."},
    {"count": 2, "sense": "smell", "prompt": "Find 2 things you can smell."},
    {"count": 1, "sense": "taste", "prompt": "Notice 1 thing you can taste."},
]

BREATHING = {
    "name": "Box breathing",
    "phases": [{"label": "Breathe in", "seconds": 4}, {"label": "Hold", "seconds": 4},
               {"label": "Breathe out", "seconds": 4}, {"label": "Hold", "seconds": 4}],
    "note": "Slow breathing can calm the body's stress response. Stop if you feel dizzy "
            "and breathe normally.",
}


def all_resources():
    return {
        "helplines": config.HELPLINES,
        "counselling_cell": config.COUNSELLING_CELL,
        "peer_support": PEER_SUPPORT,
        "when_to_get_help": WHEN_TO_GET_HELP,
        "sleep_tips": SLEEP_TIPS,
        "grounding": GROUNDING_STEPS,
        "breathing": BREATHING,
        "disclaimer": "MindEase is a supportive screening and self-help tool. It does not "
                      "diagnose or treat any condition and is not a substitute for "
                      "professional care.",
    }


def support_screen(reason, level="urgent"):
    """Content of the gentle support screen (item 9, journal phrases, script)."""
    headline = {
        "item9": "Thank you for answering honestly.",
        "journal": "Thank you for writing this down.",
        "script": "Thank you for putting this into words.",
        "someone_else": "It sounds like you're worried about someone.",
    }.get(reason, "You don't have to go through this alone.")
    if reason == "someone_else":
        body = ("You can help by listening, asking them directly how they are, and helping "
                "them reach support. If they might be in immediate danger, call 112 and "
                "stay with them.")
    elif level == "concern":
        body = ("What you're feeling matters, and you don't have to carry it alone. "
                "Talking to someone can really help, today if possible.")
    else:
        body = ("It sounds like things might feel really hard right now. You deserve "
                "support, and help is available right now, any time of day or night.")
    return {
        "reason": reason, "level": level, "headline": headline, "body": body,
        "helplines": config.HELPLINES,
        "actions": [
            {"id": "call_telemanas", "label": "Call Tele-MANAS 14416", "tel": "14416"},
            {"id": "talk_counsellor", "label": "Talk to a counsellor now"},
            {"id": "breathe", "label": "Breathe with me for a minute"},
        ],
        "emergency": "If you are in immediate danger, call 112 now.",
        "peer": reason == "someone_else",
    }
