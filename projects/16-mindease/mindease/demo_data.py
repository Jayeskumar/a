"""Deterministic synthetic demo data (fixed seed). Nothing here is real student data.

* Ananya: a demo 2nd-year student with a 3-week journal. Weeks 1-2 are mostly fine;
  in the last 5 days before exams, her mood, sleep and journal tone dip together.
* Cohort: 60 pseudonymous students over an 8-week term. Semester exams fall in weeks 7-8,
  where weekly PHQ-9 / GAD-7 check-ins show a stress spike. Rare PHQ-9 item-9 answers
  create alerts for the counsellor dashboard.

Run `python -m mindease.demo_data` to (re)write data/demo_seed.json with fixed dates.
"""

import datetime as _dt
import hashlib
import json
import os
import random

from . import config, questionnaires, sentiment

FIXED_END_DATE = _dt.date(2026, 10, 22)  # used for the committed snapshot and tests

# (mood 1-5, sleep hours, journal text) for days -21 .. -1
ANANYA_JOURNAL = [
    (4, 7.5, "Back to college after the weekend. Had a semma fun lunch with my friends "
             "\U0001F604"),
    (4, 7.0, "Lab session went well, finally understood how the circuit works."),
    (5, 8.0, "Cultural fest practice tonight! Really happy and excited for the dance "
             "performance \U0001F389"),
    (4, 7.5, "Bit tired after practice but it was totally worth it."),
    (4, 7.0, "Normal day. Classes, canteen, library."),
    (5, 8.0, "We performed at the fest and everyone loved it! Vera level feeling "
             "\U0001F60A"),
    (4, 8.5, "Lazy Sunday, slept well and watched a movie with my cousins."),
    (4, 7.0, "Timetable for semester exams is out. A little nervous but I have a plan."),
    (4, 7.0, "Studied two chapters of maths. Felt productive."),
    (3, 6.5, "Too many assignments this week, konjam stressed."),
    (4, 7.0, "Group study with Divya helped a lot, not bad at all."),
    (4, 7.5, "Calm day. Went for a walk in the evening, felt peaceful."),
    (3, 6.5, "Internal marks came out. Not happy with my physics score, but okay."),
    (4, 7.5, "Called Amma, felt better after talking to her."),
    (4, 6.5, "Revision is slow but steady. A bit worried about the syllabus."),
    (4, 6.0, "Long study day, but I finished the electronics unit. Proud of that."),
    (2, 5.5, "Couldn't sleep properly, so much tension about the maths exam \U0001F61F"),
    (2, 5.0, "Feeling really tired and not happy with how I'm studying. Everyone else "
             "seems ahead."),
    (3, 5.5, "Video call with my cousin helped a bit, but still anxious."),
    (2, 5.0, "Romba stressed. Skipped lunch to study and still feel behind "
             "\U0001F61E"),
    (2, 4.5, "I feel so drained and lonely. Thookam varala, my mind keeps racing about "
             "exams."),
]

# Ananya's earlier check-ins: (days before end, instrument, answers)
ANANYA_SCREENINGS = [
    (20, "phq9", [0, 1, 1, 1, 0, 0, 1, 0, 0]),   # 4 minimal
    (20, "gad7", [1, 1, 1, 0, 0, 0, 0]),         # 3 minimal
    (6, "phq9", [1, 1, 1, 1, 1, 1, 1, 0, 0]),    # 7 mild
    (6, "gad7", [2, 2, 1, 1, 1, 1, 1]),          # 9 mild
]

# Suggested live-demo entry (shown as a one-click example in the UI).
DEMO_LIVE_ENTRY = {
    "mood": 2, "sleep": 4.5,
    "text": "Exams are killing me. Couldn't sleep again and I feel like nothing will ever "
            "get better.",
}


def pseudonym(seed, i):
    """Stable pseudonymous ID such as 'S-7F3A' (no link to name or roll number)."""
    return "S-" + hashlib.sha256(("%s:%s" % (seed, i)).encode()).hexdigest()[:4].upper()


