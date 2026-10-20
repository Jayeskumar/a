"""Trend engine: rolling averages and change detection on mood, sleep and journal tone.

Three detectors, all computed against *your own* baseline (never against other
students):

* CUSUM       - one-sided lower CUSUM on standardised values (Page 1954):
                S_t = max(0, S_{t-1} - z_t - k), alarm when S_t > h.
                Accumulates small, persistent drops that a single bad day would not show.
* Dip run     - consecutive most-recent days below baseline mean - 1 sd.
                Easy to explain: "your mood has dipped for 5 days".
* Slope test  - OLS slope over the last 7 days with a one-sided t-test (95%).

Decision rule (dip_decision): a dip is reported when CUSUM has crossed h AND the latest
2+ days are still below the dip threshold. The slope test is shown as supporting evidence
only: on its own it fired on 26% of simulated stable weeks (integer 1-5 moods + checking
every day inflates it).

The engine only produces kind, non-alarmist "insights" with the evidence that produced
them. It never labels a student.
"""

import datetime as _dt
import math
import re

from . import config

METRICS = ("mood", "sleep", "sentiment")
METRIC_NAMES = {"mood": "mood", "sleep": "sleep", "sentiment": "journal tone"}
MONITOR_WINDOW = 7  # days examined by CUSUM / slope after the baseline period


# ---------------------------------------------------------------- basic statistics
def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def rolling_mean(values, window=config.ROLLING_WINDOW, min_periods=3):
    """Trailing rolling mean; None until min_periods non-missing values are available."""
    out = []
    for i in range(len(values)):
        win = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(round(mean(win), 3) if len(win) >= min_periods else None)
    return out


