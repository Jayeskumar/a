"""Smart questionnaire: pick the next question that tells us the most.

For every scheme that is still undecided (rule status UNKNOWN) we model
"eligible?" as a Bernoulli variable whose probability p_s is computed
analytically from the rule tree, with unanswered facts drawn from answer
priors (learnt from a synthetic population). The greedy score of an
unanswered question q is its expected information gain

    IG(q) = sum over undecided s of [ H(p_s) - sum_a P(q=a) * H(p_s | q=a) ]

where H is binary entropy and "| q=a" means: add the answer, then apply the
gate shortcuts and logical inferences (Catalogue.close). Candidates are the
facts some undecided scheme still needs, plus any screening gate that covers
such a fact. We ask the argmax, update, and stop when no scheme is undecided.

Alternatives kept for the ablation in REPORT.md: "resolve" (expected number of
schemes decided by the answer) and "static" (bank order with skip logic).
"""
import math

from . import config, rules

STRATEGIES = ("ig", "resolve", "static")


def entropy(p):
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log(p, 2) + (1 - p) * math.log(1 - p, 2))


def learn_priors(catalogue, population, smoothing=config.PRIOR_SMOOTHING):
    """question id -> [(value, probability)] from answer frequencies (Laplace smoothed)."""
    priors = {}
    for q in catalogue.questions:
        values = [True, False] if q["type"] == "bool" else [o["value"] for o in q["options"]]
        counts = dict((v, smoothing) for v in values)
        for prof in population:
            v = catalogue.truth_answer(q["id"], prof)
            if v is None:
                continue
            b = catalogue.bucket(q["id"], v)
            if b in counts:
                counts[b] += 1
        total = float(sum(counts.values()))
        priors[q["id"]] = [(v, counts[v] / total) for v in values]
    return priors


class Selector(object):
    def __init__(self, catalogue, priors):
        self.cat = catalogue
        self.priors = priors
        self.params = catalogue.params
        self.order = dict((q["id"], i) for i, q in enumerate(catalogue.questions))

    # ------------------------------------------------------------- state
    def closed(self, profile):
        return self.cat.close(profile)[0]

    def open_schemes(self, closed):
        """Undecided schemes and the atomic facts that could still decide each one."""
        out = []
        for s in self.cat.schemes:
            tr = rules.evaluate(s["rule"], closed, self.params)
            if tr["status"] == rules.UNKNOWN:
                out.append((s, rules.needed_facts(tr)))
        return out

    def candidates(self, profile, skipped=()):
        """question id -> list of undecided schemes its answer could affect."""
        skipped = set(skipped)
        closed = self.closed(profile)
        by_fact = {}
        for s, needed in self.open_schemes(closed):
            for f in needed:
                if closed.get(f) is None:
                    by_fact.setdefault(f, []).append(s)
        cand = {}
        for f, schemes in by_fact.items():
            if f not in skipped and f not in profile:
                cand[f] = list(schemes)
        for g in self.cat.gates:
            gid = g["id"]
            if gid in profile or gid in skipped:
                continue
            seen = {}
            for f in g["gate"]["sets"]:
                for s in by_fact.get(f, []):
                    seen[s["id"]] = s
            if seen:
                cand[gid] = list(seen.values())
        return cand, closed

    # ------------------------------------------------------------- scores
    def _branches(self, qid, profile):
        """[(probability, closed profile after answering qid=value)]."""
        out = []
        for v, pa in self.priors.get(qid) or []:
            prof = dict(profile)
            prof[qid] = v
            out.append((pa, self.closed(prof)))
        return out

    def info_gain(self, schemes, closed, branches):
        gain = 0.0
        for s in schemes:
            h0 = entropy(rules.prob_pass(s["rule"], closed, self.priors, self.params))
            h1 = sum(pa * entropy(rules.prob_pass(s["rule"], cp, self.priors, self.params))
                     for pa, cp in branches)
            gain += h0 - h1
        return gain

    def expected_resolved(self, schemes, branches):
        exp = 0.0
        for pa, cp in branches:
            exp += pa * sum(1 for s in schemes
                            if rules.status_of(s["rule"], cp, self.params) != rules.UNKNOWN)
        return exp

    def _score(self, qid, schemes, profile, closed, strategy):
        if strategy == "static":
            return -self.order[qid], 0.0, 0.0
        br = self._branches(qid, profile)
        er = self.expected_resolved(schemes, br)
        ig = self.info_gain(schemes, closed, br) if strategy == "ig" else 0.0
        if strategy == "resolve":
            return er + 1e-3 * len(schemes), ig, er
        return ig + config.TIE_WEIGHT * er, ig, er

    # ------------------------------------------------------------- choose
    def next_question(self, profile, skipped=(), strategy=None, top=3):
        """Best next question, or None when every scheme is decided (or only
        skipped facts remain). Returns the question id with its explanation."""
        strategy = strategy or config.DEFAULT_STRATEGY
        if strategy not in STRATEGIES:
            raise ValueError("unknown strategy '%s'" % strategy)
        cand, closed = self.candidates(profile, skipped)
        if not cand:
            return None
        if strategy == "static":
            # bank order, atomic questions only (a plain form with skip logic)
            atomic = [q for q in cand if "gate" not in self.cat.q_by_id[q]]
            cand = dict((q, cand[q]) for q in (atomic or list(cand)))
        ranked = []
        for qid, schemes in cand.items():
            sc, ig, er = self._score(qid, schemes, profile, closed, strategy)
            ranked.append((sc, -self.order[qid], qid, schemes, ig, er))
        ranked.sort(key=lambda r: (r[0], r[1]), reverse=True)
        best = ranked[0]
        qid, schemes = best[2], best[3]
        if strategy != "ig":
            br = self._branches(qid, profile)
            ig, er = self.info_gain(schemes, closed, br), self.expected_resolved(schemes, br)
        else:
            ig, er = best[4], best[5]
        return {
            "id": qid,
            "strategy": strategy,
            "score": round(best[0], 4),
            "info_gain_bits": round(ig, 4),
            "expected_resolved": round(er, 2),
            "affects": [s["id"] for s in schemes],
            "open_schemes": len(self.open_schemes(closed)),
            "alternatives": [{"id": r[2], "score": round(r[0], 4), "affects": len(r[3])}
                             for r in ranked[1:top]],
        }

    def simulate(self, truth, strategy=None, max_steps=100):
        """Run the questionnaire against a complete profile; returns the Q&A log."""
        profile, skipped, steps = {}, [], []
        for _ in range(max_steps):
            nq = self.next_question(profile, skipped, strategy)
            if nq is None:
                break
            qid = nq["id"]
            ans = self.cat.truth_answer(qid, truth)
            if ans is None:
                skipped.append(qid)
                steps.append({"id": qid, "answer": None, "open_before": nq["open_schemes"]})
                continue
            profile[qid] = ans
            steps.append({"id": qid, "answer": ans, "open_before": nq["open_schemes"],
                          "info_gain_bits": nq["info_gain_bits"],
                          "expected_resolved": nq["expected_resolved"]})
        return {"steps": steps, "profile": profile, "skipped": skipped}
