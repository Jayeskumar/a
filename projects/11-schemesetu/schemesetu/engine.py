"""SchemeSetu facade: one object the HTTP layer (and tests) talk to."""
import os
import random
import time

from . import benefits, checklist, config, questionnaire, rules, search, synth, village
from .catalogue import Catalogue, ProfileError  # noqa: F401  (re-exported)

STATUS = {rules.PASS: "eligible", rules.FAIL: "not_eligible", rules.UNKNOWN: "possibly"}
_ORDER = {"eligible": 0, "possibly": 1, "not_eligible": 2}

# Illustrative uptake used only to seed the demo village's tracker.
DEMO_UPTAKE = {"pm_kisan": 0.75, "pm_jay": 0.6, "kmut": 0.7, "mgnrega": 0.6, "ignoaps": 0.5,
               "ignwps": 0.45, "pmfby": 0.3, "kcc": 0.35, "cmchis": 0.5, "nrlm_shg": 0.4}
DEMO_UPTAKE_DEFAULT = 0.2


def _blocking(trace):
    """Leaves that make a FAIL result fail (the 'why not')."""
    if trace["status"] != rules.FAIL:
        return []
    if trace["kind"] == "cond":
        return [trace]
    if trace["kind"] == "not":
        return [dict(l, negated=True) for l in rules.leaves(trace["children"][0])]
    out = []
    for k in trace["children"]:
        out.extend(_blocking(k))
    return out


def _decisive_pass(trace):
    """Leaves that make a PASS result pass (the 'why yes')."""
    if trace["status"] != rules.PASS:
        return []
    if trace["kind"] == "cond":
        return [trace]
    if trace["kind"] == "not":
        return []
    out = []
    for k in trace["children"]:
        out.extend(_decisive_pass(k))
    return out


# Display order for eligible schemes: tangible cash first, then grants, cover, the rest.
def _kind_rank(scheme):
    kind = scheme["benefit"]["kind"]
    if kind == "annual" and not scheme.get("conditional"):
        return 0
    return {"one_time": 1, "annual": 2, "cover": 3, "future": 4}.get(kind, 5)


