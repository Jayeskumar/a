import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studypilot import keyphrases, mastery, quiz, srs, text, textrank  # noqa: E402
from studypilot.analysis import Analysis  # noqa: E402
from studypilot.bm25 import BM25  # noqa: E402
from studypilot.samples import SAMPLES  # noqa: E402
from studypilot.store import Store  # noqa: E402

DAY = srs.DAY


class TestText(unittest.TestCase):
    def test_stemmer_groups_inflections(self):
        for group in (["process", "processes"], ["schedule", "scheduled", "scheduling"],
                      ["allocate", "allocated", "allocation"], ["policy", "policies"],
                      ["deadlock", "deadlocks", "deadlocked"], ["run", "running"],
                      ["regularisation", "regularization"]):
            self.assertEqual(len({text.stem(w) for w in group}), 1, group)

    def test_stemmer_keeps_short_and_nonalpha(self):
        self.assertEqual(text.stem("TCP"), "tcp")
        self.assertEqual(text.stem("48-bit"), "48-bit")
        self.assertEqual(text.stem("Banker's"), "banker")

    def test_tokenizer_offsets_and_compounds(self):
        s = "The wait-for graph (TCP/IP) isn't Banker's."
        toks = text.tokenize(s)
        for t in toks:
            self.assertEqual(s[t.start:t.end], t.text)
        self.assertIn("wait-for", [t.text for t in toks])
        self.assertTrue(next(t for t in toks if t.text == "The").is_stop)

    def test_sentence_splitter(self):
        doc = ("# Heading\n\nDr. Smith uses e.g. queues. Pi is 3.14 here! Is it?\n"
               "- bullet one\n- bullet two\n\nNew paragraph. E. Dijkstra wrote it.")
        sents = text.split_sentences(doc)
        self.assertEqual([s.text for s in sents], [
            "Dr. Smith uses e.g. queues.", "Pi is 3.14 here!", "Is it?",
            "bullet one", "bullet two", "New paragraph.", "E. Dijkstra wrote it."])
        self.assertEqual(sents[0].section, "Heading")
        self.assertEqual(sents[0].para, sents[2].para)
        self.assertNotEqual(sents[2].para, sents[3].para)

    def test_query_terms_drop_question_words(self):
        q = text.query_terms("What is the meaning of k-means?")
        self.assertEqual(q, text.query_terms("k-means"))
        self.assertIn("k-means", q)


class TestTextRank(unittest.TestCase):
    def test_similarity(self):
        self.assertEqual(textrank.similarity(["a", "b"], ["c"]), 0.0)
        self.assertGreater(textrank.similarity(["a", "b"], ["a", "b"]),
                           textrank.similarity(["a", "b"], ["a", "c"]))

    def test_pagerank_sums_to_one_and_is_symmetric(self):
        w = [[0, 1, 1], [1, 0, 1], [1, 1, 0]]
        scores, _ = textrank.pagerank(w)
        self.assertAlmostEqual(sum(scores), 1.0, places=9)
        for s in scores:
            self.assertAlmostEqual(s, 1 / 3, places=6)

    def test_pagerank_hub_wins(self):
        # star graph: node 0 connected to everyone else
        n = 5
        w = [[0.0] * n for _ in range(n)]
        for j in range(1, n):
            w[0][j] = w[j][0] = 1.0
        scores, it = textrank.pagerank(w)
        self.assertEqual(max(range(n), key=lambda i: scores[i]), 0)
        self.assertLess(it, textrank.MAX_ITER)
        # closed form for a star: hub = (1-d)/n + d * Σ leaf/1 ... check vs fixed point
        d = textrank.DAMPING
        leaf = (1 - scores[0]) / (n - 1)
        self.assertAlmostEqual(scores[0], (1 - d) / n + d * (n - 1) * leaf, places=6)

    def test_pagerank_dangling_and_empty(self):
        self.assertEqual(textrank.pagerank([]), ([], 0))
        scores, _ = textrank.pagerank([[0, 0], [0, 0]])
        self.assertAlmostEqual(scores[0], 0.5)

    def test_summary_picks_central_sentence(self):
        terms = [["deadlock", "process", "resource"], ["deadlock", "process"],
                 ["deadlock", "resource"], ["banana", "bread"]]
        res = textrank.rank_sentences(terms)
        self.assertEqual(res["order"][0], 0)
        self.assertEqual(res["order"][-1], 3)
        self.assertEqual(textrank.summarize(terms, 2), sorted(res["order"][:2]))


