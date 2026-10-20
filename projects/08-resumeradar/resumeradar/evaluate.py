"""Offline evaluation behind the numbers in REPORT.md.

    python -m resumeradar.evaluate          # prints a JSON report

1. Ranking agreement with hand-labelled relevance (0-3) for 20 demo resumes x 3 JDs:
   Spearman rho, NDCG@5 and top-5 overlap, for ResumeRadar and two baselines
   (literal keyword ATS, plain bag-of-words TF-IDF).
2. Skill-extraction precision/recall on a hand-labelled gold set of tricky snippets.
3. Fairness: max score change when identity fields are deleted or swapped, blind vs standard.
4. Latency for screening 100 synthetic resumes.
"""
import json
import math
import re
import statistics
import time

from . import ontology, screening
from .demo import get_demo, synthetic_batch
from .extract import parse_resume
from .jd import parse_jd
from .tfidf import TfidfModel, cosine
from .text import content_terms

# (snippet, expected canonical skills). Lines starting "Skills:" are parsed as a Skills section.
EXTRACTION_GOLD = [
    ("Built REST APIs with DRF and Postgres", {"REST APIs", "Django REST Framework", "PostgreSQL"}),
    ("Skills: JS, TS, ReactJS, Node", {"JavaScript", "TypeScript", "React", "Node.js"}),
    ("I go to the office daily and react quickly to issues", set()),
    ("Wrote services in Go and Python", {"Go", "Python"}),
    ("Hands-on with k8s, docker-compose and CI/CD on AWS", {"Kubernetes", "Docker", "CI/CD", "AWS"}),
    ("Analysed A/B tests using R and SQL", {"A/B Testing", "R", "SQL"}),
    ("Excel at teamwork and communication", {"Teamwork", "Communication"}),
    ("Data Structures & Algorithms, OOPS, DBMS, Operating Systems",
     {"Data Structures", "Algorithms", "OOP", "Database Fundamentals", "Operating Systems"}),
    ("Machine learning with scikit-learn, XGBoost and PyTorch",
     {"Machine Learning", "scikit-learn", "Tree Ensembles", "PyTorch"}),
    ("Dashboards in Power BI (DAX) and Tableau", {"Data Visualization", "Power BI", "Tableau"}),
    ("Spring Boot microservices on Azure with Jenkins", {"Spring Boot", "Microservices", "Azure", "Jenkins"}),
    ("Used C++ and C# for game tools; some C", {"C++", "C#", "C"}),
    ("Experience with the MERN stack", {"MongoDB", "Express.js", "React", "Node.js"}),
    ("Responsible for the rest of the migration", set()),
    ("Designed RESTful endpoints secured with JWT", {"REST APIs", "OAuth & JWT"}),
    ("Strong in pandas, numpy and matplotlib", {"Pandas", "NumPy", "Matplotlib"}),
    ("Containerised Flask apps and deployed them to Heroku", {"Docker", "Flask", "Heroku"}),
    ("Mentored juniors and led a team of 4", {"Leadership"}),
    ("Statistics, hypothesis testing (t-test, chi-square) and regression",
     {"Statistics", "Hypothesis Testing", "Regression Analysis"}),
    ("Wrote unit tests with pytest and jest", {"Unit Testing", "PyTest", "Jest"}),
    ("Android apps in Kotlin; iOS apps in Swift", {"Android", "Kotlin", "iOS", "Swift"}),
    ("Advanced Excel: VLOOKUP, pivot tables, macros", {"Excel"}),
    ("Exposure to GCP and BigQuery", {"GCP", "BigQuery"}),
    ("Built an LLM chatbot with LangChain and a vector database (RAG)", {"LLMs", "LangChain", "RAG"}),
    ("Linux, Bash scripting, Nginx", {"Linux", "Bash", "Nginx"}),
    ("Tested 30 APIs in Postman", {"REST APIs", "Postman"}),
    ("Skills: HTML5, CSS3, SCSS, Bootstrap, jQuery", {"HTML", "CSS", "Sass", "Bootstrap", "jQuery"}),
    ("Spark and Kafka streaming jobs on Hadoop", {"Apache Spark", "Apache Kafka", "Hadoop"}),
]


def ndcg_at_k(order, gains, k=5):
    dcg = sum((2 ** gains[i] - 1) / math.log2(r + 2) for r, i in enumerate(order[:k]))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(r + 2) for r, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def ranking_metrics(scores, labels):
    ids = sorted(labels)
    order = sorted(ids, key=lambda i: (-scores[i], i))
    hand_top = {i for i in ids if labels[i] >= 2}
    k = len(hand_top) or 5
    return {"spearman": round(screening.spearman([scores[i] for i in ids], [labels[i] for i in ids]), 3),
            "ndcg@5": round(ndcg_at_k(order, labels, 5), 3),
            "top5_overlap": round(len(set(order[:k]) & hand_top) / float(k), 3),
            "top5": order[:5]}


def keyword_ats_scores(jd_text, resumes):
    """Literal keyword ATS baseline: share of JD skills whose exact canonical name appears."""
    jd = parse_jd(jd_text)
    out = {}
    for r in resumes:
        got = tw = 0.0
        for req in jd["requirements"]:
            w = 2.0 if req["kind"] == "must" else 1.0
            tw += w
            if any(re.search(r"(?<![\w+#.])%s(?![\w+#])" % re.escape(ontology.name_of(s)), r["text"], re.I)
                   for s in req["skills"]):
                got += w
        out[r["id"]] = round(100.0 * got / tw, 2) if tw else 0.0
    return out


