"""Gap analysis: missing skills, a prerequisite-ordered learning path and bullet rewrites."""
import heapq
import math
import re

from . import ontology
from .config import HOURS_PER_WEEK
from .scoring import implied_map


class CycleError(ValueError):
    pass


def topological_sort(nodes, prereqs, priority=None):
    """Kahn's algorithm. prereqs: {node: [nodes that must come first]} (restricted to `nodes`).

    Ties are broken by `priority(node)` (smaller first) so the order is deterministic.
    Raises CycleError if the graph has a cycle.
    """
    nodes = list(dict.fromkeys(nodes))
    nodeset = set(nodes)
    prio = priority or (lambda n: (0, str(n)))
    indeg = {n: 0 for n in nodes}
    children = {n: [] for n in nodes}
    for n in nodes:
        for p in prereqs.get(n, ()):
            if p in nodeset:
                indeg[n] += 1
                children[p].append(n)
    heap = [(prio(n), i, n) for i, n in enumerate(nodes) if indeg[n] == 0]
    heapq.heapify(heap)
    order = []
    counter = len(nodes)
    while heap:
        _, _, n = heapq.heappop(heap)
        order.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                counter += 1
                heapq.heappush(heap, (prio(c), counter, c))
    if len(order) != len(nodes):
        stuck = sorted(str(n) for n in nodes if indeg[n] > 0)
        raise CycleError("prerequisite cycle among: " + ", ".join(stuck))
    return order


PROJECT_IDEAS = {
    "Backend": "Build a small {s} service with auth, tests and a Dockerfile",
    "Frontend": "Rebuild a page you use daily with {s}; make it responsive and accessible",
    "Languages": "Solve 20 practice problems in {s}, then port one of your projects to it",
    "Databases": "Model an e-commerce schema in {s} and write 10 analytical queries",
    "Data & Analytics": "Analyse a public dataset with {s} and publish a one-page insight report",
    "Data Engineering": "Build a daily {s} pipeline that loads a public CSV into a warehouse table",
    "ML & AI": "Train and evaluate a {s} model on a public dataset; write up what failed",
    "Cloud & DevOps": "Deploy one of your projects using {s} and document the steps",
    "Testing": "Add {s} tests to an existing project until coverage passes 80%",
    "Mathematics": "Work through a {s} course chapter and apply it to a real dataset",
    "CS Fundamentals": "Explain {s} in a short blog post with a worked example",
    "Mobile": "Ship a two-screen {s} app that calls a public API",
    "Security": "Run a {s} checklist against one of your own projects",
}


def learning_path(targets, known, must_ids=()):
    """Ordered study plan: targets plus missing prerequisites, prerequisites first."""
    known = set(known) | set(implied_map(set(known)))
    need = set()
    reason = {}

    def visit(sid, why):
        for p in ontology.get(sid).prereqs:
            if p not in known:
                reason.setdefault(p, "prerequisite for " + ontology.name_of(sid))
                if p not in need:
                    need.add(p)
                    visit(p, why)

    for t in targets:
        if t in known:
            continue
        need.add(t)
        reason[t] = "must-have in the job description" if t in must_ids else "nice-to-have in the job description"
        visit(t, reason[t])
    must_ids = set(must_ids)
    supports_must = set()
    for t in targets:
        if t in must_ids:
            supports_must.add(t)
            supports_must.update(ontology.prereq_closure(t))

    def prio(sid):
        sk = ontology.get(sid)
        return (0 if sid in supports_must else 1, sk.hours, sk.name)

    prereqs = {sid: ontology.get(sid).prereqs for sid in need}
    order = topological_sort(sorted(need), prereqs, prio)
    steps = []
    cum = 0.0
    for i, sid in enumerate(order):
        sk = ontology.get(sid)
        cum += sk.hours
        idea = PROJECT_IDEAS.get(sk.category, "Use {s} in a small project and add it to your resume")
        steps.append({"step": i + 1, "id": sid, "name": sk.name, "category": sk.category, "hours": sk.hours,
                      "cumulative_hours": cum, "week": int(math.ceil(cum / HOURS_PER_WEEK)),
                      "why": reason.get(sid, ""), "is_target": sid in targets,
                      "requires": [ontology.name_of(p) for p in sk.prereqs if p in need],
                      "practice": idea.format(s=sk.name)})
    return {"steps": steps, "total_hours": cum, "weeks": int(math.ceil(cum / HOURS_PER_WEEK)) if cum else 0,
            "hours_per_week": HOURS_PER_WEEK,
            "method": "Prerequisite closure + Kahn topological sort; ties: must-have first, then quickest win"}


