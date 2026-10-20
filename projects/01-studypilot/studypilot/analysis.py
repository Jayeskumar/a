"""One object that runs the whole NLP pipeline over a set of notes and answers
summary / concept / quiz / flashcard / QA requests with explanations."""
import time
from collections import Counter, defaultdict

from . import flashcards, keyphrases, quiz
from .bm25 import BM25
from .text import content_terms, query_terms, split_sentences, stem, word_count
from .textrank import rank_sentences

MAX_CONCEPTS = 30
READING_WPM = 200          # typical adult silent-reading speed (approx.)
EDGE_LIMIT = 90            # edges drawn in the summary graph
CONF_HIGH, CONF_MED = 0.7, 0.4
# "What is X?"-style questions: bonus (in BM25 points) for sentences that OPEN with
# the asked terms, i.e. look like a definition. Scaled by the share of the
# question's IDF mass found in the sentence's first DEF_WINDOW content words.
DEF_QUESTION = ("what is", "what are", "what does", "what do", "what's", "define",
                "explain", "describe", "meaning of", "who is", "who was")
DEF_BONUS = 2.0
DEFINING_VERBS = frozenset("is are means refers describes happens occurs".split())


class Analysis:
    def __init__(self, text, title="Untitled notes"):
        t0 = time.perf_counter()
        self.title = title
        self.text = text
        self.sentences = split_sentences(text)
        self.terms = [content_terms(s.tokens) for s in self.sentences]
        self.rank = rank_sentences(self.terms)
        self.concepts = keyphrases.extract(self.sentences, top_k=MAX_CONCEPTS)
        self.concept_by_key = {c["key"]: c for c in self.concepts}
        self.bm25 = BM25([content_terms(s.tokens, expand_hyphens=True) for s in self.sentences])
        self.cards = flashcards.build(self)
        surf = defaultdict(Counter)
        for s in self.sentences:
            for t in s.tokens:
                if not t.is_stop:
                    surf[t.stem][t.lower] += 1
                    if "-" in t.lower:
                        for part in t.lower.split("-"):
                            surf[stem(part)][part] += 1
        self.surface = {k: v.most_common(1)[0][0] for k, v in surf.items()}
        self.words = word_count(text)
        self.build_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ------------------------------------------------------------------ stats
    def stats(self):
        return {"words": self.words, "sentences": len(self.sentences),
                "concepts": len(self.concepts), "cards": len(self.cards),
                "reading_min": round(self.words / READING_WPM, 1),
                "build_ms": self.build_ms,
                "sections": sorted({s.section for s in self.sentences if s.section})}

    def _norm_score(self, sid):
        return round(self.rank["scores"][sid] * len(self.sentences), 3)

    # ---------------------------------------------------------------- summary
    def summary(self, n=None, ratio=None):
        total = len(self.sentences)
        if not total:
            return {"sentences": [], "summary_ids": [], "edges": [], "stats": {}}
        if n is None:
            n = max(1, round(total * (ratio if ratio else 0.2)))
        n = max(1, min(int(n), total))
        chosen = sorted(self.rank["order"][:n])
        chosen_set = set(chosen)
        g = self.rank["graph"]
        out = []
        for s in self.sentences:
            nbrs = sorted(((g[s.id][j], j) for j in range(total) if j != s.id and g[s.id][j] > 0),
                          reverse=True)[:3]
            out.append({
                "id": s.id, "text": s.text, "section": s.section,
                "score": self._norm_score(s.id), "rank": self.rank["ranks"][s.id] + 1,
                "in_summary": s.id in chosen_set,
                "degree": sum(1 for j in range(total) if j != s.id and g[s.id][j] > 0),
                "neighbors": [{"id": j, "weight": round(w, 3),
                               "shared": sorted({self.surface.get(t, t) for t in
                                                 set(self.terms[s.id]) & set(self.terms[j])})[:6]}
                              for w, j in nbrs],
            })
        edges = []
        for i in range(total):
            for j in range(i + 1, total):
                if g[i][j] > 0:
                    edges.append((g[i][j], i, j))
        edges.sort(reverse=True)
        summary_words = sum(word_count(self.sentences[i].text) for i in chosen)
        return {
            "sentences": out, "summary_ids": chosen,
            "edges": [{"a": i, "b": j, "w": round(w, 3)} for w, i, j in edges[:EDGE_LIMIT]],
            "stats": {"total": total, "chosen": n, "words": self.words,
                      "summary_words": summary_words,
                      "compression": round(summary_words / self.words, 3) if self.words else 0,
                      "minutes_saved": round((self.words - summary_words) / READING_WPM, 1),
                      "iterations": self.rank["iterations"]},
        }

    # --------------------------------------------------------------- concepts
    def concept_list(self, k=MAX_CONCEPTS):
        out = []
        for c in self.concepts[:k]:
            out.append({
                "key": c["key"], "phrase": c["phrase"], "weight": c["weight"],
                "score": c["score"], "rake": c["rake"], "occurrences": c["occurrences"],
                "subject": c["subject"], "type": c["type"],
                "word_scores": {self.surface.get(w, w): v for w, v in c["word_scores"].items()},
                "mentions": [{"id": sid, "text": self.sentences[sid].text,
                              "spans": [[self.sentences[sid].tokens[a].start,
                                         self.sentences[sid].tokens[b - 1].end]
                                        for (osid, a, b) in c["occ"] if osid == sid]}
                             for sid in c["sentences"][:4]],
            })
        return out

    # ------------------------------------------------------------------- quiz
    def quiz(self, n=8, seed=0):
        return quiz.generate(self, n=n, seed=seed)

    # -------------------------------------------------------------------- ask
    def ask(self, question, k=3, definition_bonus=True):
        q_terms = query_terms(question)
        if not q_terms:
            return {"question": question, "terms": [], "results": [],
                    "message": "Ask a question with at least one meaningful word."}
        q_unique = list(dict.fromkeys(q_terms))
        idf_mass = self.bm25.query_idf_mass(q_unique) or 1.0
        results = self.bm25.search(q_terms, k=self.bm25.n)  # re-rank all matches
        is_def = definition_bonus and question.lower().lstrip("¿ ").startswith(DEF_QUESTION)
        for r in results:
            r["bonus"] = 0.0
            if is_def:
                r["bonus"] = round(self._definition_bonus(r["index"], set(r["contributions"]), idf_mass), 4)
                r["score"] += r["bonus"]
        results.sort(key=lambda r: (-r["score"], r["index"]))
        results = results[:k]
        out = []
        top = results[0]["score"] if results else 0
        second = results[1]["score"] if len(results) > 1 else 0
        for rank, r in enumerate(results):
            sid = r["index"]
            s = self.sentences[sid]
            matched = set(r["contributions"])
            coverage = sum(self.bm25.idf(t) for t in matched) / idf_mass
            if rank == 0:
                margin = (top - second) / top if top else 0
                conf = 0.65 * coverage + 0.35 * margin
            else:
                conf = 0.65 * coverage * (r["score"] / top)
            conf = max(0.0, min(1.0, conf))
            spans = []
            for t in s.tokens:
                stems = {t.stem} | ({stem(p) for p in t.lower.split("-")} if "-" in t.lower else set())
                if not t.is_stop and stems & matched:
                    spans.append([t.start, t.end])
            prev_s = self.sentences[sid - 1] if sid > 0 else None
            next_s = self.sentences[sid + 1] if sid + 1 < len(self.sentences) else None
            out.append({
                "sentence_id": sid, "text": s.text, "section": s.section,
                "score": round(r["score"], 3), "confidence": round(conf, 3),
                "definition_bonus": r["bonus"],
                "label": "High" if conf >= CONF_HIGH else ("Medium" if conf >= CONF_MED else "Low"),
                "coverage": round(coverage, 3), "highlights": spans,
                "before": prev_s.text if prev_s and prev_s.para == s.para else "",
                "after": next_s.text if next_s and next_s.para == s.para else "",
                "contributions": [{"term": self.surface.get(t, t), "stem": t, **v}
                                  for t, v in sorted(r["contributions"].items(),
                                                     key=lambda kv: -kv[1]["score"])],
            })
        missing = [self.surface.get(t, t) for t in q_unique
                   if all(t not in r["contributions"] for r in results)]
        msg = "" if out else "Your notes don't seem to cover this. StudyPilot only answers from your notes, so it never makes things up."
        return {"question": question, "terms": [self.surface.get(t, t) for t in q_unique],
                "missing_terms": missing, "results": out, "message": msg}

    def _definition_bonus(self, sid, matched, idf_mass):
        """Bonus for sentences that open with the asked terms ("A deadlock is ..."):
        DEF_BONUS x (IDF share of the question found in the opening words), doubled
        when the opening is directly followed by a defining verb (is/are/means...)."""
        toks = [t for t in self.sentences[sid].tokens]
        i = 0
        while i < len(toks) and toks[i].is_stop:   # "A ...", "The ...", "No preemption ..."
            i += 1
        j = i
        while j < len(toks) and (toks[j].stem in matched or
                                 {stem(p) for p in toks[j].lower.split("-")} & matched):
            j += 1
        if j == i:
            return 0.0
        opening = set()
        for t in toks[i:j]:
            opening.add(t.stem)
            opening.update(stem(p) for p in t.lower.split("-"))
        share = sum(self.bm25.idf(t) for t in matched if t in opening) / idf_mass
        defines = j < len(toks) and toks[j].lower in DEFINING_VERBS
        return DEF_BONUS * share * (2 if defines else 1)

    def suggested_questions(self, k=6):
        qs, seen = [], set()
        for card in self.cards:
            if card["kind"] != "definition" or card["concept"] in seen:
                continue
            seen.add(card["concept"])
            front = card["front"]
            if front.startswith("Explain: "):
                front = "What is %s?" % front[len("Explain: "):]
            qs.append(front)
            if len(qs) >= k:
                break
        return qs