class TestBM25(unittest.TestCase):
    def setUp(self):
        self.docs = [["cat", "sat", "mat"], ["dog", "sat", "log"], ["cat", "cat", "chase", "mouse"],
                     ["bird", "fly"]]
        self.bm = BM25(self.docs)

    def test_idf_rare_terms_higher(self):
        self.assertGreater(self.bm.idf("mouse"), self.bm.idf("sat"))
        self.assertGreater(self.bm.idf("sat"), 0)

    def test_manual_score(self):
        import math
        n, N = 1, 4
        idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
        avgdl = sum(len(d) for d in self.docs) / 4
        tf, dl = 1, 3
        expected = idf * tf * (1.5 + 1) / (tf + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl))
        s, contrib = self.bm.score(1, ["dog"])
        self.assertAlmostEqual(s, expected, places=9)
        self.assertEqual(contrib["dog"]["tf"], 1)

    def test_ranking_and_contributions_sum(self):
        res = self.bm.search(["cat", "mouse"], k=3)
        self.assertEqual(res[0]["index"], 2)
        total = sum(c["score"] for c in res[0]["contributions"].values())
        self.assertAlmostEqual(total, res[0]["score"], places=3)
        self.assertEqual(self.bm.search(["zebra"]), [])

    def test_tf_saturates(self):
        bm = BM25([["x"] * 1 + ["y"] * 9, ["x"] * 5 + ["y"] * 5, ["z"] * 10])
        s1, _ = bm.score(0, ["x"])
        s5, _ = bm.score(1, ["x"])
        self.assertGreater(s5, s1)
        self.assertLess(s5, 5 * s1)