# --------------------------------------------------------------------------- bullets
ACTION_VERBS = frozenset("""
accelerated achieved added analysed analyzed architected audited authored automated benchmarked boosted built
championed cleaned coded collaborated compiled configured constructed containerised containerized converted
coordinated created cut debugged decreased defined delivered deployed designed developed devised diagnosed
documented drove earned eliminated enabled engineered enhanced established evaluated executed expanded
extracted facilitated fixed forecasted formulated founded generated grew guided halved headed identified
implemented improved increased initiated instrumented integrated introduced invented launched led lifted
maintained managed mentored merged migrated modelled modeled modernised modernized monitored negotiated
optimised optimized orchestrated organised organized overhauled owned parallelized partnered pioneered planned
predicted prepared presented processed produced programmed prototyped published raised ran rebuilt reduced
redesigned refactored reengineered resolved restructured revamped saved scaled scripted secured served set
shipped simplified slashed solved spearheaded standardised standardized streamlined structured supervised
taught tested trained transformed translated trimmed tuned upgraded validated visualised visualized won wrote
analyse analyze build create deliver deploy design develop implement improve lead maintain manage migrate
optimise optimize own reduce scale ship test train write automate
""".split())
WEAK_PHRASES = ["responsible for", "worked on", "working on", "involved in", "helped", "assisted", "participated in",
                "tasked with", "duties included", "in charge of", "was part of", "part of a team", "handled",
                "did ", "various", "etc", "familiar with", "exposure to", "learned", "learnt", "tried to",
                "looked after", "took care of"]
_WEAK_LEAD = re.compile(r"^(?:i\s+)?(?:was\s+)?(?:responsible for|worked on|working on|involved in|helped(?: to| with| in)?|"
                        r"assisted(?: in| with)?|participated in|tasked with|duties included|in charge of|"
                        r"was part of|part of a team (?:that|which)|handled|did|looked after|took care of)\s+", re.I)
_NUMBER = re.compile(r"\d|%|\bpercent\b|\bdoubled\b|\bhalved\b|\btripled\b|\bx\b", re.I)
_PASSIVE = re.compile(r"\b(?:was|were|been|being|is|are)\s+\w+ed\b(?:\s+by\b)?", re.I)
_FIRST_PERSON = re.compile(r"\b(?:i|me|my|mine|myself)\b", re.I)
_IRREGULAR = {"building": "Built", "writing": "Wrote", "making": "Made", "leading": "Led", "running": "Ran",
              "setting": "Set up", "doing": "Delivered", "getting": "Got", "taking": "Took", "bringing": "Brought",
              "testing": "Tested", "fixing": "Fixed", "bug": "Fixed"}
_TOPIC_VERB = [
    (re.compile(r"\btest|qa\b|bug", re.I), "Tested"),
    (re.compile(r"\bdatabase|schema|table", re.I), "Designed"),
    (re.compile(r"\bdashboard|report|mis\b|analysis|data\b", re.I), "Built"),
    (re.compile(r"\bdeploy|release|pipeline|ci\b", re.I), "Automated"),
    (re.compile(r"\bapi|backend|service|website|page|app\b|feature|component|database", re.I), "Developed"),
    (re.compile(r"\bteam|intern|junior", re.I), "Led"),
    (re.compile(r"\bcustomer|client|call|email", re.I), "Resolved"),
    (re.compile(r"\bdocument", re.I), "Documented"),
]


