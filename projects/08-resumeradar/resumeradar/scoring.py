"""Resume-vs-JD match score with a transparent weighted breakdown.

    score = 100 * sum_c  w_c * s_c / sum_c w_c        (c over the components that apply)

    must_have     weighted mean of requirement credit (1 exact/alias, 0.8/0.6 implied, 0.4 related)
    nice_to_have  same, over nice-to-have requirements
    semantic      min(1, cosine(TF-IDF(resume), TF-IDF(JD)) / SEMANTIC_COS_FULL)
    experience    min(1, relevant_years / required_years)   (1 if nothing is required)
    education     0.7 * level fit + 0.3 * field fit           (never the college name)
    evidence      weighted share of JD requirements proven in experience/projects, not just listed
"""
import re

from . import ontology
from .config import (COMPONENT_LABELS, IMPLIED_CREDIT_DIRECT, IMPLIED_CREDIT_INDIRECT, NICE_EVIDENCE_WEIGHT,
                     RELATED_CREDIT, REVIEW_AT,
                     SEMANTIC_COS_FULL, SHORTLIST_AT, STUFFING_MAX_EVIDENCE, STUFFING_MIN_SKILLS, WEIGHTS)
from .extract import TECH_FIELDS, summarize_experience
from .text import surface_forms
from .tfidf import cosine, top_contributions

_ROLE_WORDS = frozenset("developer engineer analyst backend frontend programmer architect sde devops data "
                        "software web ui full stack fullstack scientist ml".split())


def implied_map(skill_ids):
    """{prereq_id: (via_skill, depth)} for skills implied by what the candidate has."""
    out = {}
    for sid in skill_ids:
        for p, depth in ontology.prereq_closure(sid).items():
            if p in skill_ids:
                continue
            if p not in out or depth < out[p][1]:
                out[p] = (sid, depth)
    return out


def skill_credit(sid, cand_skills, implied, families):
    """(credit, kind, via) for one JD skill against a candidate."""
    if sid in cand_skills:
        info = cand_skills[sid]
        canonical = ontology.name_of(sid).lower()
        if any(s.lower() == canonical for s in info["surfaces"]):
            return 1.0, "direct", ontology.name_of(sid)
        return 1.0, "alias", info["surfaces"][0]
    if sid in implied:
        via, depth = implied[sid]
        credit = IMPLIED_CREDIT_DIRECT if depth == 1 else IMPLIED_CREDIT_INDIRECT
        return credit, "implied", ontology.name_of(via)
    fam = ontology.get(sid).family
    if fam and fam in families:
        return RELATED_CREDIT, "related", ontology.name_of(families[fam])
    return 0.0, "missing", None


def requirement_results(reqs, cand_skills, implied, families):
    out = []
    for r in reqs:
        best = (0.0, "missing", None, r["skills"][0])
        for sid in r["skills"]:
            c, kind, via = skill_credit(sid, cand_skills, implied, families)
            if c > best[0]:
                best = (c, kind, via, sid)
        credit, kind, via, sid = best
        out.append({"id": r["id"], "label": r["label"], "skill": sid, "skill_name": ontology.name_of(sid),
                    "options": [ontology.name_of(s) for s in r["skills"]], "weight": r["weight"],
                    "core": r.get("core", False), "credit": round(credit, 2), "kind": kind, "via": via,
                    "evidence": bool(sid in cand_skills and cand_skills[sid]["evidence"])})
    return out


def _weighted_mean(results):
    tw = sum(r["weight"] for r in results)
    if not tw:
        return None
    return sum(r["weight"] * r["credit"] for r in results) / tw


def _describe_reqs(results):
    got = [r for r in results if r["credit"] >= 1.0]
    part = [r for r in results if 0 < r["credit"] < 1.0]
    miss = [r for r in results if r["credit"] == 0]
    bits = ["%d of %d fully met" % (len(got), len(results))]
    if part:
        bits.append("partial: " + ", ".join("%s (%s %s)" % (r["skill_name"], r["kind"], r["via"]) for r in part[:3]))
    if miss:
        bits.append("missing: " + ", ".join(r["label"] for r in miss[:4]))
    return "; ".join(bits)


