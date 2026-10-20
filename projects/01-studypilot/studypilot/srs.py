"""SM-2 spaced repetition (Wozniak, 1987) with Anki-style four buttons.

Button -> SM-2 quality q:  Again=1, Hard=3, Good=4, Easy=5.
  if q < 3:   repetitions = 0, interval = 1 day (card is also re-shown after
              RELEARN_MINUTES in the current session, like Anki's relearning step)
  else:       repetitions += 1; interval = 1, 6, then round(interval * EF)
  EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)),  EF >= 1.3
"""
import math

QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}
DEFAULT_EF = 2.5          # SM-2 initial easiness factor
MIN_EF = 1.3              # SM-2 lower bound
RELEARN_MINUTES = 10      # lapse re-show delay (demo-friendly, Anki default is 10 min)
DAY = 86400.0


def new_state():
    return {"ef": DEFAULT_EF, "reps": 0, "interval": 0, "due": None,
            "lapses": 0, "reviews": 0, "last_rating": None, "last_review": None}


def update_ef(ef, q):
    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return max(MIN_EF, round(ef, 4))


def review(state, rating, now):
    """Return a NEW state dict after answering with ``rating`` at unix time ``now``."""
    if rating not in QUALITY:
        raise ValueError("rating must be one of: " + ", ".join(QUALITY))
    q = QUALITY[rating]
    s = dict(new_state(), **(state or {}))
    if q < 3:
        s["reps"] = 0
        s["interval"] = 1
        s["lapses"] += 1
        s["due"] = now + RELEARN_MINUTES * 60
    else:
        s["reps"] += 1
        if s["reps"] == 1:
            s["interval"] = 1
        elif s["reps"] == 2:
            s["interval"] = 6
        else:
            s["interval"] = int(math.ceil(s["interval"] * s["ef"]))
        s["due"] = now + s["interval"] * DAY
    s["ef"] = update_ef(s["ef"], q)
    s["reviews"] += 1
    s["last_rating"] = rating
    s["last_review"] = now
    return s


def preview(state, now):
    """What each button would schedule: {rating: human label}."""
    out = {}
    for r in QUALITY:
        nxt = review(state, r, now)
        secs = nxt["due"] - now
        out[r] = humanize(secs)
    return out


def humanize(secs):
    if secs < 3600:
        return "%d min" % max(1, round(secs / 60))
    if secs < DAY:
        return "%d h" % round(secs / 3600)
    days = secs / DAY
    if days < 30:
        return "%d d" % round(days)
    if days < 365:
        return "%.1f mo" % (days / 30)
    return "%.1f y" % (days / 365)


def is_due(state, now):
    return state is None or state.get("due") is None or state["due"] <= now
