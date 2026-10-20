"""CivicLens engine: builds the demo stream, trains every model, evaluates it, serves queries.

All state lives in one Engine instance; app.py wraps calls in Engine.lock.
"""

import bisect
import json
import math
import os
import random
import threading
import time

from . import config as C
from . import datagen as G
from . import metrics as M
from . import topics as T
from . import urgency as U
from .dedup import (LSHIndex, MinHasher, PairScorer, UnionFind, geo_cell, haversine_m,
                    neighbour_cells)
from .features import TfidfVectorizer, append_features, doc_terms
from .hotspot import dbscan, emerging_test, match_planted, summarise_clusters
from .models import MultinomialNB, OneVsRest, LogisticRegression
from .sla import (DOW, breach_feature_names, breach_vector, kaplan_meier, km_median, resolution_stats,
                  survival_at, survival_grid)
from .text import concepts, script_of, shingles, tokenize

DEPT_IDX = {d: i for i, d in enumerate(C.DEPT_CODES)}
LANG_NAME = {"en": "English", "ta": "Tamil", "tg": "Tanglish"}


def _r(x, n=3):
    return None if x is None else round(x, n)


class Engine:
    def __init__(self, data_dir=None, replay=True, seed=None):
        self.lock = threading.RLock()
        self.seed = C.SEED if seed is None else seed
        self.data_dir = data_dir
        self.timings = {}
        self.live = []
        t0 = time.time()
        self._build()
        self.timings["total_build_s"] = round(time.time() - t0, 2)
        self.clock = self.now_t
        if replay:
            self._replay_filed()

    # ================================================================== build
    def _tick(self, name, t):
        self.timings[name] = round(time.time() - t, 3)
        return time.time()

    def _build(self):
        t = time.time()
        g = G.generate(self.seed)
        self.g = g
        self.wards = g["wards"]
        self.ward_codes = [w["code"] for w in self.wards]
        self.ward_by_code = {w["code"]: w for w in self.wards}
        self.now_t = self.clock = g["now_t"]
        self.planted = g["planted"]
        cs = self.complaints = g["complaints"]
        self.by_id = {c["id"]: c for c in cs}
        t = self._tick("generate_s", t)

        # ---------- features + incident-grouped split
        self.terms = [doc_terms(c["text"]) for c in cs]
        incs = sorted(set(c["incident"] for c in cs))
        random.Random(C.SEED + 1).shuffle(incs)
        test_inc = set(incs[:int(len(incs) * C.TEST_FRACTION)])
        self.tr = [i for i, c in enumerate(cs) if c["incident"] not in test_inc]
        self.te = [i for i, c in enumerate(cs) if c["incident"] in test_inc]
        self.vec = TfidfVectorizer().fit([self.terms[i] for i in self.tr])
        self.X = [self.vec.transform_one(tm) for tm in self.terms]
        self.Xc = [self.vec.counts_one(tm) for tm in self.terms]
        t = self._tick("features_s", t)

        # ---------- routing: NB vs LR
        y = [DEPT_IDX[c["dept"]] for c in cs]
        K, V = len(C.DEPT_CODES), self.vec.n_features
        t1 = time.time()
        self.nb = MultinomialNB(K, V, C.NB_ALPHA).fit([self.Xc[i] for i in self.tr], [y[i] for i in self.tr])
        nb_train_s = time.time() - t1
        t1 = time.time()
        self.lr = OneVsRest(K, V, epochs=C.LR_EPOCHS, lr=C.LR_RATE, l2=C.LR_L2, seed=C.SEED).fit(
            [self.X[i] for i in self.tr], [y[i] for i in self.tr])
        lr_train_s = time.time() - t1
        for i, c in enumerate(cs):
            p = self.lr.predict_proba(self.X[i])
            k = max(range(K), key=p.__getitem__)
            c["pred_dept"] = C.DEPT_CODES[k]
            c["conf"] = round(p[k], 3)
        self.routing_eval = self._eval_routing(y, nb_train_s, lr_train_s)
        t = self._tick("routing_s", t)

        # ---------- urgency
        self.rule_offset = V
        self.fired = [U.fired_rules(c["text"]) for c in cs]
        self.XU = [append_features(self.X[i], U.rule_features(self.fired[i], V)) for i in range(len(cs))]
        yu = [c["urgency"] - 1 for c in cs]
        self.urg = OneVsRest(4, V + len(U.RULE_IDS), epochs=C.LR_EPOCHS, lr=C.LR_RATE, l2=C.LR_L2,
                             seed=C.SEED + 7).fit([self.XU[i] for i in self.tr], [yu[i] for i in self.tr])
        for i, c in enumerate(cs):
            probs = self.urg.predict_proba(self.XU[i])
            pr, reason = U.combine(probs, self.fired[i])
            c["priority"] = pr
            c["priority_reason"] = reason
            c["rules"] = [f["id"] for f in self.fired[i]]
            c["model_priority"] = max(range(4), key=probs.__getitem__) + 1
        self.urgency_eval = self._eval_urgency()
        t = self._tick("urgency_s", t)

        # ---------- duplicates
        self._build_dedup()
        t = self._tick("dedup_s", t)

        # ---------- hotspots + emerging
        self._hot_cache = {}
        self.hotspot_eval = self._eval_hotspots()
        self.weekly = self._weekly_counts()
        self.emerging_eval = self._eval_emerging()
        self.emerging_now = self.emerging(C.N_WEEKS)
        t = self._tick("hotspots_s", t)

        # ---------- SLA
        self._build_sla()
        t = self._tick("sla_s", t)

        # ---------- topics
        self._topic_cache = {}
        self._prepare_topics()
        t = self._tick("topics_s", t)

    # ================================================================== routing eval
    def _eval_routing(self, y, nb_s, lr_s):
        cs, K = self.complaints, len(C.DEPT_CODES)
        yt = [y[i] for i in self.te]
        t1 = time.time()
        pn = [self.nb.predict(self.Xc[i]) for i in self.te]
        nb_ms = (time.time() - t1) * 1000.0 / max(1, len(self.te))
        t1 = time.time()
        pl = [self.lr.predict(self.X[i]) for i in self.te]
        lr_ms = (time.time() - t1) * 1000.0 / max(1, len(self.te))
        out = {"n_train": len(self.tr), "n_test": len(self.te), "n_features": self.vec.n_features,
               "split": "by incident (duplicates never straddle train/test), %d%% hold-out" % (100 * C.TEST_FRACTION),
               "departments": C.DEPT_CODES, "dept_names": [C.DEPT_NAME[d] for d in C.DEPT_CODES], "models": {}}
        conf = {"nb": [max(self.nb.predict_proba(self.Xc[i])) for i in self.te],
                "lr": [max(self.lr.predict_proba(self.X[i])) for i in self.te]}
        for name, pred, tr_s, ms in (("nb", pn, nb_s, nb_ms), ("lr", pl, lr_s, lr_ms)):
            by_lang = {}
            for lg in ("en", "ta", "tg"):
                ii = [k for k, i in enumerate(self.te) if cs[i]["lang"] == lg]
                by_lang[lg] = {"n": len(ii), "accuracy": _r(M.accuracy([yt[k] for k in ii], [pred[k] for k in ii]))}
            pcs = M.per_class(yt, pred, K)
            out["models"][name] = {
                "label": "Multinomial Naive Bayes" if name == "nb" else "TF-IDF logistic regression (one-vs-rest)",
                "accuracy": _r(M.accuracy(yt, pred)), "macro_f1": _r(M.macro_f1(yt, pred, K)),
                "confusion": M.confusion(yt, pred, K), "per_class": [{k: _r(v) for k, v in p.items()} for p in pcs],
                "by_language": by_lang, "train_s": round(tr_s, 2), "predict_ms": round(ms, 3),
                "ece": _r(M.expected_calibration_error(conf[name], [a == b for a, b in zip(yt, pred)])),
                "mean_confidence": _r(sum(conf[name]) / len(conf[name]))}
        out["models"]["nb"]["top_words"] = {d: [w[2:] for w, _ in self.nb.top_features(k, self.vec.names, 8)]
                                            for k, d in enumerate(C.DEPT_CODES)}
        out["models"]["lr"]["top_words"] = {d: [w[2:] for w, _ in self.lr.top_features(k, self.vec.names, 8)]
                                            for k, d in enumerate(C.DEPT_CODES)}
        out["models"]["lr"]["loss_history"] = [round(v, 4) for v in self.lr.models[0].loss_history]
        mistakes = []
        for k, i in enumerate(self.te):
            if pl[k] != yt[k] and len(mistakes) < 8:
                mistakes.append({"id": cs[i]["id"], "text": cs[i]["text"], "true": C.DEPT_CODES[yt[k]],
                                 "pred": C.DEPT_CODES[pl[k]]})
        out["mistakes"] = mistakes
        out["agreement"] = _r(sum(1 for a, b in zip(pn, pl) if a == b) / float(len(pl)))
        return out

    def _eval_urgency(self):
        cs = self.complaints
        yt = [cs[i]["urgency"] for i in self.te]
        variants = {
            "rules": [U.rules_only_priority(self.fired[i]) for i in self.te],
            "model": [cs[i]["model_priority"] for i in self.te],
            "combined": [cs[i]["priority"] for i in self.te],
        }
        out = {"n_test": len(self.te), "variants": {}}
        for name, pred in variants.items():
            y0, p0 = [v - 1 for v in yt], [v - 1 for v in pred]
            p1 = M.binary_prf([1 if v == 1 else 0 for v in yt], [1 if v == 1 else 0 for v in pred])
            under = sum(1 for a, b in zip(yt, pred) if a <= 2 and b >= 3)
            urgent = sum(1 for a in yt if a <= 2)
            out["variants"][name] = {
                "accuracy": _r(M.accuracy(y0, p0)), "macro_f1": _r(M.macro_f1(y0, p0, 4)),
                "within_one": _r(sum(1 for a, b in zip(yt, pred) if abs(a - b) <= 1) / float(len(yt))),
                "p1_recall": _r(p1["recall"]), "p1_precision": _r(p1["precision"]),
                "under_triage": _r(under / float(urgent)) if urgent else 0.0,
                "confusion": M.confusion(y0, p0, 4)}
        out["rules"] = [{"id": r[0], "label": r[1], "kind": r[2],
                         "fires": sum(1 for f in self.fired if any(x["id"] == r[0] for x in f)),
                         "weight_p1": round(self.urg.models[0].w[self.rule_offset + k], 2)}
                        for k, r in enumerate(U.RULES)]
        dist = {}
        for c in cs:
            dist[c["priority"]] = dist.get(c["priority"], 0) + 1
        out["distribution"] = {"P%d" % k: dist.get(k, 0) for k in (1, 2, 3, 4)}
        return out

    # ================================================================== duplicates
    def _dup_item(self, c):
        return {"t": c["t"], "lat": c["lat"], "lon": c["lon"], "dept": c["pred_dept"], "closed_t": c["closed_t"]}

    def _build_dedup(self):
        cs = self.complaints
        self.hasher = MinHasher(C.MINHASH_PERM, seed=C.SEED)
        self.lsh = LSHIndex(C.LSH_BANDS, C.LSH_ROWS)
        self.shingles = [shingles(c["text"]) for c in cs]
        self.sigs = [self.hasher.signature(s) for s in self.shingles]
        self.cells = [geo_cell(c["lat"], c["lon"]) for c in cs]
        self.dup_cands = []           # per complaint: [j, jac, dist, gap, eligible, prob]
        n_cand = 0
        t1 = time.time()
        for i, c in enumerate(cs):
            cand = self.lsh.query(self.sigs[i], neighbour_cells(self.cells[i]))
            n_cand += len(cand)
            rows = []
            for j in sorted(cand):
                b = cs[j]
                jac = MinHasher.similarity(self.sigs[i], self.sigs[j])
                dist = haversine_m(c["lat"], c["lon"], b["lat"], b["lon"])
                gap = c["t"] - b["t"]
                still_open = b["closed_t"] is None or b["closed_t"] > c["t"]
                same = b["pred_dept"] == c["pred_dept"] or jac >= 0.6
                elig = (still_open and same and dist <= C.DUP_MAX_DIST_M and 0 <= gap <= C.DUP_MAX_GAP_DAYS
                        and jac >= C.DUP_MIN_JACCARD)
                rows.append([j, jac, dist, gap, elig, 0.0])
            self.dup_cands.append(rows)
            self.lsh.add(i, self.sigs[i], self.cells[i])
        lsh_ms = (time.time() - t1) * 1000.0 / len(cs)
        self.n_lsh_candidates = n_cand
        # learn the pair scorer on weeks 1-7, tune its threshold there, evaluate on weeks 8-13
        split_week = 7
        tr_rows, tr_y = [], []
        for i, rows in enumerate(self.dup_cands):
            if cs[i]["week"] > split_week:
                continue
            for r in rows:
                if r[4]:
                    tr_rows.append((r[1], r[2], r[3]))
                    tr_y.append(1 if cs[r[0]]["incident"] == cs[i]["incident"] else 0)
        self.pair_scorer = PairScorer().fit(tr_rows, tr_y)
        for rows in self.dup_cands:
            for r in rows:
                if r[4]:
                    r[5] = self.pair_scorer.prob(r[1], r[2], r[3])
        tune_idx = [i for i, c in enumerate(cs) if c["week"] <= split_week]
        eval_idx = [i for i, c in enumerate(cs) if c["week"] > split_week]
        grid = [round(0.20 + 0.05 * k, 2) for k in range(15)]
        tuning = []
        for th in grid:
            labels = self._dup_labels(th)
            r = M.pair_prf([cs[i]["incident"] for i in tune_idx], [labels[i] for i in tune_idx])
            tuning.append({"threshold": th, "precision": _r(r["precision"]), "recall": _r(r["recall"]), "f1": _r(r["f1"])})
        best = max(tuning, key=lambda r: (r["f1"], -r["threshold"]))
        self.dup_threshold = best["threshold"]
        labels = self._dup_labels(self.dup_threshold)
        self._apply_dup_labels(labels)
        truth = [cs[i]["incident"] for i in eval_idx]
        ev = M.pair_prf(truth, [labels[i] for i in eval_idx])
        # baselines on the same window: text only, and place+time only
        text_only = self._dup_labels_rule(lambda r: r[1] >= 0.5 and 0 <= r[3] <= C.DUP_MAX_GAP_DAYS, key=1)
        geo_only = self._dup_labels_rule(lambda r: r[2] <= 100 and 0 <= r[3] <= 2 and r[4], key=2, smaller=True)
        ev_text = M.pair_prf(truth, [text_only[i] for i in eval_idx])
        ev_geo = M.pair_prf(truth, [geo_only[i] for i in eval_idx])
        # LSH recall: share of true duplicate pairs that became candidates at all
        true_pairs = M.same_cluster_pairs([c["incident"] for c in cs])
        cand_pairs = set()
        for i, rows in enumerate(self.dup_cands):
            for r in rows:
                cand_pairs.add((r[0], i) if r[0] < i else (i, r[0]))
        lsh_recall = len(true_pairs & cand_pairs) / float(len(true_pairs)) if true_pairs else 0.0
        n = len(cs)
        errs = []
        for i in range(0, n, 5):
            for r in self.dup_cands[i][:4]:
                j = r[0]
                ex = len(self.shingles[i] & self.shingles[j]) / float(len(self.shingles[i] | self.shingles[j]) or 1)
                errs.append(abs(ex - r[1]))
        sims_true, sims_false = [], []
        for i, rows in enumerate(self.dup_cands):
            for r in rows:
                (sims_true if cs[r[0]]["incident"] == cs[i]["incident"] else sims_false).append(r[1])
        fmt = lambda d: {k: _r(v) if isinstance(v, float) else v for k, v in d.items()}
        self.dup_eval = {
            "threshold": self.dup_threshold, "tuning": tuning, "tune_weeks": "1-%d" % split_week,
            "eval_weeks": "%d-%d" % (split_week + 1, C.N_WEEKS), "n_eval": len(eval_idx),
            "pairwise": fmt(ev), "text_only_baseline": fmt(ev_text), "geo_time_baseline": fmt(ev_geo),
            "scorer_weights": self.pair_scorer.weights(), "scorer_train_pairs": len(tr_rows),
            "lsh": {"bands": C.LSH_BANDS, "rows": C.LSH_ROWS, "perm": C.MINHASH_PERM, "geo_cell_m": C.DUP_GEO_CELL_M,
                    "candidate_pairs": len(cand_pairs), "all_pairs": n * (n - 1) // 2,
                    "reduction": _r(1.0 - len(cand_pairs) / float(n * (n - 1) // 2), 5),
                    "candidate_recall": _r(lsh_recall), "minhash_mae": _r(sum(errs) / len(errs) if errs else 0.0, 4),
                    "ms_per_complaint": round(lsh_ms, 2),
                    "curve": [{"s": round(s / 20.0, 2), "p": _r(LSHIndex.probability(s / 20.0))} for s in range(21)]},
            "sim_hist": {"dup": self._hist(sims_true), "non_dup": self._hist(sims_false)},
            "true_incidents": len(set(c["incident"] for c in cs)),
            "pred_incidents": len(set(c["root"] for c in cs)), "complaints": n,
            "merged": sum(1 for c in cs if c["dup_of"]),
        }

    @staticmethod
    def _hist(vals, bins=10):
        h = [0] * bins
        for v in vals:
            h[min(bins - 1, int(v * bins))] += 1
        return h

    def _best_match(self, rows, th):
        best = None
        for r in rows:
            if r[4] and r[5] >= th and (best is None or r[5] > best[5]):
                best = r
        return best

    def _dup_labels(self, th):
        n = len(self.complaints)
        uf = UnionFind(n)
        for i, rows in enumerate(self.dup_cands):
            b = self._best_match(rows, th)
            if b:
                uf.union(b[0], i)
        return [uf.find(i) for i in range(n)]

    def _dup_labels_rule(self, ok, key, smaller=False):
        n = len(self.complaints)
        uf = UnionFind(n)
        for i, rows in enumerate(self.dup_cands):
            cand = [r for r in rows if ok(r)]
            if cand:
                b = (min if smaller else max)(cand, key=lambda r: r[key])
                uf.union(b[0], i)
        return [uf.find(i) for i in range(n)]

    def _apply_dup_labels(self, labels):
        cs = self.complaints
        size = {}
        for l in labels:
            size[l] = size.get(l, 0) + 1
        for i, c in enumerate(cs):
            c["root"] = cs[labels[i]]["id"]
            c["dup_of"] = None
            c["inc_size"] = size[labels[i]]
        for i, rows in enumerate(self.dup_cands):
            b = self._best_match(rows, self.dup_threshold)
            if b:
                cs[i]["dup_of"] = cs[b[0]]["id"]
                cs[i]["dup_info"] = {"jaccard": _r(b[1]), "dist_m": round(b[2], 1), "gap_h": round(b[3] * 24, 2),
                                     "p": _r(b[5])}

    # ================================================================== hotspots
    def _incident_points(self, dept=None, weeks=None):
        """One point per predicted incident (its root complaint)."""
        pts, meta = [], []
        lo_week = C.N_WEEKS - weeks + 1 if weeks else 1
        for c in self.all_complaints():
            if c["root"] != c["id"]:
                continue
            if dept and c["pred_dept"] != dept:
                continue
            if c["week"] < lo_week:
                continue
            pts.append((c["lat"], c["lon"]))
            meta.append(c)
        return pts, meta

    def hotspots(self, dept=None, eps=C.DBSCAN_EPS_M, min_pts=C.DBSCAN_MIN_PTS, weeks=None):
        key = (dept, eps, min_pts, weeks, len(self.live))
        if key in self._hot_cache:
            return self._hot_cache[key]
        depts = [dept] if dept else C.HOTSPOT_DEPTS
        clusters = []
        for d in depts:
            pts, meta = self._incident_points(d, weeks)
            labels = dbscan(pts, eps, min_pts)
            for s in summarise_clusters(pts, labels):
                mem = [meta[i] for i in s["members"]]
                wards = {}
                for m in mem:
                    wards[m["ward"]] = wards.get(m["ward"], 0) + 1
                ward = max(sorted(wards), key=wards.get)
                recent = sum(1 for m in mem if m["week"] > C.N_WEEKS - 4)
                clusters.append({"dept": d, "dept_name": C.DEPT_NAME[d], "n": s["n"], "center": s["center"],
                                 "radius_m": max(40.0, s["radius_m"]), "ward": ward,
                                 "ward_name": self.ward_by_code[ward]["name"], "recent_4w": recent,
                                 "open": sum(1 for m in mem if self._is_open(m)),
                                 "sample": [m["id"] for m in mem[:5]]})
        clusters.sort(key=lambda c: -c["n"])
        planted = [p for p in self.planted if (not dept or p["dept"] == dept)]
        matches = match_planted(clusters, planted)
        for di, c in enumerate(clusters):
            c["id"] = "HS-%d" % (di + 1)
            if di in matches:
                pi, m = matches[di]
                c["planted"] = planted[pi]["id"]
                c["planted_error_m"] = round(m, 1)
            else:
                c["planted"] = None
        res = {"eps_m": eps, "min_pts": min_pts, "weeks": weeks or C.N_WEEKS, "clusters": clusters,
               "planted": planted}
        self._hot_cache[key] = res
        return res

    def _eval_hotspots(self):
        h = self.hotspots()
        hits = [c for c in h["clusters"] if c["planted"]]
        persistent = [p for p in self.planted if p["kind"] == "persistent"]
        found = {c["planted"] for c in hits}
        return {"eps_m": h["eps_m"], "min_pts": h["min_pts"], "detected": len(h["clusters"]),
                "matched": len(hits), "precision": _r(len(hits) / float(len(h["clusters"]))) if h["clusters"] else 0.0,
                "persistent_recall": _r(sum(1 for p in persistent if p["id"] in found) / float(len(persistent))),
                "surge_found": sorted(p["id"] for p in self.planted if p["kind"] == "surge" and p["id"] in found),
                "all_recall": _r(len(found) / float(len(self.planted))),
                "mean_center_error_m": _r(sum(c["planted_error_m"] for c in hits) / len(hits), 1) if hits else None,
                "false_hotspots": [{"dept": c["dept"], "ward": c["ward"], "n": c["n"]} for c in h["clusters"] if not c["planted"]]}

    def _weekly_counts(self):
        """(ward, dept) -> [incidents per week] using predicted incidents and departments."""
        out = {}
        for c in self.complaints:
            if c["root"] != c["id"]:
                continue
            key = (c["ward"], c["pred_dept"])
            if key not in out:
                out[key] = [0] * C.N_WEEKS
            out[key][c["week"] - 1] += 1
        return out

    def emerging(self, week=C.N_WEEKS):
        flags = []
        for (ward, dept), series in sorted(self.weekly.items()):
            r = emerging_test(series, week)
            if r and r["flag"]:
                p = next((pl for pl in self.planted if pl["kind"] == "surge" and pl["ward"] == ward
                          and pl["dept"] == dept and pl["week"] == week), None)
                flags.append(dict(r, ward=ward, ward_name=self.ward_by_code[ward]["name"], dept=dept,
                                  dept_name=C.DEPT_NAME[dept], week=week, series=series,
                                  planted=p["id"] if p else None, p=float("%.3g" % r["p"])))
        flags.sort(key=lambda f: -f["z"])
        return flags

    def _eval_emerging(self):
        all_flags, tested = [], 0
        for w in range(C.EMERGING_BASELINE_WEEKS + 1, C.N_WEEKS + 1):
            all_flags += self.emerging(w)
            tested += len(self.weekly)
        surges = [p for p in self.planted if p["kind"] == "surge"]
        found = {f["planted"] for f in all_flags if f["planted"]}
        false = [f for f in all_flags if not f["planted"]]
        return {"tested_cells": tested, "flags": len(all_flags), "planted_surges": len(surges),
                "surges_detected": sorted(found), "recall": _r(len(found) / float(len(surges))) if surges else None,
                "false_flags": len(false), "false_flag_rate": _r(len(false) / float(tested), 4),
                "false_list": [{"ward": f["ward"], "dept": f["dept"], "week": f["week"], "x": f["x"], "lambda": f["lambda"]}
                               for f in false][:10],
                "z": C.EMERGING_Z, "min_count": C.EMERGING_MIN_COUNT, "baseline_weeks": C.EMERGING_BASELINE_WEEKS}

    def heatgrid(self, dept=None):
        weeks = list(range(1, C.N_WEEKS + 1))
        rows = []
        for w in self.ward_codes:
            if dept:
                series = list(self.weekly.get((w, dept), [0] * C.N_WEEKS))
            else:
                series = [0] * C.N_WEEKS
                for d in C.DEPT_CODES:
                    for k, v in enumerate(self.weekly.get((w, d), [])):
                        series[k] += v
            flags = []
            for wk in weeks:
                r = emerging_test(series, wk)
                flags.append(bool(r and r["flag"]))
            rows.append({"ward": w, "name": self.ward_by_code[w]["name"], "counts": series, "flags": flags})
        mx = max([max(r["counts"]) for r in rows] + [1])
        return {"dept": dept, "weeks": weeks, "rows": rows, "max": mx,
                "week_starts": [G.iso((k - 1) * 7)[:10] for k in weeks]}

    # ================================================================== SLA
    def _is_open(self, c):
        return c.get("closed_t") is None

    def _build_sla(self):
        cs = self.complaints
        by_dept = {}
        for c in cs:
            by_dept.setdefault(c["pred_dept"], []).append(c)
        self._filed_sorted, self._closed_sorted = {}, {}
        for d in C.DEPT_CODES:
            lst = by_dept.get(d, [])
            self._filed_sorted[d] = sorted(c["t"] for c in lst)
            self._closed_sorted[d] = sorted(c["closed_t"] for c in lst if c["closed_t"] is not None)
        for c in cs:
            c["backlog"] = self.backlog_at(c["pred_dept"], c["t"])
        self.dept_mean_backlog = {}
        for d in C.DEPT_CODES:
            lst = by_dept.get(d, [])
            self.dept_mean_backlog[d] = sum(c["backlog"] for c in lst) / float(len(lst)) if lst else 0.0
        self.bnames = breach_feature_names(self.ward_codes)
        self.bindex = {n: i for i, n in enumerate(self.bnames)}
        rows, X, y = [], [], []
        for c in cs:
            sla = C.SLA_DAYS[c["pred_dept"]]
            c["sla_days"] = sla
            c["breached"] = c["age_days"] > sla
            if c["t"] + sla <= self.now_t:
                rows.append(c)
                X.append(self._bvec(c))
                y.append(1 if c["breached"] else 0)
        cut = C.N_WEEKS - C.BREACH_TEST_WEEKS
        tr = [k for k, c in enumerate(rows) if c["week"] <= cut]
        te = [k for k, c in enumerate(rows) if c["week"] > cut]
        m = LogisticRegression(len(self.bnames), epochs=C.BREACH_EPOCHS, lr=C.BREACH_RATE, l2=C.BREACH_L2,
                               seed=C.SEED).fit([X[k] for k in tr], [y[k] for k in tr])
        s = [m.predict_proba(X[k]) for k in te]
        yt = [y[k] for k in te]
        base_rate = sum(y[k] for k in tr) / float(len(tr))
        pred = [1 if v >= C.AT_RISK_THRESHOLD else 0 for v in s]
        prf = M.binary_prf(yt, pred)
        # simple baseline: department breach rate on the training weeks
        dept_rate = {}
        for d in C.DEPT_CODES:
            ks = [k for k in tr if rows[k]["pred_dept"] == d]
            dept_rate[d] = sum(y[k] for k in ks) / float(len(ks)) if ks else base_rate
        s_base = [dept_rate[rows[k]["pred_dept"]] for k in te]
        self.breach_eval = {
            "n_train": len(tr), "n_test": len(te), "test_weeks": "%d-%d" % (cut + 1, C.N_WEEKS),
            "auc": _r(M.roc_auc(yt, s)), "auc_dept_baseline": _r(M.roc_auc(yt, s_base)),
            "brier": _r(M.brier(yt, s)), "base_rate": _r(base_rate), "test_rate": _r(sum(yt) / float(len(yt))) if yt else None,
            "precision": _r(prf["precision"]), "recall": _r(prf["recall"]), "threshold": C.AT_RISK_THRESHOLD,
            "loss_history": [round(v, 4) for v in m.loss_history[::3]]}
        # refit on every labelled row for serving
        self.breach = LogisticRegression(len(self.bnames), epochs=C.BREACH_EPOCHS, lr=C.BREACH_RATE,
                                         l2=C.BREACH_L2, seed=C.SEED).fit(X, y)
        coefs = sorted(((self.breach.w[j], n) for j, n in enumerate(self.bnames)), reverse=True)
        self.breach_eval["top_risk_factors"] = [{"feature": n, "weight": round(w, 3)} for w, n in coefs[:8]]
        self.breach_eval["top_protective"] = [{"feature": n, "weight": round(w, 3)} for w, n in coefs[-6:][::-1]]

    def _bvec(self, c):
        return breach_vector(self.bindex, c["pred_dept"], c["ward"], c["dow"], c["priority"], c["backlog"],
                             self.dept_mean_backlog.get(c["pred_dept"], 0.0) if hasattr(self, "dept_mean_backlog") else 0.0)

    def backlog_at(self, dept, t):
        f = bisect.bisect_left(self._filed_sorted.get(dept, []), t)
        cl = bisect.bisect_right(self._closed_sorted.get(dept, []), t)
        live = sum(1 for c in getattr(self, "live", []) if c["pred_dept"] == dept and c["t"] < t)
        return max(0, f - cl) + live

    def breach_risk(self, c):
        x = self._bvec(c)
        p = self.breach.predict_proba(x)
        contrib = sorted(((self.breach.w[j] * v, self.bnames[j]) for j, v in zip(*x)), reverse=True)
        return p, [{"feature": n, "contribution": round(w, 3)} for w, n in contrib if w > 0][:3]

    def sla(self):
        cs = self.all_complaints()
        depts = []
        overall_d, overall_e = [], []
        for d in C.DEPT_CODES:
            lst = [c for c in cs if c["pred_dept"] == d]
            dur = [c["age_days"] if c.get("closed_t") is None else c["res_days"] for c in lst]
            ev = [0 if c.get("closed_t") is None else 1 for c in lst]
            overall_d += dur
            overall_e += ev
            grid, curve = survival_grid(dur, ev)
            res = [c["res_days"] for c in lst if c.get("res_days") is not None]
            labelled = [c for c in lst if c["t"] + C.SLA_DAYS[d] <= self.now_t]
            comp = sum(1 for c in labelled if not c["breached"]) / float(len(labelled)) if labelled else None
            recent = [c for c in labelled if c["week"] > C.N_WEEKS - 4]
            comp4 = sum(1 for c in recent if not c["breached"]) / float(len(recent)) if recent else None
            open_now = [c for c in lst if c.get("closed_t") is None]
            depts.append({
                "dept": d, "name": C.DEPT_NAME[d], "sla_days": C.SLA_DAYS[d], "received": len(lst),
                "open": len(open_now), "open_breached": sum(1 for c in open_now if c["age_days"] > C.SLA_DAYS[d]),
                "compliance": _r(comp), "compliance_4w": _r(comp4), "stats": resolution_stats(res),
                "km_median": _r(km_median(curve), 2), "open_after_sla_pct": round(100 * survival_at(curve, C.SLA_DAYS[d]), 1),
                "curve": grid, "backlog_now": self.backlog_at(d, self.clock),
                "duplicates": sum(1 for c in lst if c.get("dup_of"))})
        grid, curve = survival_grid(overall_d, overall_e)
        return {"departments": depts, "overall_curve": grid, "overall_median": _r(km_median(curve), 2),
                "breach_model": self.breach_eval, "now": G.iso(self.clock)}

    def wards_ranking(self):
        cs = self.all_complaints()
        out = []
        for w in self.wards:
            lst = [c for c in cs if c["ward"] == w["code"]]
            lab = [c for c in lst if c["t"] + c["sla_days"] <= self.now_t]
            res = [c["res_days"] for c in lst if c.get("res_days") is not None]
            open_now = [c for c in lst if c.get("closed_t") is None]
            br = sum(1 for c in lab if c["breached"]) / float(len(lab)) if lab else 0.0
            out.append({"ward": w["code"], "name": w["name"], "name_ta": w["name_ta"], "complaints": len(lst),
                        "incidents": sum(1 for c in lst if c["root"] == c["id"]), "open": len(open_now),
                        "breach_rate": _r(br), "median_res": _r(M.percentile(res, 0.5), 2) if res else None,
                        "p1": sum(1 for c in lst if c["priority"] == 1), "center": w["center"]})
        out.sort(key=lambda r: (-r["breach_rate"], -r["open"]))
        for k, r in enumerate(out):
            r["rank"] = k + 1
        return out

    # ================================================================== topics
    def _prepare_topics(self):
        cs = self.complaints
        self.topic_idx = [i for i, c in enumerate(cs) if c["pred_dept"] == "OTHER" and c["root"] == c["id"]]
        toks = [[t for t in concepts(cs[i]["text"]) if t not in T.PLACE_CONCEPTS and not t.isdigit()]
                for i in self.topic_idx]
        self.topic_vecs, _ = T.tfidf_dicts(toks, min_df=2)
        sil = []
        for k in range(C.TOPIC_K_RANGE[0], C.TOPIC_K_RANGE[1] + 1):
            labels, cents, inertia = T.kmeans(self.topic_vecs, k, seed=C.SEED, restarts=C.TOPIC_RESTARTS)
            self._topic_cache[k] = (labels, cents, inertia)
            sil.append({"k": k, "silhouette": _r(T.silhouette(self.topic_vecs, labels)), "inertia": _r(inertia, 2)})
        self.topic_sil = sil
        self.topic_best_k = max(sil, key=lambda r: r["silhouette"])["k"]

    def topics(self, k=None):
        k = k or self.topic_best_k
        if k not in self._topic_cache:
            self._topic_cache[k] = T.kmeans(self.topic_vecs, k, seed=C.SEED, restarts=C.TOPIC_RESTARTS)
        labels, cents, inertia = self._topic_cache[k]
        cs = self.complaints
        clusters = []
        for c in range(k):
            mem = [self.topic_idx[i] for i in range(len(labels)) if labels[i] == c]
            if not mem:
                continue
            truth = {}
            for i in mem:
                key = cs[i]["issue"] if cs[i]["dept"] == "OTHER" else "misrouted:" + cs[i]["dept"]
                truth[key] = truth.get(key, 0) + 1
            top_truth = max(sorted(truth), key=truth.get)
            langs = {}
            for i in mem:
                langs[cs[i]["lang"]] = langs.get(cs[i]["lang"], 0) + 1
            recent = sum(1 for i in mem if cs[i]["week"] > C.N_WEEKS - 4)
            clusters.append({"topic": c, "size": len(mem), "terms": T.top_terms(cents[c], 6),
                             "examples": [{"id": cs[i]["id"], "text": cs[i]["text"], "lang": cs[i]["lang"]} for i in mem[:4]],
                             "planted_topic": top_truth, "purity": _r(truth[top_truth] / float(len(mem))),
                             "languages": langs, "recent_4w": recent})
        clusters.sort(key=lambda c: -c["size"])
        truth_all = [cs[i]["issue"] if cs[i]["dept"] == "OTHER" else "misrouted" for i in self.topic_idx]
        return {"k": k, "best_k": self.topic_best_k, "n_docs": len(self.topic_idx), "clusters": clusters,
                "silhouette": self.topic_sil, "purity": _r(T.purity(labels, truth_all)),
                "planted_topics": sorted(set(i[1] for i in G.ISSUES if i[0] == "OTHER"))}

    # ================================================================== live pipeline
    def all_complaints(self):
        return self.complaints + self.live if self.live else self.complaints

    def get(self, cid):
        if cid in self.by_id:
            return self.by_id[cid]
        for c in self.live:
            if c["id"] == cid:
                return c
        return None

    def _route_explain(self, text):
        toks, counts, spans = doc_terms(text, with_spans=True)
        x = self.vec.transform_one(counts)
        p = self.lr.predict_proba(x)
        K = len(C.DEPT_CODES)
        k = max(range(K), key=p.__getitem__)
        xc = self.vec.counts_one(counts)
        pnb = self.nb.predict_proba(xc)
        w = self.lr.models[k].w
        tok_contrib = [0.0] * len(toks)
        feats = []
        for j, v in zip(*x):
            nm = self.vec.names[j]
            cval = w[j] * v
            feats.append((cval, nm))
            occ = spans.get(nm, [])
            if not occ:
                continue
            share = cval / len(occ)
            for o in occ:
                for ti in o:
                    tok_contrib[ti] += share / len(o)
        feats.sort(reverse=True)
        known = sum(1 for nm in counts if nm in self.vec.vocab)
        return {
            "dept": C.DEPT_CODES[k], "dept_name": C.DEPT_NAME[C.DEPT_CODES[k]], "confidence": round(p[k], 3),
            "lr_probs": sorted([{"dept": C.DEPT_CODES[i], "p": round(p[i], 3)} for i in range(K)], key=lambda r: -r["p"]),
            "nb_probs": sorted([{"dept": C.DEPT_CODES[i], "p": round(pnb[i], 4)} for i in range(K)], key=lambda r: -r["p"]),
            "nb_dept": C.DEPT_CODES[max(range(K), key=pnb.__getitem__)],
            "tokens": [{"t": t, "w": round(cv, 3)} for t, cv in zip(toks, tok_contrib)],
            "top_features": [{"f": nm, "w": round(cv, 3)} for cv, nm in feats[:8] if cv > 0],
            "bias": round(self.lr.models[k].b, 3), "known_features": known, "total_features": len(counts),
        }, x

    def analyze(self, text, lat=None, lon=None, channel="App", record=False):
        """Run the full pipeline on a new complaint. record=True files it into the live queue."""
        t_all = time.time()
        stages = {}
        t = time.time()
        text = " ".join(str(text).split())
        lang = script_of(text)
        route, x = self._route_explain(text)
        stages["routing_ms"] = (time.time() - t) * 1000
        t = time.time()
        cons = concepts(text)
        fired = U.fired_rules(text, cons)
        xu = append_features(x, U.rule_features(fired, self.rule_offset))
        probs = self.urg.predict_proba(xu)
        pr, reason = U.combine(probs, fired)
        wk = self.urg.models[pr - 1].w
        utok = sorted(((wk[j] * v, self.vec.names[j]) for j, v in zip(*x) if self.vec.names[j][0] == "w"), reverse=True)
        stages["urgency_ms"] = (time.time() - t) * 1000
        # location
        if lat is None or lon is None:
            w = self.ward_by_code["W07"]
            lat, lon = w["center"]
        x_m, y_m = G.to_xy(lat, lon)
        ward = G.ward_code(G.ward_of_xy(x_m, y_m))
        t_new = self.clock + (3.0 / 1440.0 if record else 0.0)
        # duplicates: history via LSH, live items brute force
        t = time.time()
        sh = shingles(text)
        sig = self.hasher.signature(sh)
        cands = [(self.complaints[j], self.sigs[j]) for j in sorted(self.lsh.query(sig, neighbour_cells(geo_cell(lat, lon))))]
        cands += [(c, c["_sig"]) for c in self.live]
        best = None
        checked = []
        for b, sb in cands:
            jac = MinHasher.similarity(sig, sb)
            dist = haversine_m(lat, lon, b["lat"], b["lon"])
            gap = t_new - b["t"]
            still_open = b.get("closed_t") is None
            same = b["pred_dept"] == route["dept"] or jac >= 0.6
            score = self.pair_scorer.prob(jac, dist, max(0.0, gap))
            ok = (still_open and same and dist <= C.DUP_MAX_DIST_M and 0 <= gap <= C.DUP_MAX_GAP_DAYS
                  and jac >= C.DUP_MIN_JACCARD and score >= self.dup_threshold)
            why = []
            if not still_open:
                why.append("already resolved")
            if not same:
                why.append("other department")
            if dist > C.DUP_MAX_DIST_M:
                why.append("%.0f m away" % dist)
            if gap > C.DUP_MAX_GAP_DAYS:
                why.append("%.0f days earlier" % gap)
            if jac < C.DUP_MIN_JACCARD:
                why.append("text too different")
            elif not why and score < self.dup_threshold:
                why.append("P(same) below %.2f" % self.dup_threshold)
            row = {"id": b["id"], "text": b["text"], "jaccard": round(jac, 3), "dist_m": round(dist), "gap_h": round(gap * 24, 2),
                   "score": round(score, 3), "duplicate": ok, "why_not": why}
            checked.append(row)
            if ok and (best is None or score > best["score"]):
                best = row
        if best:
            best["explain"] = self.pair_scorer.explain(best["jaccard"], best["dist_m"], best["gap_h"] / 24.0)
        checked.sort(key=lambda r: (-r["duplicate"], -r["score"]))
        stages["dedup_ms"] = (time.time() - t) * 1000
        # hotspot membership
        t = time.time()
        hs = None
        for h in self.hotspots()["clusters"]:
            if h["dept"] != route["dept"]:
                continue
            d = haversine_m(lat, lon, h["center"][0], h["center"][1])
            if d <= max(h["radius_m"], C.DBSCAN_EPS_M) + 30 and (hs is None or d < hs["dist_m"]):
                hs = {"id": h["id"], "n": h["n"], "dist_m": round(d), "ward_name": h["ward_name"]}
        em = next(({"z": f["z"], "x": f["x"], "lambda": f["lambda"], "week": f["week"]} for f in self.emerging_now
                   if f["ward"] == ward and f["dept"] == route["dept"]), None)
        stages["hotspot_ms"] = (time.time() - t) * 1000
        # SLA
        t = time.time()
        dept = route["dept"]
        sla_days = C.SLA_DAYS[dept]
        backlog = self.backlog_at(dept, t_new)
        rec = {"pred_dept": dept, "ward": ward, "dow": int(t_new) % 7, "priority": pr, "backlog": backlog}
        risk, factors = self.breach_risk(rec)
        stages["sla_ms"] = (time.time() - t) * 1000
        total_ms = (time.time() - t_all) * 1000
        root = None
        if best:
            bc = self.get(best["id"])
            root = bc["root"] if bc else best["id"]
        result = {
            "text": text, "lang": lang, "lang_name": LANG_NAME[lang], "channel": channel,
            "lat": round(lat, 6), "lon": round(lon, 6), "ward": ward, "ward_name": self.ward_by_code[ward]["name"],
            "concepts": cons, "routing": route,
            "urgency": {"priority": pr, "label": C.PRIORITY_LABELS[pr], "reason": reason,
                        "probs": [round(v, 3) for v in probs], "rules": fired,
                        "top_words": [{"f": nm[2:], "w": round(v, 3)} for v, nm in utok[:5] if v > 0]},
            "duplicate": {"is_duplicate": bool(best), "of": best["id"] if best else None, "root": root,
                          "match": best, "checked": checked[:6], "lsh_candidates": len(cands),
                          "threshold": self.dup_threshold},
            "hotspot": hs, "emerging": em,
            "sla": {"days": sla_days, "due": G.iso(t_new + sla_days), "breach_risk": round(risk, 3),
                    "factors": factors, "backlog": backlog},
            "latency_ms": {k: round(v, 2) for k, v in stages.items()},
            "total_ms": round(total_ms, 2),
        }
        if record:
            self.clock = t_new
            cid = "C-%05d" % (10001 + len(self.complaints) + len(self.live))
            c = {"id": cid, "t": t_new, "ts": G.iso(t_new), "text": text, "lang": lang, "channel": channel,
                 "ward": ward, "lat": lat, "lon": lon, "pred_dept": dept, "conf": route["confidence"],
                 "priority": pr, "priority_reason": reason, "rules": [f["id"] for f in fired],
                 "dup_of": best["id"] if best else None, "root": root or cid, "closed_t": None, "res_days": None,
                 "status": "open", "week": G.week_of(min(t_new, self.now_t)), "dow": int(t_new) % 7,
                 "age_days": 0.0, "sla_days": sla_days, "breached": False, "backlog": backlog, "live": True,
                 "_sig": sig, "dept": None, "urgency": None, "incident": None, "issue": None,
                 "dup_info": ({"jaccard": best["jaccard"], "dist_m": best["dist_m"], "gap_h": best["gap_h"],
                               "p": best["score"]} if best else None), "breach_risk": round(risk, 3)}
            self.live.append(c)
            if best:
                for o in self.all_complaints():
                    if o["root"] == root:
                        o["inc_size"] = o.get("inc_size", 1) + 1
                c["inc_size"] = next((o["inc_size"] for o in self.all_complaints() if o["id"] == root), 2)
            else:
                c["inc_size"] = 1
            self._hot_cache = {}
            result["id"] = cid
            result["ts"] = c["ts"]
            self._save_filed()
        return result

    # ================================================================== scripted demo
    def _place(self, ward, typ=None, kind="lm"):
        for p in self.g["places"]:
            if p["ward"] == ward and p["kind"] == kind and (typ is None or p["name"].lower().endswith(typ)):
                return p
        return next(p for p in self.g["places"] if p["ward"] == ward)

    def demo_samples(self):
        """A scripted stream that exercises every stage: safety rule, cross-language duplicate,
        hotspot, emerging ward, typo tolerance, topic routing and the campus department."""
        rng = random.Random(42)
        out = []

        def jit(lat, lon, m=25.0):
            return round(lat + rng.uniform(-m, m) / 110574.0, 6), round(lon + rng.uniform(-m, m) / 109020.0, 6)

        p = self._place("W08")
        la, lo = jit(p["lat"], p["lon"])
        out.append({"label": "Live wire · Tanglish", "lang": "tg", "channel": "WhatsApp", "lat": la, "lon": lo,
                    "text": "%s kitta current wire thongitu iruku, romba danger. school pasanga intha vazhi la dhaan poraanga" % p["name_tg"]})
        cs = self.complaints
        prefer = ["light_not_working", "drain_overflow", "pipe_leak", "no_water", "pothole", "garbage_not_collected"]
        cand = [c for c in reversed(cs) if c["closed_t"] is None and c["root"] == c["id"] and c["place"]["kind"] == "lm"
                and c["issue"] in prefer and c["pred_dept"] == c["dept"] and not c["vague"]]
        cand.sort(key=lambda c: prefer.index(c["issue"]))
        if cand:
            c = cand[0]
            lang = "ta" if c["lang"] != "ta" else "en"
            r2 = random.Random(7)
            text = None
            for _ in range(20):
                tx, mods, _ = G.compose(r2, c["issue"], c["place"], lang, int(c["ward"][1:]))
                if not mods and "Also" not in tx and "மேலும்" not in tx:
                    text = tx
                    break
            text = text or tx
            la, lo = jit(c["lat"], c["lon"], 30)
            out.append({"label": "%s duplicate" % LANG_NAME[lang], "lang": lang, "channel": "App",
                        "lat": la, "lon": lo, "text": text, "expect_dup_of": c["id"]})
        p = self._place("W09", "hospital") if any(x["ward"] == "W09" and x["name"].endswith("hospital") for x in self.g["places"]) else self._place("W09")
        la, lo = jit(p["lat"], p["lon"])
        out.append({"label": "Sewage in water", "lang": "en", "channel": "Call centre", "lat": la, "lon": lo,
                    "text": "Sewage mixing in drinking water near %s, many children falling sick" % p["name"]})
        surge = next((h for h in self.planted if h["id"] == "E3"), None)
        if surge:
            p = next(x for x in self.g["places"] if x["ward"] == surge["ward"] and x["name"] == surge["place"])
            la, lo = jit(surge["center"][0], surge["center"][1], 60)
            out.append({"label": "Garbage · Tamil", "lang": "ta", "channel": "App", "lat": la, "lon": lo,
                        "text": "%s அருகில் ஒரு வாரமாக குப்பை அள்ளவில்லை, துர்நாற்றம் தாங்க முடியவில்லை" % p["name_ta"]})
        hs = next((h for h in self.planted if h["id"] == "H2"), None)
        if hs:
            la, lo = jit(hs["center"][0], hs["center"][1], 40)
            out.append({"label": "Typos + accident", "lang": "en", "channel": "Social media", "lat": la,
                        "lon": lo, "text": "Very big pothle near %s, acident happend yesterday nite, pls fix" % hs["place"]})
        p = self._place("W13")
        la, lo = jit(p["lat"], p["lon"])
        out.append({"label": "Noise", "lang": "en", "channel": "App", "lat": la, "lon": lo,
                    "text": "Loud music from marriage hall near %s till 1 am, loudspeaker noise every night" % p["name"]})
        p = self._place("W20", kind="campus")
        gh = next((x for x in self.g["places"] if x["ward"] == "W20" and x["name"] == "girls hostel"), p)
        la, lo = jit(gh["lat"], gh["lon"], 15)
        out.append({"label": "Hostel", "lang": "en", "channel": "App", "lat": la, "lon": lo,
                    "text": "No water in the bathrooms of girls hostel since morning, warden not responding"})
        p = self._place("W08")
        la, lo = jit(p["lat"], p["lon"], 30)
        out.append({"label": "Live wire again", "lang": "en", "channel": "Call centre", "lat": la, "lon": lo,
                    "text": "Live wire hanging near %s, very dangerous for children" % p["name"]})
        return out

    # ================================================================== persistence of filed complaints
    def _filed_path(self):
        return os.path.join(self.data_dir, "filed_complaints.json") if self.data_dir else None

    def _save_filed(self):
        p = self._filed_path()
        if not p:
            return
        rows = [{"text": c["text"], "lat": c["lat"], "lon": c["lon"], "channel": c["channel"]} for c in self.live]
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"filed": rows}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)

    def _replay_filed(self):
        p = self._filed_path()
        if not p or not os.path.exists(p):
            return
        try:
            with open(p, encoding="utf-8") as f:
                rows = json.load(f).get("filed", [])
        except (OSError, ValueError):
            return
        for r in rows[:500]:
            try:
                self.analyze(r["text"], float(r["lat"]), float(r["lon"]), r.get("channel", "App"), record=True)
            except (KeyError, TypeError, ValueError):
                continue

    def reset_live(self):
        self.live = []
        self.clock = self.now_t
        self._hot_cache = {}
        self._recount_incidents()
        p = self._filed_path()
        if p and os.path.exists(p):
            os.remove(p)

    def _recount_incidents(self):
        size = {}
        for c in self.complaints:
            size[c["root"]] = size.get(c["root"], 0) + 1
        for c in self.complaints:
            c["inc_size"] = size[c["root"]]

    # ================================================================== views
    def public(self, c, full=False):
        open_ = c.get("closed_t") is None
        age = (self.clock - c["t"]) if open_ else c["age_days"]
        out = {"id": c["id"], "ts": c["ts"], "text": c["text"], "lang": c["lang"], "channel": c["channel"],
               "ward": c["ward"], "ward_name": self.ward_by_code[c["ward"]]["name"], "lat": c["lat"], "lon": c["lon"],
               "dept": c["pred_dept"], "dept_name": C.DEPT_NAME[c["pred_dept"]], "conf": c["conf"],
               "priority": c["priority"], "priority_reason": c["priority_reason"], "rules": c["rules"],
               "dup_of": c["dup_of"], "root": c["root"], "inc_size": c.get("inc_size", 1),
               "status": "open" if open_ else "resolved", "age_days": round(age, 2), "sla_days": c["sla_days"],
               "due": G.iso(c["t"] + c["sla_days"]), "breached": age > c["sla_days"],
               "live": bool(c.get("live"))}
        if not open_:
            out["res_days"] = round(c["res_days"], 2)
        if c.get("dup_info"):
            out["dup_info"] = c["dup_info"]
        if full:
            out["ground_truth"] = None if c.get("live") else {
                "dept": c["dept"], "urgency": c["urgency"], "incident": c["incident"], "issue": c["issue"],
                "planted": c.get("planted")}
            out["siblings"] = [o["id"] for o in self.all_complaints() if o["root"] == c["root"] and o["id"] != c["id"]][:12]
            if open_:
                p, f = self.breach_risk(c)
                out["breach_risk"] = round(p, 3)
                out["breach_factors"] = f
        return out

    def queue(self, limit=40, dept=None, priority=None, status=None, q=None):
        rows = []
        for c in reversed(self.all_complaints()):
            if dept and c["pred_dept"] != dept:
                continue
            if priority and c["priority"] != priority:
                continue
            if status == "open" and c.get("closed_t") is not None:
                continue
            if q and q.lower() not in c["text"].lower() and q.upper() != c["id"]:
                continue
            rows.append(self.public(c))
            if len(rows) >= limit:
                break
        return rows

    def at_risk(self, limit=30):
        rows = []
        for c in self.all_complaints():
            if c.get("closed_t") is not None:
                continue
            age = self.clock - c["t"]
            if age > c["sla_days"]:
                continue
            p, f = self.breach_risk(c)
            r = self.public(c)
            r["breach_risk"] = round(p, 3)
            r["factors"] = f
            r["hours_left"] = round((c["t"] + c["sla_days"] - self.clock) * 24, 1)
            rows.append(r)
        rows.sort(key=lambda r: (-r["breach_risk"], r["hours_left"]))
        overdue = []
        for c in self.all_complaints():
            if c.get("closed_t") is None and self.clock - c["t"] > c["sla_days"]:
                r = self.public(c)
                r["overdue_days"] = round(self.clock - c["t"] - c["sla_days"], 2)
                overdue.append(r)
        overdue.sort(key=lambda r: (r["priority"], -r["overdue_days"]))
        return {"at_risk": rows[:limit], "n_at_risk": sum(1 for r in rows if r["breach_risk"] >= C.AT_RISK_THRESHOLD),
                "n_open_within_sla": len(rows), "overdue": overdue[:limit], "n_overdue": len(overdue),
                "threshold": C.AT_RISK_THRESHOLD}

    def summary(self):
        cs = self.all_complaints()
        open_ = [c for c in cs if c.get("closed_t") is None]
        breached_open = [c for c in open_ if self.clock - c["t"] > c["sla_days"]]
        recent = [c for c in self.complaints if c["week"] > C.N_WEEKS - 4]
        res = [c["res_days"] for c in recent if c.get("res_days") is not None]
        lab = [c for c in recent if c["t"] + c["sla_days"] <= self.now_t]
        weekly = [0] * C.N_WEEKS
        weekly_inc = [0] * C.N_WEEKS
        for c in self.complaints:
            weekly[c["week"] - 1] += 1
            if c["root"] == c["id"]:
                weekly_inc[c["week"] - 1] += 1
        by_dept = {d: 0 for d in C.DEPT_CODES}
        for c in cs:
            by_dept[c["pred_dept"]] += 1
        by_lang = {}
        for c in cs:
            by_lang[c["lang"]] = by_lang.get(c["lang"], 0) + 1
        by_channel = {}
        for c in cs:
            by_channel[c["channel"]] = by_channel.get(c["channel"], 0) + 1
        em = self.emerging(C.N_WEEKS)
        return {
            "town": C.TOWN_NAME, "now": G.iso(self.clock), "period": [G.iso(0)[:10], G.iso(self.now_t)[:10]],
            "kpis": {"complaints": len(cs), "open": len(open_), "open_breached": len(breached_open),
                     "p1_open": sum(1 for c in open_ if c["priority"] == 1),
                     "median_res_days_4w": _r(M.percentile(res, 0.5), 2) if res else None,
                     "sla_compliance_4w": _r(sum(1 for c in lab if not c["breached"]) / float(len(lab))) if lab else None,
                     "duplicates_merged": sum(1 for c in cs if c.get("dup_of")),
                     "incidents": sum(1 for c in cs if c["root"] == c["id"]),
                     "emerging_this_week": len(em), "live_filed": len(self.live)},
            "weekly": weekly, "weekly_incidents": weekly_inc,
            "week_starts": [G.iso(k * 7)[:10] for k in range(C.N_WEEKS)],
            "by_dept": [{"dept": d, "name": C.DEPT_NAME[d], "n": by_dept[d]} for d in C.DEPT_CODES],
            "by_lang": by_lang, "by_channel": by_channel, "emerging": em[:6],
            "headline": {"routing_acc": self.routing_eval["models"]["lr"]["accuracy"],
                         "routing_f1": self.routing_eval["models"]["lr"]["macro_f1"],
                         "dup_f1": self.dup_eval["pairwise"]["f1"], "hotspot_precision": self.hotspot_eval["precision"],
                         "hotspot_recall": self.hotspot_eval["persistent_recall"], "breach_auc": self.breach_eval["auc"]},
            "build_s": self.timings.get("total_build_s"),
        }

    def map_points(self, dept=None, weeks=None):
        pts = []
        lo_week = C.N_WEEKS - weeks + 1 if weeks else 1
        for c in self.all_complaints():
            if c["root"] != c["id"] or (dept and c["pred_dept"] != dept) or c["week"] < lo_week:
                continue
            pts.append([c["id"], round(c["lat"], 5), round(c["lon"], 5), C.DEPT_CODES.index(c["pred_dept"]),
                        c["priority"], 1 if c.get("closed_t") is None else 0, c.get("inc_size", 1), c["week"]])
        return {"fields": ["id", "lat", "lon", "dept", "priority", "open", "reports", "week"], "points": pts,
                "departments": C.DEPT_CODES}

    def town(self):
        return {"name": C.TOWN_NAME, "wards": self.wards, "places": self.g["places"],
                "bounds": [C.ORIGIN_LAT, C.ORIGIN_LON] + list(G.to_latlon(C.GRID_COLS * 1000.0 * C.WARD_KM,
                                                                          C.GRID_ROWS * 1000.0 * C.WARD_KM)),
                "departments": [{"code": d, "name": C.DEPT_NAME[d], "sla_days": C.SLA_DAYS[d]} for d in C.DEPT_CODES],
                "priorities": C.PRIORITY_LABELS, "channels": [c for c, _ in C.CHANNELS],
                "defaults": {"eps_m": C.DBSCAN_EPS_M, "min_pts": C.DBSCAN_MIN_PTS}}

    def models(self):
        return {"routing": self.routing_eval, "urgency": self.urgency_eval, "duplicates": self.dup_eval,
                "hotspots": self.hotspot_eval, "emerging": self.emerging_eval, "breach": self.breach_eval,
                "timings": self.timings}