def education_fit(edu, req):
    level = edu.get("level")
    need = req.get("level", 0)
    if need <= 0:
        lvl = 1.0
        lvl_txt = "no minimum degree"
    elif level is None:
        lvl, lvl_txt = 0.0, "no degree found (needs %s)" % req.get("label")
    elif level >= need:
        lvl, lvl_txt = 1.0, "%s meets %s" % (edu.get("degree"), req.get("label"))
    elif level == need - 1:
        lvl, lvl_txt = 0.5, "%s is one level below %s" % (edu.get("degree"), req.get("label"))
    else:
        lvl, lvl_txt = 0.0, "%s below %s" % (edu.get("degree"), req.get("label"))
    field = edu.get("field")
    fields = req.get("fields") or []
    if req.get("any_field"):
        fit, ftxt = 1.0, "any field accepted"
    elif field and field in fields:
        fit, ftxt = 1.0, "%s matches" % field
    elif req.get("equivalent_ok"):
        fit, ftxt = 0.6, "equivalent experience accepted"
    elif req.get("related_ok") and field in TECH_FIELDS:
        fit, ftxt = 0.6, "%s counted as related" % field
    else:
        fit, ftxt = 0.2, "%s not in %s" % (field or "field unknown", ", ".join(fields))
    return 0.7 * lvl + 0.3 * fit, "%s; %s" % (lvl_txt, ftxt)


def _is_relevant_role(entry, jd_skill_ids, title_words):
    if set(entry.get("skills", ())) & jd_skill_ids:
        return True
    words = set(re.findall(r"[a-z]+", entry.get("title", "").lower()))
    return bool(words & title_words & _ROLE_WORDS)


def recommendation(score):
    if score >= SHORTLIST_AT:
        return {"level": "strong", "label": "Strong match - shortlist", "rule": "score >= %d" % SHORTLIST_AT}
    if score >= REVIEW_AT:
        return {"level": "review", "label": "Potential - human review", "rule": "%d <= score < %d" % (REVIEW_AT, SHORTLIST_AT)}
    return {"level": "low", "label": "Low match - send coaching", "rule": "score < %d" % REVIEW_AT}


