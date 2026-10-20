"""Concept mastery and exam-readiness score, driven by quiz + flashcard history.

For each concept c:
  quiz evidence   q_c = (correct + 1) / (attempts + 2)        (Laplace-smoothed accuracy)
                  w_q = attempts / (attempts + 1)              (more attempts -> more trust)
  card evidence   k_c = mean over the concept's reviewed cards of
                        0.6 * strength(last button) + 0.4 * min(reps, 3) / 3
                  w_k = reviews / (reviews + 1)
  mastery m_c     = (w_q q_c + w_k k_c) / (w_q + w_k)          (0 if no evidence yet)
Readiness = Σ importance_c * m_c / Σ importance_c over the top concepts, where
importance is the concept's keyphrase weight. "Study next" = largest
importance_c * (1 - m_c).
"""
from collections import defaultdict

STRENGTH = {"again": 0.0, "hard": 0.5, "good": 0.8, "easy": 1.0}
TOP_CONCEPTS = 15
LEVELS = [(80, "Exam-ready"), (60, "Almost there"), (30, "Building up"), (0, "Just starting")]


def compute(concepts, cards, card_states, quiz_log, top=TOP_CONCEPTS):
    concepts = [c for c in concepts if c.get("quizzable", True)][:top]
    attempts, correct = defaultdict(int), defaultdict(int)
    for rec in quiz_log:
        attempts[rec["concept"]] += 1
        correct[rec["concept"]] += 1 if rec["correct"] else 0
    cards_by_concept = defaultdict(list)
    for card in cards:
        st = card_states.get(card["id"])
        if st and st.get("reviews"):
            cards_by_concept[card["concept"]].append(st)

    rows, num, den = [], 0.0, 0.0
    for c in concepts:
        key = c["key"]
        att = attempts[key]
        q = (correct[key] + 1) / (att + 2) if att else None
        wq = att / (att + 1)
        sts = cards_by_concept.get(key, [])
        reviews = sum(s["reviews"] for s in sts)
        if sts:
            k = sum(0.6 * STRENGTH.get(s.get("last_rating"), 0) +
                    0.4 * min(s.get("reps", 0), 3) / 3 for s in sts) / len(sts)
        else:
            k = None
        wk = reviews / (reviews + 1)
        if wq + wk > 0:
            m = ((wq * (q or 0)) + (wk * (k or 0))) / (wq + wk)
            status = "learning" if m < 0.6 else ("strong" if m >= 0.8 else "good")
        else:
            m, status = 0.0, "not started"
        imp = c["weight"]
        num += imp * m
        den += imp
        rows.append({"concept": key, "phrase": c["phrase"], "importance": imp,
                     "mastery": round(m, 3), "status": status,
                     "quiz": {"attempts": att, "correct": correct[key],
                              "score": None if q is None else round(q, 3)},
                     "cards": {"reviewed": len(sts), "reviews": reviews,
                               "score": None if k is None else round(k, 3)}})
    readiness = round(100 * num / den) if den else 0
    level = next(name for cut, name in LEVELS if readiness >= cut)
    study_next = sorted(rows, key=lambda r: -(r["importance"] * (1 - r["mastery"])))[:3]
    total_att = sum(attempts.values())
    total_ok = sum(correct.values())
    covered = sum(1 for r in rows if r["status"] != "not started")
    return {
        "readiness": readiness, "level": level, "concepts": rows,
        "study_next": [{"concept": r["concept"], "phrase": r["phrase"],
                        "reason": "importance %.2f, mastery %d%%" % (r["importance"], 100 * r["mastery"])}
                       for r in study_next],
        "totals": {"quiz_attempts": total_att, "quiz_correct": total_ok,
                   "quiz_accuracy": round(total_ok / total_att, 3) if total_att else None,
                   "cards_reviewed": sum(1 for s in card_states.values() if s.get("reviews")),
                   "concepts_covered": covered, "concepts_total": len(rows)},
    }
