"""Bulk screening, single-resume analysis and the blind-mode bias check."""
import time

from . import ats, blind, gaps, interview
from .extract import parse_resume, public_profile
from .jd import bias_lint, parse_jd, public_jd
from .scoring import score_profile
from .tfidf import TfidfModel, doc_terms

_BG = {}


def background_model():
    """IDF background fitted once on the bundled demo corpus (masked), so single-resume
    scores do not swing with the size of the request."""
    if "m" not in _BG:
        from .demo import get_demo
        d = get_demo()
        m = TfidfModel()
        for doc in [j["text"] for j in d["jds"]] + [r["text"] for r in d["resumes"]]:
            txt = blind.mask(doc)["text"]
            m.add(doc_terms(txt, parse_resume(txt)["skills"]))
        _BG["m"] = m
    return _BG["m"]


def _prepare(jd_text, resumes, blind_mode):
    jd_src = blind.mask(jd_text)["text"] if blind_mode else jd_text
    jd = parse_jd(jd_src)
    jd["bias_flags"] = bias_lint(jd_text)  # lint the JD as written, not the masked copy
    jd_skills = {sid: {"count": 1} for sid in jd["skill_ids"]}
    jd_terms = doc_terms(jd["text"], jd_skills)
    items = []
    for r in resumes:
        raw = r["text"]
        masked = blind.mask(raw) if blind_mode else None
        text = masked["text"] if masked else raw
        prof = parse_resume(text)
        items.append({"id": r["id"], "raw": raw, "masked": masked, "profile": prof,
                      "terms": doc_terms(prof["text"], prof["skills"]), "meta": r})
    model = background_model().copy()
    model.add(jd_terms)
    for it in items:
        model.add(it["terms"])
    jd_vec = model.vector(jd_terms)
    return jd, jd_vec, items, model


def _rank(rows):
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def scores_only(jd_text, resumes, blind_mode=True):
    """{id: score} - the core pipeline, used by the bias check and benchmarks."""
    jd, jd_vec, items, model = _prepare(jd_text, resumes, blind_mode)
    return {it["id"]: score_profile(it["profile"], jd, model.vector(it["terms"]), jd_vec)["score"] for it in items}


def analyze_item(it, jd, jd_vec, model, blind_mode):
    match = score_profile(it["profile"], jd, model.vector(it["terms"]), jd_vec)
    prof = it["profile"]
    report = {
        "id": it["id"],
        "score": match["score"],
        "match": match,
        "profile": public_profile(prof),
        "gaps": gaps.gap_report(prof, jd, match),
        "ats": ats.check(parse_resume(it["raw"]) if it["masked"] else prof, jd, match),
        "interview": interview.generate(prof, jd, match),
        "blind": blind_mode,
    }
    if it["masked"]:
        report["masked_text"] = it["masked"]["text"]
        report["redactions"] = {"counts": it["masked"]["counts"], "total": it["masked"]["total"],
                                "items": it["masked"]["redactions"][:40]}
    else:
        report["masked_text"] = None
        report["redactions"] = None
    return report


def screen(jd_text, resumes, blind_mode=True, details=True):
    t0 = time.perf_counter()
    jd, jd_vec, items, model = _prepare(jd_text, resumes, blind_mode)
    rows = []
    for idx, it in enumerate(items):
        if details:
            rep = analyze_item(it, jd, jd_vec, model, blind_mode)
        else:
            rep = {"id": it["id"], "match": score_profile(it["profile"], jd, model.vector(it["terms"]), jd_vec)}
            rep["score"] = rep["match"]["score"]
        m = rep["match"]
        meta = it["meta"]
        rep["display_name"] = ("Candidate %02d" % (idx + 1)) if blind_mode else (meta.get("name") or meta["id"])
        rep["summary"] = {
            "must_met": sum(1 for r in m["must"] if r["credit"] >= 1.0),
            "must_partial": sum(1 for r in m["must"] if 0 < r["credit"] < 1.0),
            "must_total": len(m["must"]),
            "years": m["experience"]["relevant_years"],
            "top_missing": [r["label"] for r in m["must"] if r["credit"] == 0][:3],
            "recommendation": m["recommendation"],
            "ats": rep["ats"]["score"] if details else None,
            "flags": [f["type"] for f in m["flags"]],
        }
        rows.append(rep)
    _rank(rows)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return {"jd": public_jd(jd), "blind": blind_mode, "count": len(rows), "elapsed_ms": round(elapsed, 1),
            "ranking": rows}


