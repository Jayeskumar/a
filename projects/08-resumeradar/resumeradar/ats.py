"""ATS-friendliness checker: rule-based, every point traceable to a check."""
import re

from . import blind
from .gaps import bullet_report

_PERSONAL_KINDS = ("age", "gender", "marital", "religion", "family", "photo", "nationality")


def _check(cid, label, points, max_points, status, message, fix=None):
    return {"id": cid, "label": label, "points": round(points, 1), "max": max_points, "status": status,
            "message": message, "fix": fix}


def check(profile, jd=None, match=None):
    """Score 0-100 for how well a plain-text resume survives an applicant tracking system."""
    text = profile["text"]
    checks = []
    c = profile["contact"]
    pts = 5 * c["email"] + 5 * c["phone"] + 5 * (c["linkedin"] or c["github"] or c["portfolio"])
    missing = [k for k, ok in (("email", c["email"]), ("phone", c["phone"]),
                               ("LinkedIn/GitHub", c["linkedin"] or c["github"] or c["portfolio"])) if not ok]
    checks.append(_check("contact", "Contact details", pts, 15, "pass" if not missing else ("warn" if pts >= 5 else "fail"),
                         "All contact details found" if not missing else "Missing: " + ", ".join(missing),
                         None if not missing else "Put email, phone and a LinkedIn/GitHub link in the first two lines"))

    heads = set(profile["sections"])
    need = [("experience/projects", bool({"experience", "projects"} & heads), 10),
            ("education", "education" in heads, 10), ("skills", "skills" in heads, 10)]
    pts = sum(p for _, ok, p in need if ok)
    miss = [n for n, ok, _ in need if not ok]
    summary_ok = "summary" in heads
    pts += 5 if summary_ok else 0
    if not summary_ok:
        miss.append("summary")
    checks.append(_check("sections", "Standard sections", pts, 35, "pass" if not miss else ("warn" if pts >= 20 else "fail"),
                         "Found: " + ", ".join(sorted(h for h in heads if h not in ("header",))),
                         None if not miss else "Add clear headings: " + ", ".join(miss)))

    wc = profile["word_count"]
    if 250 <= wc <= 900:
        pts, st, msg = 10, "pass", "%d words - a solid 1-2 page resume" % wc
    elif 150 <= wc < 250 or 900 < wc <= 1200:
        pts, st, msg = 5, "warn", "%d words - %s" % (wc, "a little thin" if wc < 250 else "a little long")
    else:
        pts, st, msg = 0, "fail", "%d words - %s" % (wc, "too short to show impact" if wc < 150 else "too long")
    checks.append(_check("length", "Length", pts, 10, st, msg,
                         None if st == "pass" else "Aim for 300-800 words: one page for freshers, two at most"))

    br = bullet_report(profile)
    if br["count"]:
        pts = 5 * min(1.0, br["action_pct"] / 80.0) + 10 * min(1.0, br["quantified_pct"] / 60.0)
        st = "pass" if pts >= 12 else ("warn" if pts >= 6 else "fail")
        msg = "%d bullets: %.0f%% start with an action verb, %.0f%% are quantified" % (
            br["count"], br["action_pct"], br["quantified_pct"])
        fix = None if st == "pass" else "Start each bullet with a verb and add a number to at least 60% of them"
    else:
        pts, st, msg, fix = 0, "fail", "No achievement bullets found", "List 3-5 bullets per role or project"
    checks.append(_check("bullets", "Bullet quality", pts, 15, st, msg, fix))

    if jd is not None and match is not None and match.get("must"):
        lit = [r for r in match["must"] if r["kind"] == "direct"]
        alias = [r for r in match["must"] if r["kind"] == "alias"]
        ratio = len(lit) / float(len(match["must"]))
        pts = 15 * ratio
        st = "pass" if ratio >= 0.7 else ("warn" if ratio >= 0.4 else "fail")
        msg = "%d of %d must-have keywords appear literally" % (len(lit), len(match["must"]))
        if alias:
            msg += "; %d only as synonyms (%s)" % (len(alias), ", ".join(r["via"] for r in alias[:3]))
        fix = None if st == "pass" else "Mirror the JD's exact wording for skills you genuinely have"
        checks.append(_check("keywords", "JD keyword match (literal)", pts, 15, st, msg, fix))

    top = sorted(profile["skills"].values(), key=lambda s: -s["count"])[:1]
    overuse = top and top[0]["count"] > 8
    too_many = len(profile["skills"]) > 35
    st = "warn" if (overuse or too_many) else "pass"
    msg = "Keyword density looks natural"
    if overuse:
        msg = "\"%s\" appears %d times - reads as stuffing" % (top[0]["name"], top[0]["count"])
    elif too_many:
        msg = "%d skills listed - recruiters distrust very long lists" % len(profile["skills"])
    checks.append(_check("density", "Keyword stuffing", 5 if st == "pass" else 2, 5, st, msg,
                         None if st == "pass" else "Keep the skills you can defend in an interview"))

    kinds = {s[2] for s in blind.find_spans(text)}
    personal = sorted(blind.KIND_LABELS[k] for k in kinds if k in _PERSONAL_KINDS)
    st = "pass" if not personal else "warn"
    checks.append(_check("personal", "No bias-inviting personal data", 5 if not personal else 0, 5, st,
                         "None found" if not personal else "Found: " + ", ".join(personal),
                         None if not personal else "Remove photo, age/DOB, gender, marital status and family names"))

    lines = [ln for ln in text.split("\n") if ln.strip()]
    tabular = sum(1 for ln in lines if ln.count("|") >= 4 or re.search(r"\s{6,}\S", ln))
    long_lines = sum(1 for ln in lines if len(ln) > 220)
    odd = len(re.findall(r"[^\x00-\x7f₹]", text))
    issues = []
    if tabular >= 3:
        issues.append("table/column layout")
    if long_lines:
        issues.append("%d very long lines" % long_lines)
    if odd > 20:
        issues.append("%d decorative symbols" % odd)
    st = "pass" if not issues else "warn"
    checks.append(_check("format", "Parse-friendly formatting", 5 if not issues else 2, 5, st,
                         "Plain single-column text" if not issues else "Risky: " + ", ".join(issues),
                         None if not issues else "Use a single column with simple bullets; avoid tables and icons"))

    roles = profile["experience"]["entries"]
    if roles:
        dated = sum(1 for r in roles if r["dated"])
        st = "pass" if dated == len(roles) else ("warn" if dated else "fail")
        checks.append(_check("dates", "Dates on every role", 5 * dated / float(len(roles)), 5, st,
                             "%d of %d roles have start-end dates" % (dated, len(roles)),
                             None if st == "pass" else "Add 'Mon YYYY - Mon YYYY' to every role"))

    got = sum(ch["points"] for ch in checks)
    mx = sum(ch["max"] for ch in checks)
    score = round(100.0 * got / mx, 1) if mx else 0.0
    grade = "Good" if score >= 80 else ("Needs work" if score >= 60 else "At risk")
    return {"score": score, "grade": grade, "checks": checks, "points": round(got, 1), "max_points": mx}