def week_starts(today, weeks=config.COHORT_WEEKS):
    """Monday of each term week; the last week contains `today`."""
    monday = today - _dt.timedelta(days=today.weekday())
    return [monday - _dt.timedelta(weeks=weeks - w) for w in range(1, weeks + 1)]


def ananya(end_date):
    """Ananya's journal entries (with analysis) and earlier screenings."""
    entries = []
    n = len(ANANYA_JOURNAL)
    for i, (mood, sleep, text) in enumerate(ANANYA_JOURNAL):
        day = end_date - _dt.timedelta(days=n - 1 - i)
        a = sentiment.analyse(text, with_tokens=False)
        entries.append({"id": "j%02d" % (i + 1), "date": day.isoformat(), "mood": mood,
                        "sleep": sleep, "text": text, "sentiment": a["compound"],
                        "label": a["label"],
                        "emotions": [e["emotion"] for e in a["emotions"][:2]],
                        "flagged": False})
    screenings = []
    for k, (days_before, inst, answers) in enumerate(ANANYA_SCREENINGS):
        r = questionnaires.score(inst, answers)
        day = end_date - _dt.timedelta(days=days_before)
        screenings.append({"id": "s%02d" % (k + 1), "date": day.isoformat(),
                           "instrument": inst, "answers": answers, "total": r["total"],
                           "band": r["band"], "shared": True})
    return entries, screenings


def _clamp(v, lo=0, hi=3):
    return max(lo, min(hi, v))


