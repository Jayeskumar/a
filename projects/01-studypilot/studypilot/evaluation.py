"""Offline evaluation: python -m studypilot.evaluation   (prints a Markdown report)

* Summary quality: ROUGE-1 of the TextRank summary vs a hand-written reference
  summary of the Deadlocks notes, compared with Lead-k and random-k baselines.
* QA: top-1 / top-3 hit rate and MRR of BM25 on hand-written question ->
  answer-sentence pairs over all three sample note sets, vs a word-overlap baseline.
* Latency of each pipeline step on this machine.
"""
import random
import re
import statistics
import time
from collections import Counter

from .analysis import Analysis
from .samples import BY_ID, SAMPLES
from .text import query_terms, stem

# Written by hand from the deadlock notes (6 sentences, own wording).
REFERENCE_SUMMARY = {
    "os-deadlocks": (
        "A deadlock occurs when a set of processes are blocked because each process holds a "
        "resource while waiting for a resource held by another process in the set. Four "
        "necessary conditions must hold at the same time: mutual exclusion, hold and wait, no "
        "preemption and circular wait. Deadlocks can be handled by prevention, avoidance, "
        "detection with recovery, or by ignoring the problem. Prevention ensures that at least "
        "one of the four conditions can never hold, for example by ordering resource types to "
        "rule out circular wait. Avoidance, such as the Banker's algorithm, grants a request "
        "only if the system stays in a safe state, which requires knowing each process's "
        "maximum resource needs in advance. Detection searches a wait-for graph or runs a "
        "detection algorithm, and recovery terminates processes or preempts resources."),
}

# (sample id, question, substring(s) identifying acceptable answer sentences)
QA_PAIRS = [
    ("os-deadlocks", "What is a deadlock?", ["A deadlock is a situation"]),
    ("os-deadlocks", "What does mutual exclusion mean?", ["Mutual exclusion means"]),
    ("os-deadlocks", "Explain the hold and wait condition", ["Hold and wait means"]),
    ("os-deadlocks", "What is circular wait?", ["Circular wait means"]),
    ("os-deadlocks", "What does no preemption mean?", ["No preemption means"]),
    ("os-deadlocks", "When is a state safe?", ["A state is safe if"]),
    ("os-deadlocks", "Who proposed the Banker's algorithm?", ["proposed by Edsger Dijkstra"]),
    ("os-deadlocks", "How is the Need matrix computed?", ["Need equals Max minus Allocation"]),
    ("os-deadlocks", "How can circular wait be prevented?", ["Circular wait can be prevented"]),
    ("os-deadlocks", "What is a wait-for graph?", ["maintains a wait-for graph"]),
    ("os-deadlocks", "How does process termination recover from deadlock?", ["Process termination aborts"]),
    ("os-deadlocks", "Why do Linux and Windows ignore deadlocks?", ["including Linux and Windows"]),
    ("os-deadlocks", "How is deadlock different from livelock?", ["Deadlock is different from livelock"]),
    ("os-deadlocks", "What is a resource allocation graph?", ["A resource allocation graph is a directed graph"]),
    ("os-deadlocks", "Does a cycle in the graph always mean deadlock?",
     ["If every resource type has exactly one instance", "With multiple instances per resource type"]),
    ("ml-basics", "What is overfitting?", ["Overfitting happens when"]),
    ("ml-basics", "What does the learning rate control?", ["The learning rate controls"]),
    ("ml-basics", "How does k-means clustering work?", ["K-means clustering partitions"]),
    ("ml-basics", "What is the F1 score?", ["The F1 score is the harmonic mean"]),
    ("ml-basics", "What is the difference between L1 and L2 regularisation?", ["L1 regularisation can drive"]),
    ("ml-basics", "What is cross-validation?", ["Cross-validation divides the data"]),
    ("ml-basics", "Is logistic regression used for classification?", ["Logistic regression, despite its name"]),
    ("ml-basics", "What is recall?", ["recall is the fraction"]),
    ("cn-tcpip", "How does the TCP three-way handshake work?", ["three-way handshake"]),
    ("cn-tcpip", "What does ARP do?", ["The Address Resolution Protocol (ARP) maps"]),
    ("cn-tcpip", "Why is UDP used for games and voice calls?", ["UDP has lower overhead"]),
    ("cn-tcpip", "What is the purpose of the time-to-live field?", ["time-to-live field"]),
    ("cn-tcpip", "What does DNS do?", ["The Domain Name System (DNS) translates"]),
    ("cn-tcpip", "What is flow control?", ["Flow control uses a sliding window"]),
    ("cn-tcpip", "How long is an IPv6 address?", ["IPv6 address is 128 bits"]),
    ("cn-tcpip", "What is encapsulation?", ["Encapsulation is the process"]),
]


def _rouge_tokens(text, use_stem):
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return [stem(t) for t in toks] if use_stem else toks


def rouge1(candidate, reference, use_stem=True):
    c = Counter(_rouge_tokens(candidate, use_stem))
    r = Counter(_rouge_tokens(reference, use_stem))
    overlap = sum((c & r).values())
    p = overlap / max(1, sum(c.values()))
    rec = overlap / max(1, sum(r.values()))
    f = 2 * p * rec / (p + rec) if p + rec else 0.0
    return {"p": p, "r": rec, "f": f}


def eval_summary(k=6):
    an = Analysis(BY_ID["os-deadlocks"]["text"])
    ref = REFERENCE_SUMMARY["os-deadlocks"]
    sents = [s.text for s in an.sentences]
    tr = " ".join(sents[i] for i in an.summary(n=k)["summary_ids"])
    lead = " ".join(sents[:k])
    rnd = []
    for seed in range(200):
        idx = sorted(random.Random(seed).sample(range(len(sents)), k))
        rnd.append(rouge1(" ".join(sents[i] for i in idx), ref)["f"])
    return {"k": k, "textrank": rouge1(tr, ref), "lead": rouge1(lead, ref),
            "random_f": statistics.mean(rnd), "textrank_nostem": rouge1(tr, ref, use_stem=False)}


