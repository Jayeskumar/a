"""Auto-generated shift-handover summaries (plain text, printable)."""

from . import config, news2
from .simulator import clock_label

BAND_WORD = {"low": "LOW", "low_medium": "LOW-MEDIUM", "medium": "MEDIUM", "high": "HIGH"}


def last_change(history):
    """Most recent reading where the aggregate score changed. Returns dict or None."""
    for i in range(len(history) - 1, 0, -1):
        cur, prev = history[i], history[i - 1]
        if cur["score"] != prev["score"]:
            changed = [k for k in cur["points"] if cur["points"][k] != prev["points"].get(k)]
            return {"t": cur["t"], "from": prev["score"], "to": cur["score"],
                    "params": changed}
    return None


def score_hours_ago(history, hours):
    if not history:
        return None
    target = history[-1]["t"] - hours
    best = None
    for r in history:
        if r["t"] <= target + 1e-9:
            best = r
    return best


def patient_summary(profile, history, trend_result):
    """Return (structured dict, text) for one patient."""
    if not history:
        return {}, ""
    last = history[-1]
    full = news2.calculate(last)
    ago = score_hours_ago(history, 4)
    change = last_change(history)
    contributors = [p for p in sorted(full["parameters"], key=lambda p: -p["points"])
                    if p["points"] > 0]
    contrib_txt = ", ".join("%s %s%s (+%d)" % (p["label"], p["value"],
                                               (" " + p["unit"]) if p["unit"] else "",
                                               p["points"]) for p in contributors) or \
        "all parameters in normal range"
    head = "Bed %d - %s (%d%s) - %s" % (profile["bed"], profile["name"], profile["age"],
                                        profile["sex"], profile["diagnosis"])
    if profile.get("scale") == 2:
        head += " [SpO2 Scale 2]"
    lines = [head,
             "  NEWS2 %d (%s risk) at %s. Contributors: %s." % (
                 last["score"], BAND_WORD[full["band"]], clock_label(last["t"]), contrib_txt)]
    if ago is not None and ago is not last:
        delta = last["score"] - ago["score"]
        trend_word = "up" if delta > 0 else ("down" if delta < 0 else "unchanged")
        lines.append("  4-hour trend: %d -> %d (%s%s). Trend detector: %s." % (
            ago["score"], last["score"], trend_word,
            (" %+d" % delta) if delta else "", trend_result.get("reason", "n/a")))
    if change:
        names = ", ".join(news2.PARAM_META[k][0] for k in change["params"]) or "-"
        lines.append("  Last change: %d -> %d at %s (%s)." % (
            change["from"], change["to"], clock_label(change["t"]), names))
    else:
        lines.append("  Last change: no change in score this shift.")
    lines.append("  Monitoring: %s. Action: %s" % (full["frequency"], full["response"]))
    if trend_result.get("early_warning"):
        lines.append("  ! EARLY WARNING: projected NEWS2 %s within %g h - re-assess now." % (
            trend_result.get("projected_score"), config.TREND_HORIZON_H))
    data = {"id": profile["id"], "bed": profile["bed"], "name": profile["name"],
            "score": last["score"], "band": full["band"],
            "score_4h_ago": ago["score"] if ago else None, "last_change": change,
            "frequency": full["frequency"], "early_warning": bool(
                trend_result.get("early_warning"))}
    return data, "\n".join(lines)