def score_profile(profile, jd, resume_vec, jd_vec):
    """Full explainable match of one parsed resume against one parsed JD."""
    cand = profile["skills"]
    implied = implied_map(set(cand))
    families = {}
    for sid in cand:
        fam = ontology.get(sid).family
        if fam and fam not in families:
            families[fam] = sid
    must = requirement_results(jd["must"], cand, implied, families)
    nice = requirement_results(jd["nice"], cand, implied, families)
    comps = {}
    detail = {}
    m = _weighted_mean(must)
    if m is not None:
        comps["must_have"] = m
        detail["must_have"] = _describe_reqs(must)
    n = _weighted_mean(nice)
    if n is not None:
        comps["nice_to_have"] = n
        detail["nice_to_have"] = _describe_reqs(nice)

    cos = cosine(resume_vec, jd_vec)
    comps["semantic"] = min(1.0, cos / SEMANTIC_COS_FULL)
    terms = top_contributions(resume_vec, jd_vec, 8)
    words = surface_forms(profile["text"], [t for t, _ in terms if not t.startswith("skill:")])
    shared = [(ontology.name_of(t[6:]) if t.startswith("skill:") else words.get(t, t), round(c, 4)) for t, c in terms]
    detail["semantic"] = "cosine %.3f (full credit at %.2f); top shared terms: %s" % (
        cos, SEMANTIC_COS_FULL, ", ".join(t for t, _ in shared[:5]) or "none")

    jd_ids = set(jd["skill_ids"])
    title_words = set(re.findall(r"[a-z]+", jd["title"].lower()))
    entries = profile["experience"]["entries"]
    rel = summarize_experience(entries, profile.get("claims", []),
                               relevant_filter=lambda e: _is_relevant_role(e, jd_ids, title_words))
    total_years = profile["experience"]["years"]
    rel_years = rel["years"] if entries else total_years
    need = jd["min_years"]
    not_scored = []
    if need <= 0:
        not_scored.append({"key": "experience", "label": COMPONENT_LABELS["experience"],
                           "reason": "JD sets no minimum experience (%.1f relevant yrs found)" % rel_years})
    else:
        comps["experience"] = min(1.0, rel_years / need)
        detail["experience"] = "%.1f relevant of %.1f total yrs vs %.0f+ required" % (rel_years, total_years, need)

    if jd["education"].get("level", 0) <= 0 and not jd["education"].get("fields"):
        not_scored.append({"key": "education", "label": COMPONENT_LABELS["education"],
                           "reason": "JD sets no degree requirement"})
    else:
        ed, ed_txt = education_fit(profile["education"], jd["education"])
        comps["education"] = ed
        detail["education"] = ed_txt

    # Evidence = weighted share of ALL JD requirements that are matched and shown in real work
    # (experience/projects/certifications), so one proven skill cannot earn full marks.
    direct = [r for r in must + nice if r["kind"] in ("direct", "alias")]
    proven = [r for r in direct if r["evidence"]]
    ev_w = [(r["weight"] if r in must else NICE_EVIDENCE_WEIGHT) for r in must + nice]
    ev_total = sum(ev_w)
    ev = sum(w for r, w in zip(must + nice, ev_w) if r in proven) / ev_total if ev_total else 0.0
    detail["evidence"] = "%d of %d JD skills proven in experience/projects (%d only listed)" % (
        len(proven), len(must) + len(nice), len(direct) - len(proven))
    if ev_total:
        comps["evidence"] = ev
    else:
        not_scored.append({"key": "evidence", "label": COMPONENT_LABELS["evidence"],
                           "reason": "JD lists no skills from the ontology"})
    listed_only_ratio = (len(proven) / float(len(direct))) if direct else 0.0

    active = [k for k in WEIGHTS if k in comps]
    wsum = sum(WEIGHTS[k] for k in active)
    breakdown = []
    total = 0.0
    for k in active:
        w = WEIGHTS[k] / wsum
        pts = 100.0 * w * comps[k]
        total += pts
        breakdown.append({"key": k, "label": COMPONENT_LABELS[k], "weight": round(w, 4),
                          "score": round(comps[k], 4), "points": round(pts, 2), "max_points": round(100 * w, 2),
                          "detail": detail[k]})
    total = round(total, 1)

    flags = []
    if len(cand) >= STUFFING_MIN_SKILLS and listed_only_ratio <= STUFFING_MAX_EVIDENCE:
        flags.append({"type": "stuffing", "text": "Keyword stuffing suspected: %d skills listed, only %.0f%% of "
                      "matched JD skills shown in real work" % (len(cand), listed_only_ratio * 100)})
    alias_hits = [r for r in must + nice if r["kind"] == "alias"]
    if alias_hits:
        flags.append({"type": "alias", "text": "Matched via synonyms a keyword ATS would miss: " + ", ".join(
            "%s = %s" % (r["via"], r["skill_name"]) for r in alias_hits[:5])})
    if entries and not any(e["dated"] for e in entries):
        flags.append({"type": "dates", "text": "Experience has no dates; years could not be verified"})

    rec = recommendation(total)
    if not jd["requirements"]:
        flags.append({"type": "jd", "text": "The JD names no skills ResumeRadar knows, so only text similarity was "
                      "scored. Add a requirements list for a meaningful ranking."})
        rec = {"level": "review", "label": "Review manually - JD lists no known skills", "rule": "no JD skills parsed"}

    extra = [{"id": s, "name": cand[s]["name"], "category": cand[s]["category"]} for s in cand
             if s not in jd_ids and not ontology.is_soft(s)]
    return {
        "score": total,
        "recommendation": rec,
        "breakdown": breakdown,
        "not_scored": not_scored,
        "must": must,
        "nice": nice,
        "soft": [{"name": ontology.name_of(s), "present": s in cand} for s in jd.get("soft", [])],
        "extra_skills": extra[:15],
        "semantic": {"cosine": round(cos, 4), "shared_terms": shared},
        "experience": {"total_years": total_years, "relevant_years": rel_years, "required": need,
                       "source": profile["experience"]["source"]},
        "flags": flags,
    }
