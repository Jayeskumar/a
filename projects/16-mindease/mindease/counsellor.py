"""Counsellor dashboard: anonymised aggregates and the item-9 alert workflow.

Privacy by design:
* Only check-ins that students *chose* to share reach this view, under pseudonymous IDs.
* Journals never leave the student's view, not even in aggregate.
* Breakdowns narrower than the whole cohort suppress counts of 1-2 ("<3").
* Contact details exist only for students who opted in to be contacted.
"""

from . import config, questionnaires

PHQ_ORDER = ["minimal", "mild", "moderate", "moderately_severe", "severe"]
GAD_ORDER = ["minimal", "mild", "moderate", "severe"]
STATUS_ORDER = {"new": 0, "acknowledged": 1, "followed_up": 2}

PRIVACY_PRINCIPLES = [
    {"title": "Opt-in only",
     "text": "Students choose to share check-in scores. Sharing can be switched off any "
             "time, and the app still works fully without it."},
    {"title": "Pseudonymous IDs",
     "text": "You see IDs like S-7F3A, never names or roll numbers. A name is revealed only "
             "if the student asks a counsellor to reach out."},
    {"title": "Minimal data",
     "text": "Only questionnaire totals, bands, week and year of study are shared. Journal "
             "text, mood and sleep stay private to the student."},
    {"title": "Small-cell suppression",
     "text": "Any breakdown narrower than the whole cohort hides counts below %d, so no "
             "one can be singled out." % config.SMALL_CELL_MIN},
    {"title": "Safety over silence",
     "text": "A PHQ-9 item-9 answer above 0 always shows the student crisis resources "
             "immediately. On a shared check-in it also creates a pseudonymous alert here, "
             "so it is never missed."},
    {"title": "Support, not surveillance",
     "text": "Scores are screening signals for early support, not diagnoses, and are never "
             "used for grades, attendance or discipline."},
]


def _dedupe(screenings):
    """Keep each student's latest screening per (week, instrument)."""
    latest = {}
    for s in screenings:
        latest[(s["pid"], s["week"], s["instrument"])] = s
    return list(latest.values())


def weekly_bands(screenings, weeks, instrument):
    order = PHQ_ORDER if instrument == "phq9" else GAD_ORDER
    rows = []
    for w in weeks:
        sel = [s for s in screenings if s["week"] == w["week"] and
               s["instrument"] == instrument]
        counts = {b: 0 for b in order}
        for s in sel:
            counts[s["band"]] += 1
        n = len(sel)
        modplus = sum(1 for s in sel if s["total"] >= config.REFER_CUTOFF)
        rows.append({"week": w["week"], "start": w["start"], "exam": w["exam"], "n": n,
                     "counts": counts, "moderate_plus": modplus,
                     "pct_moderate_plus": round(100.0 * modplus / n, 1) if n else 0.0})
    return rows


def _suppress(v):
    return v if v == 0 or v >= config.SMALL_CELL_MIN else "<%d" % config.SMALL_CELL_MIN


def by_year(screenings, students, week, instrument="phq9"):
    years = {s["pid"]: s.get("year") for s in students}
    rows = []
    for y in (1, 2, 3, 4):
        sel = [s for s in screenings if s["week"] == week and s["instrument"] == instrument
               and years.get(s["pid"]) == y]
        n = len(sel)
        mod = sum(1 for s in sel if s["total"] >= config.REFER_CUTOFF)
        if n < config.SMALL_CELL_MIN:
            rows.append({"year": y, "n": _suppress(n), "moderate_plus": "suppressed",
                         "suppressed": True})
        else:
            rows.append({"year": y, "n": n, "moderate_plus": _suppress(mod),
                         "suppressed": 0 < mod < config.SMALL_CELL_MIN})
    return rows


def _narrative(rows, label):
    base = [r["pct_moderate_plus"] for r in rows if not r["exam"] and r["n"]]
    exam = [r["pct_moderate_plus"] for r in rows if r["exam"] and r["n"]]
    notes = []
    if base and exam:
        b, e = sum(base) / len(base), sum(exam) / len(exam)
        notes.append("%s moderate-or-above: %.0f%% on average in regular weeks vs %.0f%% "
                     "in exam weeks (%s)." % (label, b, e, ", ".join(
                         "week %d" % r["week"] for r in rows if r["exam"])))
    jumps = [(rows[i]["pct_moderate_plus"] - rows[i - 1]["pct_moderate_plus"], rows[i])
             for i in range(1, len(rows)) if rows[i]["n"] and rows[i - 1]["n"]]
    if jumps:
        d, r = max(jumps, key=lambda j: j[0])
        if d > 0:
            notes.append("Biggest %s week-on-week rise: +%.0f points into week %d."
                         % (label, d, r["week"]))
    return notes