def plain_tfidf_scores(jd_text, resumes):
    """Bag-of-words TF-IDF cosine without the skill ontology."""
    docs = [content_terms(jd_text)] + [content_terms(r["text"]) for r in resumes]
    m = TfidfModel().fit(docs)
    jv = m.vector(docs[0])
    return {r["id"]: round(100 * cosine(jv, m.vector(d)), 2) for r, d in zip(resumes, docs[1:])}


def extraction_eval():
    tp = fp = fn = 0
    errors = []
    base_tp = base_fn = base_fp = 0
    names = [s.name for s in ontology.SKILLS.values()]
    for snippet, expected in EXTRACTION_GOLD:
        got = {info["name"] for info in parse_resume(snippet)["skills"].values()}
        tp += len(got & expected)
        fp += len(got - expected)
        fn += len(expected - got)
        if got != expected:
            errors.append({"text": snippet, "missed": sorted(expected - got), "extra": sorted(got - expected)})
        body = snippet.split(":", 1)[1] if snippet.startswith("Skills:") else snippet
        bgot = {n for n in names if re.search(r"(?<![\w+#.])%s(?![\w+#])" % re.escape(n), body, re.I)}
        base_tp += len(bgot & expected)
        base_fp += len(bgot - expected)
        base_fn += len(expected - bgot)

    def prf(t, p_, n_):
        p = t / float(t + p_) if t + p_ else 1.0
        r = t / float(t + n_) if t + n_ else 1.0
        return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0}

    return {"snippets": len(EXTRACTION_GOLD), "expected_skills": sum(len(e) for _, e in EXTRACTION_GOLD),
            "resumeradar": prf(tp, fp, fn), "keyword_baseline": prf(base_tp, base_fp, base_fn), "errors": errors}


def latency(n=100, repeats=5):
    jd = get_demo()["jds"][0]["text"]
    batch = synthetic_batch(n)
    screening.background_model()
    core, full = [], []
    for _ in range(repeats):
        t = time.perf_counter()
        screening.scores_only(jd, batch, True)
        core.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        screening.screen(jd, batch, blind_mode=True, details=True)
        full.append((time.perf_counter() - t) * 1000)
    return {"resumes": n, "repeats": repeats,
            "score_and_rank_ms": round(statistics.median(core), 1),
            "full_reports_ms": round(statistics.median(full), 1),
            "per_resume_full_ms": round(statistics.median(full) / n, 2)}


def run(include_latency=True):
    d = get_demo()
    rankings = {}
    fairness = {}
    for jd in d["jds"]:
        labels = d["labels"][jd["id"]]
        ours = screening.scores_only(jd["text"], d["resumes"], True)
        rankings[jd["id"]] = {
            "title": jd["title"],
            "resumeradar": ranking_metrics(ours, labels),
            "keyword_ats": ranking_metrics(keyword_ats_scores(jd["text"], d["resumes"]), labels),
            "plain_tfidf": ranking_metrics(plain_tfidf_scores(jd["text"], d["resumes"]), labels),
        }
        b = screening.bias_check(jd["text"], d["resumes"])
        fairness[jd["id"]] = {
            mode: {"max_delta_stripped": b[mode]["vs_stripped"]["max_abs_delta"],
                   "max_delta_swapped": b[mode]["vs_swapped"]["max_abs_delta"],
                   "rank_changes_swapped": b[mode]["vs_swapped"]["rank_changes"],
                   "rank_changes_stripped": b[mode]["vs_stripped"]["rank_changes"],
                   "identical": b[mode]["vs_stripped"]["identical_ranking"] and b[mode]["vs_swapped"]["identical_ranking"]}
            for mode in ("blind", "standard")}
    cases = []
    for rid, jd_id, what in (("R02", "jd-backend", "alias-worded backend (Py, DRF, Postgres, k8s)"),
                             ("R15", "jd-frontend", "alias-worded frontend (ReactJS, JS, TS)"),
                             ("R05", "jd-backend", "keyword-stuffed, no evidence")):
        jd_text = next(j["text"] for j in d["jds"] if j["id"] == jd_id)
        row = {"resume": rid, "jd": jd_id, "what": what, "hand_label": d["labels"][jd_id][rid]}
        for name, fn in (("resumeradar", lambda t, rs: screening.scores_only(t, rs, True)),
                         ("keyword_ats", keyword_ats_scores), ("plain_tfidf", plain_tfidf_scores)):
            sc = fn(jd_text, d["resumes"])
            order = sorted(sc, key=lambda i: (-sc[i], i))
            row[name] = {"rank": order.index(rid) + 1, "score": sc[rid]}
        cases.append(row)
    mean = {}
    for system in ("resumeradar", "keyword_ats", "plain_tfidf"):
        mean[system] = {m: round(sum(rankings[j][system][m] for j in rankings) / len(rankings), 3)
                        for m in ("spearman", "ndcg@5", "top5_overlap")}
    out = {"rankings": rankings, "mean": mean, "case_studies": cases, "extraction": extraction_eval(), "fairness": fairness,
           "ontology": ontology.stats()}
    if include_latency:
        out["latency"] = latency()
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