def ols_slope(xs, ys):
    """Least-squares slope with its t statistic. Returns dict or None if n < 3."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    sse = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    df = n - 2
    se = math.sqrt(sse / df) / math.sqrt(sxx) if df > 0 else 0.0
    if se == 0:
        t = 99.0 if b > 0 else (-99.0 if b < 0 else 0.0)
    else:
        t = max(-99.0, min(99.0, b / se))
    crit = config.T_CRIT_95_ONE_SIDED.get(df, 1.645)
    return {"slope": round(b, 4), "intercept": round(a, 4), "t": round(t, 3), "df": df,
            "t_crit": crit, "n": n, "significant_down": t < -crit, "significant_up": t > crit}


def cusum_lower(values, mu, sigma, k=None, h=None):
    """One-sided lower CUSUM. Returns (S list, alarm index or None, change-start index)."""
    k = config.CUSUM_K if k is None else k
    h = config.CUSUM_H if h is None else h
    s, out, alarm, start = 0.0, [], None, None
    last_zero = -1
    for i, x in enumerate(values):
        z = (x - mu) / sigma
        s = max(0.0, s - z - k)
        out.append(round(s, 3))
        if s == 0:
            last_zero = i
        if alarm is None and s > h:
            alarm = i
            start = last_zero + 1
    return out, alarm, start


# ---------------------------------------------------------------- series building
def _parse_date(d):
    return _dt.date.fromisoformat(d) if isinstance(d, str) else d


def daily_series(entries):
    """Collapse entries into one row per day (mean of that day's values), sorted."""
    days = {}
    for e in entries:
        try:
            day = _parse_date(e["date"])
        except (KeyError, ValueError, TypeError):
            continue
        row = days.setdefault(day, {m: [] for m in METRICS})
        for m in METRICS:
            v = e.get(m)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row[m].append(float(v))
    out = []
    for day in sorted(days):
        row = {"date": day.isoformat()}
        for m in METRICS:
            vals = days[day][m]
            row[m] = round(mean(vals), 3) if vals else None
        out.append(row)
    return out


def _baseline(values):
    """Baseline = up to BASELINE_MAX_POINTS values before the monitoring window."""
    base = [v for v in values[:-MONITOR_WINDOW] if v is not None]
    base = base[-config.BASELINE_MAX_POINTS:]
    if len(base) < config.BASELINE_MIN_POINTS:
        return None
    return base


def detect_metric(series, metric):
    """Run all three detectors on one metric. Returns a JSON-friendly dict."""
    dates = [r["date"] for r in series]
    values = [r[metric] for r in series]
    base = _baseline(values)
    if base is None:
        return {"metric": metric, "ready": False}
    mu = mean(base)
    sigma = max(sd(base), config.SD_FLOOR[metric])
    idx = [i for i in range(max(0, len(values) - MONITOR_WINDOW), len(values))
           if values[i] is not None]
    mon_vals = [values[i] for i in idx]
    mon_dates = [dates[i] for i in idx]
    s_vals, alarm, start = cusum_lower(mon_vals, mu, sigma) if mon_vals else ([], None, None)

    # dip run: consecutive most-recent non-missing values below mu - DIP_SD * sigma
    threshold = mu - config.DIP_SD * sigma
    run, run_vals, run_dates = 0, [], []
    for i in range(len(values) - 1, -1, -1):
        v = values[i]
        if v is None:
            continue
        if v < threshold:
            run += 1
            run_vals.insert(0, v)
            run_dates.insert(0, dates[i])
        else:
            break
    consecutive = True
    if len(run_dates) > 1:
        ds = [_parse_date(d) for d in run_dates]
        consecutive = all((b - a).days == 1 for a, b in zip(ds, ds[1:]))

    # slope over the last SLOPE_WINDOW non-missing days (x = day number)
    pts = [(dates[i], values[i]) for i in range(len(values)) if values[i] is not None]
    pts = pts[-config.SLOPE_WINDOW:]
    slope = None
    if len(pts) >= 3:
        d0 = _parse_date(pts[0][0])
        slope = ols_slope([(_parse_date(d) - d0).days for d, _ in pts], [v for _, v in pts])

    recent = [v for v in values[-config.RECENT_WINDOW:] if v is not None]
    return {
        "metric": metric, "ready": True,
        "baseline": {"mean": round(mu, 3), "sd": round(sigma, 3), "n": len(base)},
        "recent_mean": round(mean(recent), 3) if recent else None,
        "recent_n": len(recent),
        "cusum": {"values": s_vals, "dates": mon_dates, "k": config.CUSUM_K,
                  "h": config.CUSUM_H,
                  "alarm_date": mon_dates[alarm] if alarm is not None else None,
                  "change_start": mon_dates[start] if alarm is not None else None,
                  "alarm_value": s_vals[alarm] if alarm is not None else None,
                  "current": s_vals[-1] if s_vals else 0.0,
                  "peak": max(s_vals) if s_vals else 0.0},
        "dip_run": {"length": run, "threshold": round(threshold, 3), "values": run_vals,
                    "dates": run_dates, "consecutive_days": consecutive},
        "slope": slope,
    }


def dip_decision(d):
    """The single rule used by the app and the evaluation: CUSUM alarm + recent run."""
    if not d or not d.get("ready"):
        return False
    return d["cusum"]["alarm_date"] is not None and \
        d["dip_run"]["length"] >= config.DIP_RUN_MIN


# ---------------------------------------------------------------- "what helped before"
ACTIVITIES = [
    (r"\b(walk|walked|walking)\b", "going for a walk"),
    (r"\b(call(ed)?|talk(ed|ing)? to|video call|chat(ted)? with)\b", "talking to someone close"),
    (r"\b(friends?|roommate|cousins?|divya)\b", "time with friends and family"),
    (r"\b(music|songs?|sing(ing)?)\b", "music"),
    (r"\b(movie|film)\b", "watching a movie"),
    (r"\b(slept well|good sleep|rested)\b", "a good night's sleep"),
    (r"\b(group study|studied with|study group)\b", "studying with others"),
    (r"\b(dance|danc(ed|ing)|practice|performed|sketch(ing)?|draw(ing)?)\b", "creative practice"),
    (r"\b(yoga|gym|exercise|badminton|cricket|football|run|ran|played)\b", "being active"),
    (r"\b(breathing|meditat\w*)\b", "breathing / meditation"),
    (r"\b(plan|planned|timetable|finished|productive)\b", "a clear plan for the day"),
]


def helped_before(entries, min_mood=4):
    """Activities mentioned on better days (mood >= 4), most frequent first."""
    counts = {}
    for e in entries:
        if (e.get("mood") or 0) < min_mood:
            continue
        text = (e.get("text") or "").lower()
        for rx, label in ACTIVITIES:
            if re.search(rx, text):
                counts[label] = counts.get(label, 0) + 1
    return [{"activity": k, "days": v}
            for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:4]


# ---------------------------------------------------------------- insights
def _fmt_date(d):
    day = _parse_date(d)
    return "%d %s" % (day.day, day.strftime("%b"))


def _fmt_vals(vals, metric):
    if metric == "sleep":
        return ", ".join("%.1f h" % v for v in vals)
    if metric == "sentiment":
        return ", ".join("%+.2f" % v for v in vals)
    return ", ".join("%g" % v for v in vals)


def _unit(metric, v):
    if metric == "mood":
        return "%.1f/5" % v
    if metric == "sleep":
        return "%.1f h" % v
    return "%+.2f" % v


def analyse(entries, today=None):
    """Full trend analysis + kind insights for one student's journal entries."""
    series = daily_series(entries)
    for m in METRICS:
        avgs = rolling_mean([r[m] for r in series])
        for r, a in zip(series, avgs):
            r[m + "_avg7"] = a
    result = {"series": series, "detectors": {}, "insights": [],
              "helped_before": helped_before(entries), "status": "ok",
              "settings": {"monitor_window": MONITOR_WINDOW,
                           "rolling_window": config.ROLLING_WINDOW,
                           "cusum_k": config.CUSUM_K, "cusum_h": config.CUSUM_H,
                           "dip_sd": config.DIP_SD, "slope_window": config.SLOPE_WINDOW}}
    if len(series) < config.BASELINE_MIN_POINTS + 2:
        result["status"] = "not_enough_data"
        result["insights"].append({
            "id": "warming_up", "kind": "info", "tone": "gentle", "metric": None,
            "title": "Getting to know your usual",
            "message": "After about a week of check-ins, MindEase can notice changes "
                       "compared with *your* usual - never compared with anyone else.",
            "suggestion": {"text": "Add today's mood, sleep and a line or two.",
                           "action": "journal"},
            "evidence": ["%d day(s) logged so far; %d needed."
                         % (len(series), config.BASELINE_MIN_POINTS + 2)],
        })
        return result

    det = {m: detect_metric(series, m) for m in METRICS}
    result["detectors"] = det
    dips = {m: det[m] for m in METRICS if dip_decision(det[m])}

    insights = []
    if "mood" in dips:
        insights.append(_dip_insight("mood", dips["mood"]))
    sleep_d = det["sleep"]
    if sleep_d.get("ready") and sleep_d["recent_mean"] is not None:
        drop = sleep_d["baseline"]["mean"] - sleep_d["recent_mean"]
        if sleep_d["recent_mean"] < config.SLEEP_LOW_HOURS or "sleep" in dips:
            insights.append(_sleep_insight(sleep_d, drop))
    if "sentiment" in dips:
        insights.append(_tone_insight(dips["sentiment"], entries))
    flagged = sum(1 for i in insights if i["kind"] in ("dip", "sleep", "tone"))
    if flagged >= 2:
        insights.insert(0, {
            "id": "together", "kind": "together", "tone": "notice", "metric": None,
            "title": "A few things have dipped together",
            "message": "Your %s have all been lower than your usual at the same time. "
                       "That happens to a lot of students around exams, and it's a good "
                       "moment to be extra kind to yourself and to let someone in."
                       % _join([METRIC_NAMES[i["metric"]] for i in insights
                                if i["metric"]]),
            "suggestion": {"text": "Take the 2-minute PHQ-9 check-in, or use the "
                                   "'Talk to someone' script to reach out.",
                           "action": "checkin"},
            "evidence": ["%d of 3 signals (mood, sleep, journal tone) are below your "
                         "baseline." % flagged],
        })
    mood_d = det["mood"]
    if mood_d.get("ready") and "mood" not in dips:
        slope = mood_d["slope"] or {}
        if slope.get("significant_up") or (mood_d["recent_mean"] or 0) >= \
                mood_d["baseline"]["mean"] + 0.5:
            insights.append({
                "id": "lift", "kind": "lift", "tone": "positive", "metric": "mood",
                "title": "Your mood has lifted lately",
                "message": "Your recent days are brighter than your usual. Whatever "
                           "you're doing, it seems to help. Worth noticing what it is.",
                "suggestion": {"text": "Jot down one thing that helped today.",
                               "action": "journal"},
                "evidence": ["Recent mean %s vs usual %s." % (
                    _unit("mood", mood_d["recent_mean"]),
                    _unit("mood", mood_d["baseline"]["mean"]))],
            })
        elif not insights:
            insights.append({
                "id": "steady", "kind": "steady", "tone": "positive", "metric": "mood",
                "title": "Things look fairly steady",
                "message": "Your mood, sleep and journal tone are close to your usual. "
                           "Keep doing what works for you.",
                "suggestion": {"text": "A short breathing break still helps on busy days.",
                               "action": "breathing"},
                "evidence": ["No dip: CUSUM is below h = %g or fewer than %d recent days "
                             "are under your usual." % (config.CUSUM_H, config.DIP_RUN_MIN)],
            })
    if result["helped_before"] and any(i["kind"] in ("dip", "together") for i in insights):
        acts = [a["activity"] for a in result["helped_before"][:3]]
        insights.append({
            "id": "helped", "kind": "helped", "tone": "positive", "metric": None,
            "title": "What helped on your better days",
            "message": "On days you felt good, you often mentioned %s. Could one of these "
                       "fit into today, even for 10 minutes?" % _join(acts),
            "suggestion": {"text": "Pick one and make it small.", "action": "toolkit"},
            "evidence": ["%s: %d good day(s)" % (a["activity"], a["days"])
                         for a in result["helped_before"][:3]],
        })
    result["insights"] = insights
    return result


def _join(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _evidence(d):
    m = d["metric"]
    ev = []
    run = d["dip_run"]
    if run["length"]:
        ev.append("Last %d day(s): %s, below your usual %s ± %s (%d earlier days); "
                  "threshold %s." % (run["length"], _fmt_vals(run["values"], m),
                                     _unit(m, d["baseline"]["mean"]),
                                     ("%.1f" % d["baseline"]["sd"]) if m != "sentiment"
                                     else "%.2f" % d["baseline"]["sd"],
                                     d["baseline"]["n"], _unit(m, run["threshold"])))
    c = d["cusum"]
    if c["alarm_date"]:
        ev.append("CUSUM crossed its threshold on %s (S = %.1f > h = %g; now %.1f); the "
                  "change seems to have started around %s." % (
                      _fmt_date(c["alarm_date"]), c["alarm_value"], c["h"], c["current"],
                      _fmt_date(c["change_start"])))
    s = d["slope"]
    if s and s["significant_down"]:
        ev.append("%d-day trend: %+.2f per day (t = %.2f, below -%.2f, significant at "
                  "95%%)." % (s["n"], s["slope"], s["t"], s["t_crit"]))
    return ev


def _dip_insight(metric, d):
    run = d["dip_run"]
    n = run["length"]
    span = "for %d days in a row" % n if run["consecutive_days"] else \
        "in your last %d check-ins" % n
    return {
        "id": "mood_dip", "kind": "dip", "tone": "gentle", "metric": "mood",
        "title": "Your mood has dipped %s" % span,
        "message": "Your mood has been lower than your usual (about %s) lately. That's "
                   "really common during busy or stressful weeks, and it's worth being "
                   "gentle with yourself." % _unit("mood", d["baseline"]["mean"]),
        "suggestion": {"text": "Try a 2-minute box-breathing break, then tell one person "
                               "you trust how this week is going.", "action": "breathing"},
        "evidence": _evidence(d),
    }


def _sleep_insight(d, drop):
    recent = d["recent_mean"]
    msg = "You've averaged %.1f h of sleep over your last %d nights" % (recent,
                                                                        d["recent_n"])
    if drop >= 0.5:
        msg += ", about %.1f h less than your usual %.1f h" % (drop, d["baseline"]["mean"])
    msg += ". Less sleep makes everything, including exams, feel harder."
    ev = _evidence(d) or []
    ev.insert(0, "Recent mean %.1f h; gentle flag below %.1f h (adults 18-25 are advised "
                 "%d-%d h)." % (recent, config.SLEEP_LOW_HOURS,
                                config.SLEEP_RECOMMENDED[0], config.SLEEP_RECOMMENDED[1]))
    return {
        "id": "sleep_low", "kind": "sleep", "tone": "gentle", "metric": "sleep",
        "title": "Sleep has been running short",
        "message": msg,
        "suggestion": {"text": "Protect a fixed bedtime tonight; an all-nighter usually "
                               "costs more marks than it earns.", "action": "sleep"},
        "evidence": ev,
    }


def _tone_insight(d, entries):
    from . import sentiment  # local import keeps trends usable on its own
    recent_dates = set(d["dip_run"]["dates"])
    words = {}
    for e in entries:
        if e.get("date") in recent_dates and e.get("text"):
            for t in sentiment.analyse(e["text"])["tokens"]:
                if t["score"] < 0:
                    words[t["text"].lower()] = words.get(t["text"].lower(), 0) + 1
    top = [w for w, _ in sorted(words.items(), key=lambda kv: -kv[1])][:4]
    ev = _evidence(d)
    if top:
        ev.append("Words that pulled the tone down: " + ", ".join("'%s'" % w for w in top)
                  + ".")
    return {
        "id": "tone_dip", "kind": "tone", "tone": "gentle", "metric": "sentiment",
        "title": "Your journal has sounded heavier",
        "message": "Your recent entries use more stressed or tired words than usual. "
                   "Writing it down is already a healthy step.",
        "suggestion": {"text": "Try the 5-4-3-2-1 grounding exercise when thoughts race.",
                       "action": "grounding"},
        "evidence": ev,
    }