def analyze(resume_text, jd_text, blind_mode=True):
    res = screen(jd_text, [{"id": "you", "text": resume_text, "name": "You"}], blind_mode=blind_mode)
    out = res["ranking"][0]
    out["jd"] = res["jd"]
    out["elapsed_ms"] = res["elapsed_ms"]
    return out


# --------------------------------------------------------------------------- bias check
def _avg_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(a, b):
    """Spearman rank correlation with average ranks for ties (Pearson on ranks)."""
    n = len(a)
    if n < 2:
        return 1.0
    ra, rb = _avg_ranks(a), _avg_ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    if va == 0 or vb == 0:
        return 1.0 if va == vb else 0.0
    return cov / (va * vb) ** 0.5


def _order(scores):
    return [k for k, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def compare(base, other, k=5):
    ids = sorted(base)
    a = [base[i] for i in ids]
    b = [other[i] for i in ids]
    oa, ob = _order(base), _order(other)
    deltas = {i: round(other[i] - base[i], 2) for i in ids}
    return {
        "spearman": round(spearman(a, b), 4),
        "identical_ranking": oa == ob,
        "rank_changes": sum(1 for i in ids if oa.index(i) != ob.index(i)),
        "top_k_identical": oa[:k] == ob[:k],
        "max_abs_delta": round(max(abs(d) for d in deltas.values()) if deltas else 0.0, 2),
        "mean_abs_delta": round(sum(abs(d) for d in deltas.values()) / max(1, len(deltas)), 3),
        "deltas": deltas,
    }


def bias_check(jd_text, resumes):
    """Score every resume as-is, with identity fields deleted, and with identity swapped -
    in blind mode and in standard mode - and compare the rankings."""
    t0 = time.perf_counter()
    stripped = [dict(r, text=blind.strip(r["text"])) for r in resumes]
    swapped = [dict(r, text=blind.counterfactual(r["text"], r["id"])) for r in resumes]
    out = {}
    for mode, flag in (("blind", True), ("standard", False)):
        base = scores_only(jd_text, resumes, flag)
        s_scores = scores_only(jd_text, stripped, flag)
        c_scores = scores_only(jd_text, swapped, flag)
        vs_s = compare(base, s_scores)
        vs_c = compare(base, c_scores)
        rows = []
        order = _order(base)
        for rid in order:
            rows.append({"id": rid, "score": base[rid], "stripped": s_scores[rid], "swapped": c_scores[rid],
                         "rank": order.index(rid) + 1,
                         "rank_stripped": _order(s_scores).index(rid) + 1,
                         "rank_swapped": _order(c_scores).index(rid) + 1})
        for d in (vs_s, vs_c):
            d.pop("deltas", None)
        out[mode] = {"vs_stripped": vs_s, "vs_swapped": vs_c, "rows": rows,
                     "invariant": vs_s["identical_ranking"] and vs_c["identical_ranking"]
                     and vs_s["max_abs_delta"] == 0 and vs_c["max_abs_delta"] == 0}
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    out["explanation"] = ("Each resume is scored three ways: as submitted, with identity fields deleted, and with "
                          "identity swapped (name and pronouns to the other gender, top college <-> government "
                          "college, age +6, different city). A fair screen must give identical rankings.")
    return out
