"""Crop recommendation: trains GNB + Random Forest on the synthetic set and explains output."""
import math
import threading
import time

from . import config, dataset
from .forest import RandomForest
from .gnb import GaussianNB

_lock = threading.Lock()
_model = None


class CropRecommender:
    def __init__(self, rf_params=None):
        rf_params = dict(rf_params or config.RF_PARAMS)
        X, y = dataset.generate()
        Xtr, ytr, Xte, yte = dataset.stratified_split(X, y)
        t0 = time.perf_counter()
        self.gnb = GaussianNB().fit(Xtr, ytr)
        t1 = time.perf_counter()
        self.rf = RandomForest(**rf_params).fit(Xtr, ytr)
        t2 = time.perf_counter()
        self.metrics = {
            "n_train": len(Xtr), "n_test": len(Xte), "n_crops": len(config.CROPS),
            "gnb_accuracy": accuracy([self.gnb.predict(x) for x in Xte], yte),
            "rf_accuracy": accuracy([self.rf.predict(x) for x in Xte], yte),
            "blend_accuracy": accuracy([top_k(self._blend(x), 1)[0][0] for x in Xte], yte),
            "gnb_top3_accuracy": topk_accuracy([self.gnb.predict_proba(x) for x in Xte], yte),
            "rf_top3_accuracy": topk_accuracy([self.rf.predict_proba(x) for x in Xte], yte),
            "rf_oob_accuracy": self.rf.oob_score,
            "gnb_train_ms": round((t1 - t0) * 1000, 1),
            "rf_train_ms": round((t2 - t1) * 1000, 1),
            "rf_trees": rf_params["n_trees"], "rf_max_depth": rf_params["max_depth"],
            "rf_max_features": rf_params["max_features"],
            "rf_feature_importance": dict(zip(config.FEATURES,
                                              [round(v, 4) for v in self.rf.feature_importances()])),
        }

    def _blend(self, x):
        pg = self.gnb.predict_proba(x)
        pr = self.rf.predict_proba(x)
        return {c: 0.5 * pg[c] + 0.5 * pr[c] for c in pg}

    def recommend(self, inputs):
        x = [float(inputs[f]) for f in config.FEATURES]
        pg = self.gnb.predict_proba(x)
        pr = self.rf.predict_proba(x)
        blend = {c: 0.5 * pg[c] + 0.5 * pr[c] for c in pg}
        top = top_k(blend, 3)
        best, runner = top[0][0], top[1][0]
        deltas, prior_delta = self.gnb.explain(x, best, runner)
        rf_bias, rf_contrib = self.rf.contributions(x, best)
        explanation = []
        for i, f in enumerate(config.FEATURES):
            mu = self.gnb.means[best][i]
            sd = math.sqrt(self.gnb.vars[best][i])
            lo, hi = config.CROP_RANGES[best][i]
            explanation.append({
                "feature": f, "value": x[i], "unit": config.FEATURE_UNITS[f],
                "gnb_log_odds": round(deltas[i], 3),
                "rf_contribution": round(rf_contrib[i], 4),
                "crop_mean": round(mu, 2), "crop_sd": round(sd, 2),
                "typical_range": [lo, hi],
                "z": round((x[i] - mu) / sd, 2) if sd else 0.0,
                "in_range": lo <= x[i] <= hi,
            })
        return {
            "inputs": dict(zip(config.FEATURES, x)),
            "top3": [_crop_entry(c, p) for c, p in top],
            "gnb_top3": [_crop_entry(c, p) for c, p in top_k(pg, 3)],
            "rf_top3": [_crop_entry(c, p) for c, p in top_k(pr, 3)],
            "explanation": {
                "crop": best, "versus": runner,
                "gnb_prior_log_odds": round(prior_delta, 3),
                "gnb_total_log_odds": round(sum(deltas) + prior_delta, 3),
                "rf_bias": round(rf_bias, 4),
                "features": explanation,
                "method": ("GNB: log N(x|crop) - log N(x|runner-up) per input. "
                           "RF: Saabas path contributions to P(crop)."),
            },
            "agreement": top_k(pg, 1)[0][0] == top_k(pr, 1)[0][0],
        }


def _crop_entry(c, p):
    return {"crop": c, "name": config.CROP_NAMES[c], "prob": round(p, 4)}


def top_k(prob, k):
    return sorted(prob.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


def accuracy(pred, truth):
    return round(sum(1 for a, b in zip(pred, truth) if a == b) / float(len(truth)), 4)


def topk_accuracy(probs, truth, k=3):
    hits = sum(1 for p, t in zip(probs, truth) if t in [c for c, _ in top_k(p, k)])
    return round(hits / float(len(truth)), 4)


def get_model():
    """Lazily train the shared model once (thread-safe)."""
    global _model
    with _lock:
        if _model is None:
            _model = CropRecommender()
        return _model