def _overlap_baseline(an, question):
    q = set(query_terms(question))
    scores = []
    for i, s in enumerate(an.sentences):
        sc = len(q & set(t.stem for t in s.tokens))
        scores.append((sc, -i))
    scores.sort(reverse=True)
    return [-i for _, i in scores[:3]]


def eval_qa():
    ans = {s["id"]: Analysis(s["text"]) for s in SAMPLES}
    rows, hit1, hit3, mrr, base1, base3, plain1 = [], 0, 0, 0.0, 0, 0, 0
    for sid, q, golds in QA_PAIRS:
        an = ans[sid]
        gold_ids = {i for i, s in enumerate(an.sentences) if any(g in s.text for g in golds)}
        assert gold_ids, (q, golds)
        res = an.ask(q, k=3)["results"]
        ranked = [r["sentence_id"] for r in res]
        rank = next((i + 1 for i, x in enumerate(ranked) if x in gold_ids), None)
        hit1 += rank == 1
        hit3 += rank is not None
        mrr += 1 / rank if rank else 0
        b = _overlap_baseline(an, q)
        base1 += b[0] in gold_ids
        base3 += bool(set(b) & gold_ids)
        plain = an.ask(q, k=1, definition_bonus=False)["results"]
        plain1 += bool(plain) and plain[0]["sentence_id"] in gold_ids
        rows.append((sid, q, rank, res[0]["confidence"] if res else 0))
    n = len(QA_PAIRS)
    conf_right = [c for _, _, r, c in rows if r == 1]
    conf_wrong = [c for _, _, r, c in rows if r != 1]
    return {"n": n, "top1": hit1 / n, "top3": hit3 / n, "mrr": mrr / n, "baseline_top1": base1 / n,
            "baseline_top3": base3 / n, "plain_top1": plain1 / n,
            "misses": [(s, q, r) for s, q, r, _ in rows if r != 1],
            "conf_right": statistics.mean(conf_right) if conf_right else 0,
            "conf_wrong": statistics.mean(conf_wrong) if conf_wrong else 0}


def _time(fn, reps):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts)


def eval_latency(reps=15):
    out = {}
    for s in SAMPLES:
        an = Analysis(s["text"])
        out[s["id"]] = {
            "sentences": len(an.sentences), "words": an.words,
            "build_ms": _time(lambda: Analysis(s["text"]), reps),
            "summary_ms": _time(lambda: an.summary(n=6), reps),
            "quiz_ms": _time(lambda: an.quiz(8), reps),
            "ask_ms": _time(lambda: an.ask("How does it work and why is it used?"), reps * 4),
        }
    big = "\n\n".join(s["text"] for s in SAMPLES) * 4
    an = Analysis(big)
    out["stress (12 note sets)"] = {"sentences": len(an.sentences), "words": an.words,
                                    "build_ms": _time(lambda: Analysis(big), 3),
                                    "summary_ms": _time(lambda: an.summary(n=10), 3),
                                    "quiz_ms": _time(lambda: an.quiz(8), 3),
                                    "ask_ms": _time(lambda: an.ask("What is flow control?"), 20)}
    return out


def main():
    s = eval_summary()
    q = eval_qa()
    lat = eval_latency()
    print("## Summary (Deadlocks notes, k=%d sentences, ROUGE-1 vs hand-written reference)\n" % s["k"])
    print("| Method | Precision | Recall | F1 |\n|---|---|---|---|")
    for name, r in (("TextRank (StudyPilot)", s["textrank"]), ("Lead-%d baseline" % s["k"], s["lead"])):
        print("| %s | %.3f | %.3f | %.3f |" % (name, r["p"], r["r"], r["f"]))
    print("| Random-%d (mean of 200) | – | – | %.3f |" % (s["k"], s["random_f"]))
    print("\nTextRank ROUGE-1 F1 without stemming: %.3f\n" % s["textrank_nostem"]["f"])
    print("## Ask-your-notes QA (%d hand-written questions, 3 note sets)\n" % q["n"])
    print("| Metric | BM25 + definition bonus (StudyPilot) | Plain BM25 | Word-overlap baseline |\n|---|---|---|---|")
    print("| Top-1 hit rate | %.1f%% | %.1f%% | %.1f%% |" % (100 * q["top1"], 100 * q["plain_top1"], 100 * q["baseline_top1"]))
    print("| Top-3 hit rate | %.1f%% | – | %.1f%% |" % (100 * q["top3"], 100 * q["baseline_top3"]))
    print("| MRR@3 | %.3f | – | – |" % q["mrr"])
    print("\nMean confidence when top-1 correct: %.2f; when wrong: %.2f" % (q["conf_right"], q["conf_wrong"]))
    print("Misses: " + "; ".join("%s (rank %s)" % (qq, r) for _, qq, r in q["misses"]))
    print("\n## Latency (median ms, this machine, single thread)\n")
    print("| Notes | Sentences | Words | Analyse (all steps) | Summary | Quiz (8 q) | Ask |\n|---|---|---|---|---|---|---|")
    for k, v in lat.items():
        print("| %s | %d | %d | %.1f | %.2f | %.2f | %.2f |" % (
            k, v["sentences"], v["words"], v["build_ms"], v["summary_ms"], v["quiz_ms"], v["ask_ms"]))


if __name__ == "__main__":
    main()