class Engine(object):
    def __init__(self, data_dir):
        t0 = time.perf_counter()
        self.data_dir = data_dir
        self.cat = Catalogue(data_dir)
        prior_pop = synth.population(config.PRIOR_POPULATION, config.PRIOR_SEED)
        self.priors = questionnaire.learn_priors(self.cat, prior_pop)
        self.selector = questionnaire.Selector(self.cat, self.priors)
        self.index = search.build_index(self.cat, data_dir)
        self.startup_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ------------------------------------------------------------ profile
    def normalise(self, raw):
        return self.cat.normalise_profile(raw)

    def statuses(self, profile):
        closed = self.cat.close(profile)[0]
        return dict((s["id"], STATUS[rules.status_of(s["rule"], closed, self.cat.params)])
                    for s in self.cat.schemes)

    # ------------------------------------------------------------ evaluate
    def evaluate(self, profile):
        cat = self.cat
        explicit = profile
        profile, inferred = cat.close(explicit)
        results = []
        for s in cat.schemes:
            tr = rules.evaluate(s["rule"], profile, cat.params)
            st = STATUS[tr["status"]]
            lv = rules.leaves(tr)
            needed = rules.needed_facts(tr)
            if st == "eligible":
                met = [cat.condition_text(l) for l in _decisive_pass(tr)]
                more = " +%d" % (len(met) - 3) if len(met) > 3 else ""
                reason = {"en": "Met: " + "; ".join(m["en"] for m in met[:3]) + more,
                          "ta": "பூர்த்தி: " + "; ".join(m["ta"] for m in met[:3]) + more}
            elif st == "not_eligible":
                b = _blocking(tr)[0]
                txt = cat.condition_text(b)
                reason = {"en": "Not met: " + txt["en"], "ta": "பூர்த்தியாகவில்லை: " + txt["ta"]}
            else:
                names_en = ", ".join(cat.q_by_id[f]["short"]["en"] for f in needed)
                names_ta = ", ".join(cat.q_by_id[f]["short"]["ta"] for f in needed)
                reason = {"en": "Need answer: " + names_en, "ta": "பதில் தேவை: " + names_ta}
            amt = benefits.scheme_amount(s, profile, cat.params)
            results.append({
                "id": s["id"], "short": s["short"], "name": s["name"], "category": s["category"],
                "level": s.get("level", "central"), "status": st, "reason": reason, "rank": _kind_rank(s),
                "benefit": dict(s["benefit"], amount=amt), "summary": s["summary"],
                "conditions": {"pass": sum(1 for l in lv if l["status"] == rules.PASS),
                               "fail": sum(1 for l in lv if l["status"] == rules.FAIL),
                               "unknown": sum(1 for l in lv if l["status"] == rules.UNKNOWN),
                               "total": len(lv)},
                "needed": needed, "trace": cat.explain(tr, inferred),
            })
        results.sort(key=lambda r: (_ORDER[r["status"]], r["rank"], -(r["benefit"].get("amount") or 0), r["id"]))
        counts = {"eligible": 0, "possibly": 0, "not_eligible": 0}
        for r in results:
            counts[r["status"]] += 1
        inf = []
        for f, src in sorted(inferred.items(), key=lambda kv: self.cat.questions.index(cat.q_by_id[kv[0]])):
            inf.append({"fact": f, "short": cat.q_by_id[f]["short"],
                        "answer": cat.answer_label(f, profile[f]),
                        "from": src, "from_short": cat.q_by_id[src]["short"]})
        atomic_ids = [q["id"] for q in cat.atomic]
        return {
            "answered": len(explicit), "known_facts": sum(1 for f in atomic_ids if profile.get(f) is not None),
            "total_questions": len(cat.atomic),
            "counts": counts, "results": results, "inferred": inf,
            "benefits": benefits.estimate(results, cat, profile),
        }

    # ------------------------------------------------------------ questionnaire
    def next_question(self, profile, skipped=(), strategy=None):
        nq = self.selector.next_question(profile, skipped, strategy)
        if nq is None:
            return None
        q = self.cat.q_by_id[nq["id"]]
        names = [self.cat.by_id[s]["short"] for s in nq["affects"]]
        shown = ", ".join(names[:4]) + (" +%d" % (len(names) - 4) if len(names) > 4 else "")
        why = {
            "en": "Asked now because it can settle about %.1f of the %d schemes still open (%s). Information gain %.2f bits."
                  % (nq["expected_resolved"], nq["open_schemes"], shown, nq["info_gain_bits"]),
            "ta": "இன்னும் முடிவாகாத %d திட்டங்களில் சுமார் %.1f திட்டங்களை இந்தக் கேள்வி தீர்மானிக்கும் (%s). தகவல் ஆதாயம் %.2f பிட்."
                  % (nq["open_schemes"], nq["expected_resolved"], shown, nq["info_gain_bits"]),
        }
        return dict(nq, question=q, why=why)

    def simulate(self, truth, strategy=None):
        t0 = time.perf_counter()
        sim = self.selector.simulate(truth, strategy)
        ms = (time.perf_counter() - t0) * 1000
        steps = []
        prof = {}
        for st in sim["steps"]:
            q = self.cat.q_by_id[st["id"]]
            if st["answer"] is not None:
                prof[st["id"]] = st["answer"]
            decided = sum(1 for v in self.statuses(prof).values() if v != "possibly")
            steps.append(dict(st, text=q["text"], short=q["short"],
                              answer_label=self.cat.answer_label(st["id"], st["answer"]),
                              decided_after=decided))
        return {"steps": steps, "questions_asked": len(steps), "profile": sim["profile"],
                "skipped": sim["skipped"], "full_form": len(self.cat.atomic),
                "elapsed_ms": round(ms, 2), "strategy": strategy or config.DEFAULT_STRATEGY}

    # ------------------------------------------------------------ search / docs
    def search(self, query, k=5):
        res = self.index.search(query, k)
        for r in res["results"]:
            s = self.cat.by_id[r["id"]]
            r.update(short=s["short"], name=s["name"], category=s["category"], summary=s["summary"],
                     benefit=s["benefit"])
        return res

    def checklist(self, scheme_ids, extra=None):
        return checklist.build(scheme_ids, self.cat, extra)

    # ------------------------------------------------------------ field worker
    def demo_village_households(self):
        hs = synth.village_households()
        rng = random.Random(config.VILLAGE_SEED + 1)
        for h in hs:
            apps = {}
            for sid, st in sorted(self.statuses(h["profile"]).items()):
                if st != "eligible":
                    continue
                p = DEMO_UPTAKE.get(sid, DEMO_UPTAKE_DEFAULT) * (0.5 + h["seed_uptake"])
                u = rng.random()
                if u < p:
                    apps[sid] = {"status": "received" if u < 0.7 * p else ("applied" if u < 0.85 * p else "pending"),
                                 "updated": "2026-10-01T10:00:00"}
            h["applications"] = apps
            h.pop("seed_uptake", None)
        return hs

    def village_dashboard(self, households, village_name=None):
        return village.dashboard(households, self, village_name)

    def stats(self):
        return {"schemes": len(self.cat.schemes), "questions": len(self.cat.atomic),
                "gates": len(self.cat.gates),
                "per_scheme_fields": sum(len(s["facts"]) for s in self.cat.schemes),
                "startup_ms": self.startup_ms, "strategy": config.DEFAULT_STRATEGY}


def default_engine():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Engine(os.path.join(here, "data"))
