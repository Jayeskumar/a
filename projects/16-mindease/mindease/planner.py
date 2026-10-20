"""Exam-stress study planner built on Pomodoro blocks (25 min focus / 5 min break).

Allocation rule (explainable greedy):
  score(subject, day) = need x (1 + 2 / days_until_exam) / (1 + sessions_already_given)
  need = 6 - confidence  (confidence 1 = "not prepared" ... 5 = "very prepared")
* Less-prepared subjects get more sessions; a subject's share rises as its exam nears.
* The day before an exam, at least half the sessions go to that subject (light revision).
* No subject gets more than 2 sessions in a row (interleaving beats cramming one topic).
* Sleep is protected: no block ends after LATEST_STUDY_END, and days are capped at
  MAX_STUDY_HOURS_PER_DAY.
"""

import datetime as _dt

from . import config


def _hm(s):
    h, m = s.split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError
    return h * 60 + m


def _fmt(mins):
    return "%02d:%02d" % (mins // 60, mins % 60)


def validate(body, today):
    errors = {}
    exams_in = body.get("exams")
    exams = []
    if not isinstance(exams_in, list) or not exams_in:
        errors["exams"] = "add at least one exam"
    elif len(exams_in) > 8:
        errors["exams"] = "at most 8 exams"
    else:
        for i, e in enumerate(exams_in):
            if not isinstance(e, dict):
                errors["exams[%d]" % i] = "must be an object"
                continue
            subj = e.get("subject")
            if not isinstance(subj, str) or not subj.strip() or len(subj) > 40:
                errors["exams[%d].subject" % i] = "1-40 characters"
                continue
            try:
                d = _dt.date.fromisoformat(str(e.get("date")))
            except ValueError:
                errors["exams[%d].date" % i] = "use YYYY-MM-DD"
                continue
            conf = e.get("confidence", 3)
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) \
                    or not 1 <= conf <= 5:
                errors["exams[%d].confidence" % i] = "1 (not prepared) to 5 (very prepared)"
                continue
            exams.append({"subject": " ".join(subj.split()), "date": d,
                          "confidence": int(conf)})
    try:
        start = _dt.date.fromisoformat(str(body.get("start_date") or today.isoformat()))
    except ValueError:
        errors["start_date"] = "use YYYY-MM-DD"
        start = today
    hours = body.get("hours_per_day", 3)
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or \
            not 0.5 <= hours <= 12:
        errors["hours_per_day"] = "between 0.5 and 12"
        hours = 3
    try:
        start_time = _hm(str(body.get("start_time") or "17:30"))
    except (ValueError, AttributeError):
        errors["start_time"] = "use HH:MM (24-hour)"
        start_time = _hm("17:30")
    if exams and not errors:
        if max(e["date"] for e in exams) <= start:
            errors["exams"] = "at least one exam must be after the start date"
        elif (max(e["date"] for e in exams) - start).days > config.PLANNER_MAX_DAYS + 1:
            errors["exams"] = "plan up to %d days ahead" % config.PLANNER_MAX_DAYS
    return {"exams": exams, "start": start, "hours": float(hours),
            "start_time": start_time}, errors


def _day_blocks(start_time, minutes_budget, cutoff):
    """Focus-slot start times for one day, with breaks, within budget and cutoff.

    Returns (slots, cut_by_bedtime): the flag is True when the sleep cutoff, not the
    study budget, stopped the day."""
    slots, t, used, n = [], start_time, 0, 0
    while used + config.POMODORO_FOCUS_MIN <= minutes_budget:
        if t + config.POMODORO_FOCUS_MIN > cutoff:
            return slots, True
        slots.append(t)
        used += config.POMODORO_FOCUS_MIN
        n += 1
        brk = config.POMODORO_LONG_BREAK_MIN if n % config.POMODOROS_PER_SET == 0 \
            else config.POMODORO_BREAK_MIN
        t += config.POMODORO_FOCUS_MIN + brk
    return slots, False