def _first_word(text):
    m = re.match(r"\s*([A-Za-z]+)", text)
    return m.group(1).lower() if m else ""


def _gerund_to_past(word):
    low = word.lower()
    if low in _IRREGULAR:
        return _IRREGULAR[low]
    if low.endswith("ing") and len(low) > 5:
        stem = low[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "ls":
            stem = stem[:-1]
        elif stem.endswith(("at", "iz", "is", "ur", "ar", "ov", "ag", "ag", "uc", "ut", "rv")):
            stem += "e"
        return (stem + "ed").capitalize()
    return None


_ACTIVITY = {"deployment": "Deployed", "deployments": "Deployed", "testing": "Tested", "development": "Developed",
             "migration": "Migrated", "analysis": "Analysed", "design": "Designed", "maintenance": "Maintained",
             "implementation": "Implemented", "optimization": "Optimised", "optimisation": "Optimised",
             "automation": "Automated", "documentation": "Documented", "integration": "Integrated",
             "management": "Managed", "reporting": "Reported on", "support": "Supported", "debugging": "Debugged",
             "research": "Researched", "training": "Trained", "coordination": "Coordinated", "cleaning": "Cleaned",
             "monitoring": "Monitored", "planning": "Planned"}
_TEAM = re.compile(r"^(?:the|my|our)?\s*team\b\s*", re.I)


def suggest_rewrite(text):
    """Template rewrite: strong past-tense verb first, weak lead removed, impact placeholder added."""
    body = text.strip().rstrip(".")
    body = _WEAK_LEAD.sub("", body, count=1)
    body = re.sub(r"^(?:i|we)\s+", "", body, flags=re.I).strip()
    if not body:
        return "Delivered [what] - [add impact: e.g. cut X by N%, for N users, saving N hours/week]"
    words = body.split()
    first = words[0].lower().strip(",")
    bugs = re.search(r"\bbug[- ]?fix(?:ing|es)?\b|\bfix(?:ing)? bugs\b", body, re.I)
    if first in ACTION_VERBS or (first.endswith("ed") and len(first) > 4):
        rewrite = words[0].capitalize() + body[len(words[0]):]
    elif _gerund_to_past(first):
        rest = body[len(words[0]):]
        if bugs:
            rest = re.sub(r"\s*(?:and\s+)?(?:bug[- ]?fix(?:ing|es)?|fix(?:ing)? bugs)\b", "", rest, flags=re.I)
            rewrite = _gerund_to_past(first) + (rest if rest.strip() else " [feature/module]") + " and fixed [N] bugs"
        else:
            rewrite = _gerund_to_past(first) + (rest if rest.strip() else " [what]")
    else:
        act = next((w for w in re.findall(r"[A-Za-z]+", body) if w.lower() in _ACTIVITY), None)
        if act:
            verb = _ACTIVITY[act.lower()]
            obj = re.sub(r"\s*\b(?:in|on|with|of|for)?\s*(?:data\s+)?%s\b(?:\s+of)?" % re.escape(act), " ", body,
                         count=1, flags=re.I).strip()
            obj = re.sub(r"\s{2,}", " ", obj)
            if not obj:
                rewrite = verb + " [what]"
            elif _TEAM.match(obj):
                rest = _TEAM.sub("", obj).strip()
                rewrite = verb + " [what]" + (" " + rest if rest else "") + " with the team"
            else:
                rewrite = verb + " " + obj
        else:
            verb = next((v for rx, v in _TOPIC_VERB if rx.search(body)), "Delivered")
            w0 = words[0]
            keep_case = (w0.lower(),) in ontology.ALIAS_INDEX or not w0[1:].islower()
            rewrite = verb + " " + (body if keep_case else body[0].lower() + body[1:])
    rewrite = re.sub(r"\s{2,}", " ", rewrite).strip()
    if not _NUMBER.search(rewrite):
        rewrite += " - [add impact: e.g. cut X by N%, for N users, saving N hours/week]"
    return rewrite


def analyze_bullet(text):
    issues = []
    score = 100
    low = text.lower()
    first = _first_word(text)
    has_verb = first in ACTION_VERBS or (first.endswith("ed") and len(first) > 4 and not first.endswith("eed"))
    if not has_verb:
        issues.append("Start with a strong action verb (Built, Reduced, Automated...)")
        score -= 30
    weak = [p.strip() for p in WEAK_PHRASES if p in low]
    if weak:
        issues.append("Weak phrase: \"%s\" hides what you actually did" % weak[0])
        score -= 25
    if not _NUMBER.search(text):
        issues.append("No quantified impact - add a number (%, users, time saved, scale)")
        score -= 25
    words = len(text.split())
    if words < 6:
        issues.append("Too short (%d words) - say what, how and the result" % words)
        score -= 15
    elif words > 35:
        issues.append("Too long (%d words) - keep bullets under ~30 words" % words)
        score -= 10
    if _FIRST_PERSON.search(text):
        issues.append("Drop first-person words (I, my)")
        score -= 10
    if _PASSIVE.search(text):
        issues.append("Passive voice - say who did it")
        score -= 10
    score = max(0, score)
    return {"text": text, "score": score, "issues": issues,
            "rewrite": suggest_rewrite(text) if issues else None,
            "quantified": bool(_NUMBER.search(text)), "action_verb": has_verb}


def bullet_report(profile, limit=6):
    analysed = [analyze_bullet(b["text"]) for b in profile["bullets"]]
    if not analysed:
        return {"count": 0, "avg_score": 0, "quantified_pct": 0, "action_pct": 0, "weakest": [], "strongest": None}
    n = float(len(analysed))
    weakest = sorted([a for a in analysed if a["issues"]], key=lambda a: (a["score"], a["text"]))[:limit]
    strongest = max(analysed, key=lambda a: (a["score"], -len(a["text"])))
    return {"count": len(analysed),
            "avg_score": round(sum(a["score"] for a in analysed) / n, 1),
            "quantified_pct": round(100 * sum(a["quantified"] for a in analysed) / n, 1),
            "action_pct": round(100 * sum(a["action_verb"] for a in analysed) / n, 1),
            "weakest": weakest,
            "strongest": strongest if strongest["score"] >= 75 else None}


def gap_report(profile, jd, match):
    missing_must = [r for r in match["must"] if r["credit"] < 1.0]
    missing_nice = [r for r in match["nice"] if r["credit"] < 1.0]
    req_by_id = {r["id"]: r for r in jd["requirements"]}
    targets = []
    must_ids = []
    for r in missing_must + missing_nice:
        if r["credit"] >= 0.8:
            continue  # implied strongly enough; advise to make it explicit instead
        opts = req_by_id[r["id"]]["skills"]
        pick = min(opts, key=lambda s: (ontology.get(s).hours, s))
        targets.append(pick)
        if r in missing_must:
            must_ids.append(pick)
    path = learning_path(targets, set(profile["skills"]), must_ids)
    advice = []
    for r in missing_must + missing_nice:
        if r["kind"] == "implied":
            advice.append("You likely know %s (you use %s) - name it explicitly in your skills and bullets."
                          % (r["skill_name"], r["via"]))
        elif r["kind"] == "related":
            advice.append("You have %s, which is close to %s - highlight transferable work and do a small %s project."
                          % (r["via"], r["skill_name"], r["skill_name"]))
    for r in match["must"] + match["nice"]:
        if r["kind"] == "alias":
            advice.append("Write \"%s\" as the JD does (you wrote \"%s\") - literal-match ATS tools miss synonyms."
                          % (r["skill_name"], r["via"]))
    return {"missing_must": [r["label"] for r in missing_must if r["credit"] == 0],
            "partial_must": [{"label": r["label"], "kind": r["kind"], "via": r["via"], "credit": r["credit"]}
                             for r in missing_must if r["credit"] > 0],
            "missing_nice": [r["label"] for r in missing_nice if r["credit"] == 0],
            "learning_path": path,
            "advice": advice[:8],
            "bullets": bullet_report(profile)}
