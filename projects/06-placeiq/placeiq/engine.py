"""PlaceIQ engine: owns the current dataset and every trained artefact.

No HTTP code here - app.py calls these methods and serialises the dicts.
"""

import math
import threading
import time

from . import cluster, config as C, data, explain, metrics, stats
from .models import LinearRegression, LogisticRegression, StandardScaler, kfold_indices, stratified_split

FAIRNESS_GAP = 0.10    # flag a department whose error rate differs from overall by > 10 points (rule of thumb)
FAIRNESS_WATCH = 0.05  # "watch" a department whose mean probability is off its actual rate by > 5 points


def _vec(row):
    return [float(row[f]) for f in C.FEATURE_NAMES]


def _r(x, n=4):
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return round(x, n)
    return x


def _fit_logreg(X, y):
    sc = StandardScaler().fit(X)
    m = LogisticRegression(C.LOGREG_LR, C.LOGREG_L2, C.LOGREG_MAX_ITER, C.LOGREG_TOL).fit(sc.transform(X), y)
    return sc, m


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.load_demo()

    # ------------------------------------------------------------------ loading
    def load_demo(self):
        rows = data.generate()
        self._load(rows, "Synthetic demo cohort (seed %d)" % C.SEED, None)
        return self.dataset_info()

    def load_csv(self, text, filename="upload.csv"):
        rows, report = data.validate_csv(text)
        labelled = [r for r in rows if r["placed"] in (0, 1)]
        classes = {r["placed"] for r in labelled}
        if report["missing_columns"]:
            return False, report, "Missing required column(s): " + ", ".join(report["missing_columns"])
        if len(labelled) < C.MIN_TRAIN_ROWS or len(classes) < 2:
            return False, report, ("Need at least %d valid labelled rows with both placed and not-placed "
                                   "students to train (got %d)." % (C.MIN_TRAIN_ROWS, len(labelled)))
        self._load(rows, "Uploaded file: %s" % filename, report)
        return True, report, "Loaded %d valid rows; %d rejected." % (report["valid_rows"], report["invalid_rows"])

    def _load(self, rows, source, report):
        t0 = time.time()
        with self.lock:
            self.rows = rows
            self.by_id = {r["student_id"]: r for r in rows}
            self.source = source
            self.upload_report = report
            self._cluster_cache, self._plan_cache, self._eda = {}, {}, None
            self._train()
            self.train_seconds = time.time() - t0

    # ---------------------------------------------------------------- training
    def _train(self):
        lab = [r for r in self.rows if r["placed"] in (0, 1)]
        self.labelled = lab
        X = [_vec(r) for r in lab]
        y = [r["placed"] for r in lab]
        # 1) honest hold-out evaluation
        tr, te = stratified_split(y, C.TEST_FRACTION, C.SEED)
        sc, m = _fit_logreg([X[i] for i in tr], [y[i] for i in tr])
        p_te = m.predict_proba(sc.transform([X[i] for i in te]))
        y_te = [y[i] for i in te]
        rep = metrics.classification_report(y_te, [1 if p >= 0.5 else 0 for p in p_te])
        rep["roc_auc"] = metrics.roc_auc(y_te, p_te)
        p_tr = m.predict_proba(sc.transform([X[i] for i in tr]))
        rep["train_accuracy"] = metrics.classification_report([y[i] for i in tr],
                                                              [1 if p >= 0.5 else 0 for p in p_tr])["accuracy"]
        rep["train_auc"] = metrics.roc_auc([y[i] for i in tr], p_tr)
        rep["n_train"], rep["n_test"] = len(tr), len(te)
        rep["base_rate_test"] = sum(y_te) / len(y_te)
        rep["majority_baseline_accuracy"] = max(rep["base_rate_test"], 1 - rep["base_rate_test"])
        rep["iterations"], rep["converged"] = m.n_iter, m.converged
        self.eval = rep
        self.roc = metrics.roc_curve(y_te, p_te)
        self.loss_history = m.loss_history
        # 2) out-of-fold predictions (for fairness)
        oof = [0.0] * len(lab)
        for ftr, fte in kfold_indices(len(lab), C.CV_FOLDS, C.SEED):
            fsc, fm = _fit_logreg([X[i] for i in ftr], [y[i] for i in ftr])
            for i, p in zip(fte, fm.predict_proba(fsc.transform([X[i] for i in fte]))):
                oof[i] = p
        self.oof = oof
        cv_auc = metrics.roc_auc(y, oof)
        self.eval["cv_auc"] = cv_auc
        self.eval["cv_accuracy"] = metrics.classification_report(y, [1 if p >= 0.5 else 0 for p in oof])["accuracy"]
        # 3) deployed model, refit on every labelled row
        self.scaler, self.model = _fit_logreg(X, y)
        for r in self.rows:
            r["_p"] = self.model.predict_proba_row(self.scaler.transform_row(_vec(r)))
        # 4) package regression on placed students with a known package
        pr = [r for r in lab if r["placed"] == 1 and r.get("package_lpa") not in (None, 0, 0.0)]
        self.package = None
        if len(pr) >= 20:
            PX = [_vec(r) for r in pr]
            Py = [float(r["package_lpa"]) for r in pr]
            ptr, pte = stratified_split([0] * len(pr), C.TEST_FRACTION, C.SEED + 1)
            psc = StandardScaler().fit([PX[i] for i in ptr])
            lr = LinearRegression(C.RIDGE_PACKAGE).fit(psc.transform([PX[i] for i in ptr]), [Py[i] for i in ptr])
            pred = lr.predict(psc.transform([PX[i] for i in pte]))
            yt = [Py[i] for i in pte]
            mean_tr = sum(Py[i] for i in ptr) / len(ptr)
            fsc = StandardScaler().fit(PX)
            flr = LinearRegression(C.RIDGE_PACKAGE).fit(fsc.transform(PX), Py)
            self.package = {
                "n_train": len(ptr), "n_test": len(pte),
                "r2": metrics.r2_score(yt, pred), "mae": metrics.mae(yt, pred), "rmse": metrics.rmse(yt, pred),
                "baseline_mae": metrics.mae(yt, [mean_tr] * len(yt)),
                "scaler": fsc, "model": flr,
                "points": [{"actual": a, "pred": b} for a, b in zip(yt, pred)],
            }

    # ------------------------------------------------------------------ helpers
    def predict(self, x):
        z = self.scaler.transform_row(x)
        p = self.model.predict_proba_row(z)
        pkg = None
        if self.package:
            pkg = max(0.0, self.package["model"].predict_row(self.package["scaler"].transform_row(x)))
        return p, pkg

    def plan_for(self, row, target=C.TARGET_PROBABILITY):
        key = (row["student_id"], round(target, 3))
        if key not in self._plan_cache:
            self._plan_cache[key] = explain.counterfactual(self.model, self.scaler, _vec(row), target)
        return self._plan_cache[key]

    @staticmethod
    def status(row):
        return {1: "Placed", 0: "Not placed"}.get(row["placed"], "Pending")

    def _filter(self, dept=None, batch=None):
        rows = self.rows
        if dept and dept != "ALL":
            rows = [r for r in rows if r["dept"] == dept]
        if batch and batch != "ALL":
            rows = [r for r in rows if str(r["batch"]) == str(batch)]
        return rows

    def _public(self, r):
        d = {k: v for k, v in r.items() if not k.startswith("_")}
        d["probability"] = _r(r["_p"])
        d["status"] = self.status(r)
        return d

    # --------------------------------------------------------------- endpoints
    def dataset_info(self):
        labelled = len(self.labelled)
        return {
            "source": self.source, "rows": len(self.rows), "labelled_rows": labelled,
            "pending_rows": len(self.rows) - labelled,
            "departments": sorted({r["dept"] for r in self.rows}, key=lambda d: C.DEPARTMENTS.index(d)),
            "batches": sorted({str(r["batch"]) for r in self.rows}),
            "columns": C.ALL_COLUMNS, "required_columns": C.REQUIRED_COLUMNS,
            "train_seconds": _r(self.train_seconds, 2),
            "upload_report": self.upload_report,
        }

    def eda(self):
        if self._eda is not None:
            return self._eda
        rows = self.rows
        lab = self.labelled
        cols = {}
        for name, label, lo, hi, is_int in C.FEATURES:
            xs = [float(r[name]) for r in rows]
            s = {k: _r(v) for k, v in stats.summary(xs).items()}
            s.update({"feature": name, "label": label,
                      "histogram": [{"lo": _r(b["lo"]), "hi": _r(b["hi"]), "count": b["count"]}
                                    for b in stats.histogram(xs, 12, is_int)]})
            cols[name] = s
        pk = [float(r["package_lpa"]) for r in lab if r["placed"] == 1 and r.get("package_lpa")]
        package = {k: _r(v) for k, v in stats.summary(pk).items()} if pk else None
        if pk:
            package["histogram"] = [{"lo": _r(b["lo"]), "hi": _r(b["hi"]), "count": b["count"]}
                                    for b in stats.histogram(pk, 12)]
        corr_cols = {n: [float(r[n]) for r in lab] for n in C.FEATURE_NAMES}
        corr_cols["placed"] = [float(r["placed"]) for r in lab]
        names, mat = stats.correlation_matrix(corr_cols)
        self._eda = {
            "n": len(rows), "columns": [cols[n] for n in C.FEATURE_NAMES], "package": package,
            "dept_rates": self.dept_rates(rows),
            "correlation": {"names": names, "labels": [C.FEATURE_LABELS.get(n, "Placed") for n in names],
                            "matrix": [[_r(v, 3) for v in row] for row in mat]},
            "drivers": self.drivers(),
        }
        return self._eda

    def dept_rates(self, rows):
        out = []
        for d in C.DEPARTMENTS:
            dr = [r for r in rows if r["dept"] == d and r["placed"] in (0, 1)]
            if not dr:
                continue
            placed = [r for r in dr if r["placed"] == 1]
            pk = [float(r["package_lpa"]) for r in placed if r.get("package_lpa")]
            out.append({"dept": d, "n": len(dr), "placed": len(placed), "rate": _r(len(placed) / len(dr)),
                        "avg_package": _r(stats.mean(pk), 2) if pk else None})
        return out

    def drivers(self):
        lab = self.labelled
        y = [float(r["placed"]) for r in lab]
        out = []
        for j, name in enumerate(C.FEATURE_NAMES):
            xs = [float(r[name]) for r in lab]
            q1, q3 = stats.quantile(xs, 0.25), stats.quantile(xs, 0.75)
            lo = [r["placed"] for r in lab if float(r[name]) <= q1]
            hi = [r["placed"] for r in lab if float(r[name]) >= q3]
            out.append({
                "feature": name, "label": C.FEATURE_LABELS[name],
                "coefficient": _r(self.model.w[j]),
                "odds_ratio_per_sd": _r(math.exp(self.model.w[j])),
                "correlation": _r(stats.pearson(xs, y)),
                "rate_bottom_quartile": _r(stats.mean(lo)) if lo else None,
                "rate_top_quartile": _r(stats.mean(hi)) if hi else None,
            })
        out.sort(key=lambda d: -abs(d["coefficient"]))
        return out

    def model_info(self):
        e = self.eval
        res = {
            "test": {k: _r(v) for k, v in e.items() if k != "confusion"},
            "confusion": e["confusion"],
            "roc": [{"fpr": _r(p["fpr"]), "tpr": _r(p["tpr"]), "threshold": _r(p["threshold"])} for p in self.roc],
            "loss_history": self.loss_history,
            "coefficients": [{"feature": n, "label": C.FEATURE_LABELS[n], "weight": _r(w)}
                             for n, w in zip(C.FEATURE_NAMES, self.model.w)],
            "intercept": _r(self.model.b),
            "scaler": {"mean": [_r(v) for v in self.scaler.mean], "std": [_r(v) for v in self.scaler.std]},
            "features": [{"feature": n, "label": l, "min": lo, "max": hi, "integer": i}
                         for n, l, lo, hi, i in C.FEATURES],
            "hyperparameters": {"lr": C.LOGREG_LR, "l2": C.LOGREG_L2, "max_iter": C.LOGREG_MAX_ITER,
                                "tol": C.LOGREG_TOL, "test_fraction": C.TEST_FRACTION, "cv_folds": C.CV_FOLDS},
            "package": None,
            "fairness": self.fairness(),
            "actions": {k: {"step": v[0], "max_total": v[1], "effort_weeks": v[2]} for k, v in C.ACTIONS.items()},
            "target": C.TARGET_PROBABILITY,
        }
        if self.package:
            p = self.package
            res["package"] = {"n_train": p["n_train"], "n_test": p["n_test"], "r2": _r(p["r2"]),
                              "mae": _r(p["mae"], 3), "rmse": _r(p["rmse"], 3),
                              "baseline_mae": _r(p["baseline_mae"], 3),
                              "points": [{"actual": _r(q["actual"], 2), "pred": _r(q["pred"], 2)} for q in p["points"]],
                              "coefficients": [{"feature": n, "label": C.FEATURE_LABELS[n], "weight": _r(w)}
                                               for n, w in zip(C.FEATURE_NAMES, p["model"].w)],
                              "intercept": _r(p["model"].b),
                              "scaler": {"mean": [_r(v) for v in p["scaler"].mean],
                                         "std": [_r(v) for v in p["scaler"].std]}}
        return res

    def fairness(self, threshold=0.5):
        lab, oof = self.labelled, self.oof
        y = [r["placed"] for r in lab]
        pred = [1 if p >= threshold else 0 for p in oof]
        overall = metrics.classification_report(y, pred)
        groups, notes, watch = [], [], []
        for d in C.DEPARTMENTS:
            idx = [i for i, r in enumerate(lab) if r["dept"] == d]
            if not idx:
                continue
            yt, yp, pp = [y[i] for i in idx], [pred[i] for i in idx], [oof[i] for i in idx]
            rep = metrics.classification_report(yt, yp)
            g = {"dept": d, "n": len(idx), "actual_rate": _r(stats.mean(yt)),
                 "predicted_rate": _r(stats.mean(yp)), "mean_probability": _r(stats.mean(pp)),
                 "accuracy": _r(rep["accuracy"]), "fpr": _r(rep["fpr"]), "fnr": _r(rep["fnr"]),
                 "calibration_gap": _r(stats.mean(pp) - stats.mean(yt))}
            flags = []
            if abs(rep["fpr"] - overall["fpr"]) > FAIRNESS_GAP:
                flags.append("FPR %+.0f pts" % (100 * (rep["fpr"] - overall["fpr"])))
            if abs(rep["fnr"] - overall["fnr"]) > FAIRNESS_GAP:
                flags.append("FNR %+.0f pts" % (100 * (rep["fnr"] - overall["fnr"])))
            if abs(g["calibration_gap"]) > FAIRNESS_GAP:
                flags.append("%s by %.0f pts" % ("over-predicts" if g["calibration_gap"] > 0 else "under-predicts",
                                                 100 * abs(g["calibration_gap"])))
            g["flags"] = flags
            g["watch"] = []
            if not flags and abs(g["calibration_gap"]) > FAIRNESS_WATCH:
                g["watch"].append("%s by %.0f pts" % ("over-predicts" if g["calibration_gap"] > 0 else "under-predicts",
                                                      100 * abs(g["calibration_gap"])))
                watch.append("%s: %s" % (d, g["watch"][0]))
            if flags:
                notes.append("%s: %s" % (d, "; ".join(flags)))
            groups.append(g)
        return {"threshold": threshold, "method": "%d-fold out-of-fold predictions" % C.CV_FOLDS,
                "overall": {"accuracy": _r(overall["accuracy"]), "fpr": _r(overall["fpr"]),
                            "fnr": _r(overall["fnr"]), "n": len(y)},
                "groups": groups, "flag_threshold": FAIRNESS_GAP, "watch_threshold": FAIRNESS_WATCH,
                "notes": notes, "watch": watch,
                "dept_used_as_feature": False}

    def students(self, dept=None, batch=None, q=None, limit=1000):
        rows = self._filter(dept, batch)
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r["student_id"].lower() or ql in str(r.get("name", "")).lower()]
        rows = sorted(rows, key=lambda r: r["_p"])
        return [self._public(r) for r in rows[:limit]]

    def student(self, sid, target=C.TARGET_PROBABILITY):
        r = self.by_id.get(sid)
        if r is None:
            return None
        return self.explain_vector(_vec(r), target, base=self._public(r), row=r)

    def explain_vector(self, x, target=C.TARGET_PROBABILITY, base=None, row=None):
        p, pkg = self.predict(x)
        contrib = explain.contributions(self.model, self.scaler, x)
        plan = self.plan_for(row, target) if row is not None else explain.counterfactual(self.model, self.scaler, x, target)
        out = dict(base or {})
        out.update({
            "probability": _r(p), "logit": _r(self.model.decision(self.scaler.transform_row(x))),
            "baseline_probability": _r(1 / (1 + math.exp(-self.model.b))),
            "expected_package_lpa": _r(pkg, 2) if pkg is not None else None,
            "contributions": [{k: _r(v) for k, v in c.items()} for c in contrib],
            "plan": _clean(plan),
            "top_gap": _clean(explain.top_gap(plan)),
        })
        if row is not None:
            out["persona"] = self.persona_of(row)
        return out

    def at_risk(self, threshold=C.DEFAULT_RISK_THRESHOLD, dept=None, batch=None, include_placed=False):
        rows = [r for r in self._filter(dept, batch) if r["_p"] < threshold]
        if not include_placed:
            rows = [r for r in rows if r["placed"] != 1]
        rows.sort(key=lambda r: r["_p"])
        out = []
        for r in rows:
            plan = self.plan_for(r)
            gap = explain.top_gap(plan)
            d = self._public(r)
            d.update({"top_gap": gap["text"] if gap else "No single lever available",
                      "top_gap_feature": gap["feature"] if gap else None,
                      "plan_effort_weeks": _r(plan.get("total_effort_weeks")),
                      "plan_reachable": plan.get("reachable"),
                      "plan_p_after": _r(plan.get("p_after"))})
            out.append(d)
        return out

    def at_risk_csv(self, threshold=C.DEFAULT_RISK_THRESHOLD, dept=None, batch=None, include_placed=False):
        rows = self.at_risk(threshold, dept, batch, include_placed)
        cols = ["student_id", "name", "dept", "batch", "status", "probability", "top_gap",
                "plan_effort_weeks", "plan_p_after", "cgpa", "backlogs", "projects", "internships",
                "coding_problems", "aptitude_score", "communication_score", "mock_interview_score"]
        return data.to_csv(rows, cols)

    def clusters(self, k=C.DEFAULT_K):
        k = int(k)
        if k in self._cluster_cache:
            return self._cluster_cache[k]
        rows = self.rows
        feats = C.CLUSTER_FEATURES
        X = [[float(r[f]) for f in feats] for r in rows]
        sc = StandardScaler().fit(X)
        Z = sc.transform(X)
        res = cluster.kmeans(Z, k, seed=C.SEED)
        labels = res["labels"]
        ps = [r["_p"] for r in rows]
        p_mean, p_sd = stats.mean(ps), stats.std(ps) or 1.0
        profiles, groups = [], []
        for c in range(k):
            idx = [i for i, l in enumerate(labels) if l == c]
            members = [rows[i] for i in idx]
            zc = {f: stats.mean([Z[i][j] for i in idx]) if idx else 0.0 for j, f in enumerate(feats)}
            zc["_placed"] = (stats.mean([ps[i] for i in idx]) - p_mean) / p_sd if idx else 0.0
            profiles.append(zc)
            lab = [m for m in members if m["placed"] in (0, 1)]
            groups.append({
                "size": len(members),
                "means": {f: _r(stats.mean([float(m[f]) for m in members]), 2) for f in feats},
                "z": {f: _r(zc[f], 3) for f in feats},
                "placement_rate": _r(stats.mean([m["placed"] for m in lab])) if lab else None,
                "mean_probability": _r(stats.mean([m["_p"] for m in members])),
                "dept_mix": {d: sum(1 for m in members if m["dept"] == d) for d in C.DEPARTMENTS},
                "examples": [m["student_id"] for m in sorted(members, key=lambda m: m["_p"])[:3]],
            })
        names = cluster.name_clusters(profiles)
        for c, g in enumerate(groups):
            g["id"] = c
            g["name"], g["description"] = names[c]
        order = sorted(range(k), key=lambda c: -(groups[c]["mean_probability"] or 0))
        remap = {old: new for new, old in enumerate(order)}
        groups = [groups[c] for c in order]
        for new, g in enumerate(groups):
            g["id"] = new
        assign = {r["student_id"]: remap[l] for r, l in zip(rows, labels)}
        out = {"k": k, "features": feats, "labels": [C.FEATURE_LABELS[f] for f in feats],
               "inertia": _r(res["inertia"], 2), "iterations": res["iterations"], "clusters": groups,
               "assignments": assign}
        self._cluster_cache[k] = out
        return out

    def persona_of(self, row):
        cl = self.clusters(C.DEFAULT_K)
        cid = cl["assignments"].get(row["student_id"])
        if cid is None:
            return None
        return {"id": cid, "name": cl["clusters"][cid]["name"]}

    def dashboard(self, dept=None, batch=None, threshold=C.DEFAULT_RISK_THRESHOLD):
        rows = self._filter(dept, batch)
        lab = [r for r in rows if r["placed"] in (0, 1)]
        placed = [r for r in lab if r["placed"] == 1]
        pk = sorted(float(r["package_lpa"]) for r in placed if r.get("package_lpa"))
        risk = [r for r in rows if r["_p"] < threshold and r["placed"] != 1]
        bands = [("< 30%", 0, 0.3), ("30-50%", 0.3, 0.5), ("50-70%", 0.5, 0.7), ("70-90%", 0.7, 0.9), ("≥ 90%", 0.9, 1.01)]
        cl = self.clusters(C.DEFAULT_K)
        persona_counts = {}
        for r in rows:
            cid = cl["assignments"].get(r["student_id"])
            persona_counts[cid] = persona_counts.get(cid, 0) + 1
        gap_counts = {}
        for r in risk:
            g = explain.top_gap(self.plan_for(r))
            if g:
                gap_counts[g["label"]] = gap_counts.get(g["label"], 0) + 1
        return {
            "filters": {"dept": dept or "ALL", "batch": batch or "ALL"},
            "kpis": {
                "students": len(rows), "labelled": len(lab), "placed": len(placed),
                "placement_rate": _r(len(placed) / len(lab)) if lab else None,
                "avg_package": _r(stats.mean(pk), 2) if pk else None,
                "median_package": _r(stats.quantile(pk, 0.5), 2) if pk else None,
                "max_package": _r(max(pk), 2) if pk else None,
                "at_risk": len(risk),
                "mean_probability": _r(stats.mean([r["_p"] for r in rows])) if rows else None,
                "test_auc": _r(self.eval["roc_auc"]), "test_accuracy": _r(self.eval["accuracy"]),
            },
            "dept_rates": self.dept_rates(self._filter(None, batch)),
            "probability_bands": [{"band": b, "count": sum(1 for r in rows if lo <= r["_p"] < hi)} for b, lo, hi in bands],
            "personas": [{"id": g["id"], "name": g["name"], "count": persona_counts.get(g["id"], 0)} for g in cl["clusters"]],
            "top_gaps": sorted(({"label": k, "count": v} for k, v in gap_counts.items()), key=lambda d: -d["count"]),
            "batches": self._batch_trend(),
        }

    def _batch_trend(self):
        out = []
        for b in sorted({str(r["batch"]) for r in self.rows}):
            lab = [r for r in self.rows if str(r["batch"]) == b and r["placed"] in (0, 1)]
            if lab:
                out.append({"batch": b, "n": len(lab), "rate": _r(stats.mean([r["placed"] for r in lab]))})
        return out


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _r(obj)