def plan(body, today=None):
    """Return {"days", "subjects", "explain", "warnings"} or raise ValueError(errors)."""
    today = today or _dt.date.today()
    v, errors = validate(body, today)
    if errors:
        raise ValueError(errors)
    exams, start = v["exams"], v["start"]
    warnings = []
    hours = v["hours"]
    if hours > config.MAX_STUDY_HOURS_PER_DAY:
        warnings.append("We capped study at %d h a day. Beyond that, rest helps marks more "
                        "than extra hours." % config.MAX_STUDY_HOURS_PER_DAY)
        hours = config.MAX_STUDY_HOURS_PER_DAY
    cutoff = _hm(config.LATEST_STUDY_END)
    budget = int(round(hours * 60))
    slots_template, cut = _day_blocks(v["start_time"], budget, cutoff)
    if not slots_template:
        raise ValueError({"start_time": "no 25-minute block fits before %s"
                          % config.LATEST_STUDY_END})
    if cut:
        warnings.append("Starting at %s, only %d focus blocks fit before %s, so we kept "
                        "your evenings for sleep." % (_fmt(v["start_time"]),
                                                      len(slots_template),
                                                      config.LATEST_STUDY_END))
    for e in exams:
        if e["date"] <= start:
            warnings.append("%s is on or before the start date, so it is not scheduled."
                            % e["subject"])
    active = [e for e in exams if e["date"] > start]
    last = max(e["date"] for e in active)
    given = {e["subject"]: 0 for e in active}
    days = []
    d = start
    while d < last:
        open_exams = [e for e in active if e["date"] > d]
        blocks, seq = [], []
        tomorrow = [e for e in open_exams if (e["date"] - d).days == 1]
        exam_today = [e["subject"] for e in exams if e["date"] == d]
        # After an exam, a lighter evening: half the usual blocks.
        day_slots = slots_template[:max(1, len(slots_template) // 2)] if exam_today \
            else slots_template
        for k, t in enumerate(day_slots):
            if tomorrow and k < max(1, (len(day_slots) + 1) // 2):
                choice = min(tomorrow, key=lambda e: e["confidence"])
                reason = "revision: exam tomorrow"
            else:
                ranked = sorted(open_exams, key=lambda e: -_score(e, d, given))
                choice = ranked[0]
                if len(seq) >= 2 and seq[-1] == seq[-2] == choice["subject"] and \
                        len(ranked) > 1:
                    choice = ranked[1]
                reason = "need %d, %d day(s) left" % (6 - choice["confidence"],
                                                      (choice["date"] - d).days)
            given[choice["subject"]] += 1
            seq.append(choice["subject"])
            blocks.append({"start": _fmt(t), "end": _fmt(t + config.POMODORO_FOCUS_MIN),
                           "type": "focus", "subject": choice["subject"], "why": reason})
            n = k + 1
            if k < len(day_slots) - 1:
                long_break = n % config.POMODOROS_PER_SET == 0
                brk = config.POMODORO_LONG_BREAK_MIN if long_break else \
                    config.POMODORO_BREAK_MIN
                bstart = t + config.POMODORO_FOCUS_MIN
                blocks.append({"start": _fmt(bstart), "end": _fmt(bstart + brk),
                               "type": "long_break" if long_break else "break",
                               "subject": None, "why": None})
        note = "Sleep early: exam tomorrow." if tomorrow else (
            "Exam day: a lighter evening, you've earned it." if exam_today else None)
        days.append({"date": d.isoformat(), "weekday": d.strftime("%a"),
                     "exam_today": exam_today, "blocks": blocks,
                     "focus_min": sum(config.POMODORO_FOCUS_MIN for b in blocks
                                      if b["type"] == "focus"),
                     "note": note})
        d += _dt.timedelta(days=1)
    total = sum(given.values()) or 1
    subjects = [{"subject": e["subject"], "exam": e["date"].isoformat(),
                 "confidence": e["confidence"], "need": 6 - e["confidence"],
                 "sessions": given[e["subject"]],
                 "hours": round(given[e["subject"]] * config.POMODORO_FOCUS_MIN / 60, 1),
                 "share": round(given[e["subject"]] / total, 3)} for e in active]
    return {
        "days": days, "subjects": subjects, "warnings": warnings,
        "settings": {"focus": config.POMODORO_FOCUS_MIN, "break": config.POMODORO_BREAK_MIN,
                     "long_break": config.POMODORO_LONG_BREAK_MIN,
                     "set": config.POMODOROS_PER_SET, "latest_end": config.LATEST_STUDY_END},
        "explain": [
            "Each block is a Pomodoro: %d min focus, %d min break, a %d min break after "
            "every %d." % (config.POMODORO_FOCUS_MIN, config.POMODORO_BREAK_MIN,
                           config.POMODORO_LONG_BREAK_MIN, config.POMODOROS_PER_SET),
            "Subjects you feel less ready for (low confidence) get more blocks: "
            "need = 6 - confidence.",
            "A subject's priority grows as its exam gets closer, and the day before an exam "
            "is mostly light revision of it. Exam days get half the usual blocks.",
            "No block ends after %s, so you can still get 7-9 h of sleep."
            % config.LATEST_STUDY_END,
        ],
    }


def _score(e, d, given):
    days_left = max(1, (e["date"] - d).days)
    return (6 - e["confidence"]) * (1 + 2.0 / days_left) / (1 + given[e["subject"]])