class TestSM2(unittest.TestCase):
    def test_good_sequence_intervals(self):
        st, now = None, 1000.0
        intervals = []
        for _ in range(4):
            st = srs.review(st, "good", now)
            intervals.append(st["interval"])
            now = st["due"]
        self.assertEqual(intervals[:2], [1, 6])
        self.assertEqual(intervals[2], 15)  # ceil(6 * 2.5)
        self.assertEqual(intervals[3], 38)  # ceil(15 * 2.5)
        self.assertEqual(st["ef"], 2.5)     # q=4 leaves EF unchanged

    def test_ef_updates(self):
        self.assertAlmostEqual(srs.update_ef(2.5, 5), 2.6)
        self.assertAlmostEqual(srs.update_ef(2.5, 3), 2.36)
        self.assertEqual(srs.update_ef(1.3, 1), srs.MIN_EF)

    def test_again_resets_and_relearns_soon(self):
        st = srs.review(None, "good", 0)
        st = srs.review(st, "good", st["due"])
        now = st["due"]
        lapsed = srs.review(st, "again", now)
        self.assertEqual(lapsed["reps"], 0)
        self.assertEqual(lapsed["lapses"], 1)
        self.assertEqual(lapsed["due"], now + srs.RELEARN_MINUTES * 60)
        self.assertLess(lapsed["ef"], st["ef"])

    def test_easy_grows_faster_than_hard(self):
        base = srs.review(srs.review(None, "good", 0), "good", DAY)
        easy = srs.review(base, "easy", 7 * DAY)
        hard = srs.review(base, "hard", 7 * DAY)
        self.assertEqual(easy["interval"], hard["interval"])  # both use current EF
        self.assertGreater(easy["ef"], hard["ef"])
        self.assertGreater(srs.review(easy, "good", easy["due"])["interval"],
                           srs.review(hard, "good", hard["due"])["interval"])

    def test_invalid_rating_and_preview(self):
        with self.assertRaises(ValueError):
            srs.review(None, "meh", 0)
        p = srs.preview(None, 0)
        self.assertEqual(p["again"], "10 min")
        self.assertEqual(p["good"], "1 d")
        self.assertTrue(srs.is_due(None, 0))


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.an = {s["id"]: Analysis(s["text"], s["title"]) for s in SAMPLES}

    def test_concepts_reasonable(self):
        phrases = {c["phrase"] for c in self.an["os-deadlocks"].concepts}
        for must in ("resource allocation graph", "circular wait", "Banker's algorithm", "mutual exclusion"):
            self.assertIn(must, phrases)
        net = {c["phrase"] for c in self.an["cn-tcpip"].concepts}
        self.assertIn("transport layer", net)
        self.assertIn("TCP", net)
        for c in self.an["ml-basics"].concepts:
            self.assertGreater(c["weight"], 0)
            self.assertLessEqual(c["weight"], 1)

    def test_rake_breaks_on_verbs_and_stopwords(self):
        sents = text.split_sentences("A subnet mask divides an IP address into a network part.")
        spans = [" ".join(t.text for t in sents[0].tokens[a:b])
                 for _, a, b in keyphrases.candidates(sents)]
        self.assertIn("subnet mask", spans)
        self.assertIn("IP address", spans)
        self.assertNotIn("subnet mask divides", spans)

    def test_quiz_generation(self):
        for sid, an in self.an.items():
            qs = an.quiz(n=8)
            self.assertEqual(len(qs), 8, sid)
            self.assertEqual(len({q["concept"] for q in qs}), 8, "concepts must be distinct")
            for q in qs:
                self.assertIn(quiz.BLANK, q["prompt"])
                # filling the blank reconstructs the source sentence
                self.assertEqual(q["prompt"].replace(quiz.BLANK, q["answer_surface"], 1), q["source"])
                if q["kind"] == "mcq":
                    self.assertEqual(len(q["options"]), quiz.MCQ_OPTIONS)
                    self.assertEqual(len(set(o.lower() for o in q["options"])), quiz.MCQ_OPTIONS)
                    self.assertIn(q["answer"], q["options"])
                    for d in q["distractors"]:
                        self.assertIsNone(re.search(r"\b%s\b" % re.escape(d["phrase"].lower()),
                                                    q["source"].lower()))
            kinds = {q["kind"] for q in qs}
            self.assertEqual(kinds, {"mcq", "cloze"})
            self.assertNotIn("answer", quiz.public(qs[0]))

    def test_quiz_deterministic_and_seeded(self):
        an = self.an["ml-basics"]
        a = [q["prompt"] for q in an.quiz(6, seed=0)]
        self.assertEqual(a, [q["prompt"] for q in an.quiz(6, seed=0)])
        self.assertNotEqual(a, [q["prompt"] for q in an.quiz(6, seed=3)])

    def test_grading(self):
        q = {"id": "q1", "kind": "cloze", "answer": "Banker's algorithm", "source": "x",
             "answer_span": [0, 1], "why": {}, "concept": "banker algorithm"}
        self.assertTrue(quiz.grade(q, "bankers algorithm")["correct"])
        self.assertTrue(quiz.grade(q, "Bankers algoritm")["correct"])  # one typo
        self.assertFalse(quiz.grade(q, "ostrich algorithm")["correct"])
        self.assertFalse(quiz.grade(q, "")["correct"])
        m = dict(q, kind="mcq")
        self.assertTrue(quiz.grade(m, "banker's ALGORITHM")["correct"])
        self.assertFalse(quiz.grade(m, "Banker's")["correct"])

    def test_ask_finds_answer_and_explains(self):
        an = self.an["os-deadlocks"]
        res = an.ask("How can circular wait be prevented?")
        top = res["results"][0]
        self.assertTrue(top["text"].startswith("Circular wait can be prevented"))
        self.assertEqual(top["label"], "High")
        self.assertTrue(top["highlights"])
        terms = {c["term"] for c in top["contributions"]}
        self.assertTrue({"circular", "wait", "prevented"} & terms)
        self.assertEqual(an.ask("quantum chromodynamics")["results"], [])
        self.assertEqual(an.ask("what is the")["results"], [])

    def test_summary_lengths(self):
        an = self.an["cn-tcpip"]
        for n in (1, 3, 7):
            s = an.summary(n=n)
            self.assertEqual(len(s["summary_ids"]), n)
            self.assertEqual(s["summary_ids"], sorted(s["summary_ids"]))
        self.assertEqual(len(an.summary(n=999)["summary_ids"]), len(an.sentences))

    def test_flashcards(self):
        cards = self.an["ml-basics"].cards
        self.assertGreater(len(cards), 8)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        for c in cards:
            a, b = c["highlight"]
            self.assertEqual(quiz.normalise(c["back"][a:b]), quiz.normalise(c["answer"]))
            self.assertTrue(c["front"])

    def test_mastery_and_readiness(self):
        an = self.an["os-deadlocks"]
        empty = mastery.compute(an.concepts, an.cards, {}, [])
        self.assertEqual(empty["readiness"], 0)
        self.assertEqual(empty["level"], "Just starting")
        qs = an.quiz(8)
        log = [{"concept": q["concept"], "correct": True} for q in qs]
        states = {c["id"]: srs.review(None, "easy", 0) for c in an.cards}
        full = mastery.compute(an.concepts, an.cards, states, log)
        self.assertGreater(full["readiness"], 50)
        wrong = mastery.compute(an.concepts, an.cards, {}, [dict(r, correct=False) for r in log])
        self.assertLess(wrong["readiness"], full["readiness"])
        self.assertEqual(len(full["study_next"]), 3)


class TestStore(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            s = Store(path)
            s.put_doc("abc", "T", "some text")
            s.set_card_state("abc", "c1", srs.new_state())
            s.add_quiz_results("abc", [{"concept": "x", "correct": True}])
            s2 = Store(path)
            self.assertEqual(s2.get_doc("abc")["title"], "T")
            self.assertIn("c1", s2.card_states("abc"))
            self.assertEqual(len(s2.quiz_log("abc")), 1)
            self.assertTrue(s2.delete_doc("abc"))
            self.assertIsNone(Store(path).get_doc("abc"))

    def test_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            with open(path, "w") as f:
                f.write("{not json")
            self.assertEqual(Store(path).list_docs(), [])


if __name__ == "__main__":
    unittest.main()