def dashboard(state, today_iso):
    co = state["cohort"]
    weeks = co["weeks"]
    screenings = _dedupe(co["screenings"])
    current = weeks[-1]["week"]
    phq = weekly_bands(screenings, weeks, "phq9")
    gad = weekly_bands(screenings, weeks, "gad7")
    this_w = [s for s in screenings if s["week"] == current]
    prev = phq[-2] if len(phq) > 1 else None
    alerts = sorted(co["alerts"], key=lambda a: (STATUS_ORDER.get(a["status"], 9),
                                                 _neg_date(a["raised"])))
    for a in alerts:
        a["days_open"] = _days_between(a["raised"], today_iso)
    contacts = sorted(co["contacts"], key=lambda c: (c["status"] != "pending",
                                                     _neg_date(c["requested"])))
    kpis = {
        "week": current,
        "checkins_this_week": len({s["pid"] for s in this_w}),
        "cohort_size": len(co["students"]),
        "pct_moderate_plus": phq[-1]["pct_moderate_plus"],
        "pct_moderate_plus_prev": prev["pct_moderate_plus"] if prev else None,
        "gad_pct_moderate_plus": gad[-1]["pct_moderate_plus"],
        "open_alerts": sum(1 for a in alerts if a["status"] == "new"),
        "awaiting_follow_up": sum(1 for a in alerts if a["status"] == "acknowledged"),
        "pending_contacts": sum(1 for c in contacts if c["status"] == "pending"),
        "opted_in_contact": sum(1 for s in co["students"] if s.get("contact_opt_in")),
    }
    return {
        "kpis": kpis,
        "weeks": weeks,
        "phq9": phq,
        "gad7": gad,
        "bands": {
            "phq9": [{"band": b, "label": questionnaires.BAND_LABELS[b]} for b in PHQ_ORDER],
            "gad7": [{"band": b, "label": questionnaires.BAND_LABELS[b]} for b in GAD_ORDER],
        },
        "narrative": _narrative(phq, "PHQ-9") + _narrative(gad, "GAD-7"),
        "by_year": {"week": current, "rows": by_year(screenings, co["students"], current),
                    "min_cell": config.SMALL_CELL_MIN},
        "alerts": alerts,
        "contacts": contacts,
        "privacy": PRIVACY_PRINCIPLES,
        "explain": [
            "Counts are students who shared that week's check-in (latest one per week).",
            "Moderate-or-above means PHQ-9 >= %d or GAD-7 >= %d (published cut-points)."
            % (config.REFER_CUTOFF, config.REFER_CUTOFF),
            "Alerts come only from PHQ-9 item 9 > 0; journal text is never shared.",
        ],
    }


def _neg_date(iso):
    # sort newest first without parsing: invert digits
    return "".join(chr(ord("9") - ord(c) + ord("0")) if c.isdigit() else c for c in iso)


def _days_between(a, b):
    import datetime as dt
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days
    except ValueError:
        return None


# ------------------------------------------------------------------ workflow
def _clean(text, limit):
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError("must be text")
    return " ".join(text.split())[:limit]


def find(items, item_id):
    for it in items:
        if it["id"] == item_id:
            return it
    return None


def acknowledge(state, alert_id, by, note, now_iso):
    alert = find(state["cohort"]["alerts"], alert_id)
    if alert is None:
        raise KeyError(alert_id)
    if alert["status"] != "new":
        raise ValueError("alert is already %s" % alert["status"].replace("_", " "))
    alert["status"] = "acknowledged"
    alert["history"].append({"action": "acknowledged", "by": _clean(by, 60) or "Counsellor",
                             "at": now_iso, "note": _clean(note, 280)})
    return alert


def follow_up(state, alert_id, by, note, now_iso):
    alert = find(state["cohort"]["alerts"], alert_id)
    if alert is None:
        raise KeyError(alert_id)
    if alert["status"] == "followed_up":
        raise ValueError("alert is already followed up")
    who = _clean(by, 60) or "Counsellor"
    if alert["status"] == "new":
        alert["history"].append({"action": "acknowledged", "by": who, "at": now_iso,
                                 "note": ""})
    alert["status"] = "followed_up"
    alert["history"].append({"action": "followed_up", "by": who, "at": now_iso,
                             "note": _clean(note, 280)})
    return alert


def mark_contacted(state, contact_id, by, now_iso):
    c = find(state["cohort"]["contacts"], contact_id)
    if c is None:
        raise KeyError(contact_id)
    if c["status"] == "contacted":
        raise ValueError("already marked as contacted")
    c["status"] = "contacted"
    c["contacted_by"] = _clean(by, 60) or "Counsellor"
    c["contacted_at"] = now_iso
    return c