def cohort(today, seed=config.DEMO_SEED):
    """60 pseudonymous students x 8 weeks of opt-in PHQ-9 / GAD-7 check-ins."""
    rng = random.Random(seed)
    starts = week_starts(today)
    exam_lift = {1: 0.0, 2: 0.0, 3: 0.05, 4: 0.05, 5: 0.15, 6: 0.3, 7: 0.95, 8: 1.05}
    students, screenings = [], []
    used = set()
    for i in range(config.COHORT_SIZE):
        pid = pseudonym(seed, i)
        j = i
        while pid in used:  # astronomically rare, but keep IDs unique
            j += 1000
            pid = pseudonym(seed, j)
        used.add(pid)
        r = rng.random()
        level = rng.uniform(0.05, 0.45) if r < 0.68 else (
            rng.uniform(0.5, 1.0) if r < 0.92 else rng.uniform(1.0, 1.6))
        anx = _clamp(0.6 * level + 0.4 * rng.uniform(0.0, 1.2), 0, 2.0)
        students.append({
            "pid": pid,
            "year": rng.choices([1, 2, 3, 4], weights=[30, 27, 23, 20])[0],
            "contact_opt_in": rng.random() < config.CONTACT_OPT_IN_RATE,
            "preferred": rng.choice(["in person", "phone call", "college email"]),
            "_level": level, "_anx": anx, "_exam": rng.uniform(0.2, 0.9),
            "_p": rng.uniform(0.45, 0.95),
        })
    phq_bias = [0.0, 0.1, 0.35, 0.3, 0.0, 0.0, 0.2, -0.3, None]
    gad_bias = [0.25, 0.0, 0.2, 0.1, -0.2, 0.15, -0.15]
    for s in students:
        for w in range(1, config.COHORT_WEEKS + 1):
            p = s["_p"] * (config.WEEKLY_CHECKIN_RATE / 0.7)
            if rng.random() > p:
                continue
            lift = exam_lift[w] * s["_exam"]
            dep = s["_level"] + lift
            phq = []
            for b in phq_bias:
                if b is None:  # item 9 - rare, only at the high end
                    v = 0
                    if dep > 1.35 and rng.random() < 0.30:
                        v = 1 if rng.random() < 0.75 else 2
                    phq.append(v)
                else:
                    phq.append(_clamp(int(round(dep + b + rng.gauss(0, 0.45)))))
            anx = s["_anx"] + 1.1 * lift
            gad = [_clamp(int(round(anx + b + rng.gauss(0, 0.45)))) for b in gad_bias]
            day = starts[w - 1] + _dt.timedelta(days=rng.randint(0, 4))
            if day > today:
                day = today
            for inst, ans in (("phq9", phq), ("gad7", gad)):
                total = sum(ans)
                screenings.append({
                    "pid": s["pid"], "week": w, "date": day.isoformat(), "instrument": inst,
                    "total": total, "band": questionnaires.band_for(inst, total),
                    "item9": ans[8] if inst == "phq9" else None,
                })
    alerts, contacts = [], []
    by_pid = {s["pid"]: s for s in students}
    for sc in screenings:
        if sc["instrument"] == "phq9" and sc["item9"]:
            st = by_pid[sc["pid"]]
            w = sc["week"]
            status = "followed_up" if w <= 6 else ("acknowledged" if w == 7 else "new")
            alert = {
                "id": "A%03d" % (len(alerts) + 1), "pid": sc["pid"], "week": w,
                "raised": sc["date"], "source": "PHQ-9 item 9",
                "item9": sc["item9"],
                "item9_label": questionnaires.OPTIONS[sc["item9"]]["label"],
                "phq9_total": sc["total"], "band": sc["band"],
                "contact_ok": st["contact_opt_in"],
                "preferred": st["preferred"] if st["contact_opt_in"] else None,
                "status": status, "history": [],
            }
            if status in ("acknowledged", "followed_up"):
                alert["history"].append({"action": "acknowledged", "by": "Ms. Kavya (demo)",
                                         "at": sc["date"], "note": "Reviewed same day."})
            if status == "followed_up":
                alert["history"].append({
                    "action": "followed_up", "by": "Ms. Kavya (demo)", "at": sc["date"],
                    "note": "Student met counsellor." if st["contact_opt_in"] else
                    "No contact consent: cohort-wide support message sent."})
            alerts.append(alert)
    # Opted-in students ask for a chat the first week their PHQ-9 or GAD-7 reaches mild.
    latest, first_ask = {}, {}
    for sc in screenings:
        if sc["instrument"] == "phq9":
            latest[sc["pid"]] = sc
        if sc["total"] >= 5 and sc["pid"] not in first_ask:
            first_ask[sc["pid"]] = sc
    for s in students:
        sc = first_ask.get(s["pid"])
        if not s["contact_opt_in"] or sc is None:
            continue
        contacts.append({
            "id": "C%03d" % (len(contacts) + 1), "pid": s["pid"], "week": sc["week"],
            "requested": sc["date"], "reason": "Asked for a chat at check-in",
            "preferred": s["preferred"], "latest_band": latest[s["pid"]]["band"],
            "status": "contacted" if sc["week"] <= 6 else "pending",
        })
    public = [{k: v for k, v in s.items() if not k.startswith("_")} for s in students]
    return {
        "weeks": [{"week": w, "start": starts[w - 1].isoformat(),
                   "exam": w in config.EXAM_WEEKS} for w in range(1, config.COHORT_WEEKS + 1)],
        "students": public, "screenings": screenings, "alerts": alerts,
        "contacts": contacts,
    }


def build_state(end_date=None, today=None):
    """Complete initial app state for the demo (deterministic content)."""
    if end_date is None:
        today = today or _dt.date.today()
        end_date = today - _dt.timedelta(days=1)
    today = today or end_date + _dt.timedelta(days=1)
    entries, screenings = ananya(end_date)
    co = cohort(today)
    student_pid = pseudonym("student", config.DEMO_STUDENT_NAME)
    return {
        "version": 1,
        "generated_for": today.isoformat(),
        "student": {
            "name": config.DEMO_STUDENT_NAME, "pid": student_pid, "year": 2,
            "consent": {"share_aggregate": True, "contact": False},
            "journal": entries, "screenings": screenings,
        },
        "cohort": co,
        "counter": {"journal": len(entries), "screening": len(screenings),
                    "alert": len(co["alerts"]), "contact": len(co["contacts"])},
    }


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "data", "demo_seed.json")
    state = build_state(end_date=FIXED_END_DATE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    co = state["cohort"]
    print("wrote %s: %d journal entries, %d cohort screenings, %d alerts, %d contacts"
          % (path, len(state["student"]["journal"]), len(co["screenings"]),
             len(co["alerts"]), len(co["contacts"])))


if __name__ == "__main__":
    main()
