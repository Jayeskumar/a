"""Per-sensor calibration of low-cost optical PM sensors against a co-located reference.

Two-stage, explainable model (fitted separately for PM2.5 and PM10):

1. Humidity growth correction (kappa-Koehler, as used by Crilley et al. 2018, AMT):
       PM_dry = PM_raw / (1 + (kappa / 1.65) * aw / (1 - aw)),   aw = RH / 100
   Wet particles swell and scatter more light, so optical sensors over-read when humid.
2. Multiple linear regression on the corrected signal, humidity and temperature:
       PM_ref = b0 + b1 * PM_dry + b2 * RH + b3 * T
   kappa is chosen by grid search to minimise the regression error on the training days.

The plain MLR (kappa = 0, i.e. PM_raw + RH + T) is kept as a comparison model.
"""

from . import config as C
from .mathx import errors, least_squares, predict

FEATURE_NAMES = ["PM_dry", "RH", "T"]
RH_CAP = 95.0   # growth formula diverges at 100% RH; cap as is common practice


def growth(rh, kappa):
    aw = min(max(rh, 0.0), RH_CAP) / 100.0
    return 1.0 + (kappa / 1.65) * aw / (1.0 - aw)


def features(raw, rh, temp, kappa):
    return [raw / growth(rh, kappa), rh, temp]


def _rows(samples, kappa):
    return [features(r, h, t, kappa) for r, h, t, _ in samples]


def fit(samples, kappa_grid=None, ridge=C.RIDGE_LAMBDA):
    """samples: list of (raw, rh, temp, ref). Returns the best model over kappa_grid."""
    samples = [s for s in samples if None not in s]
    if len(samples) < 12:
        raise ValueError("need at least 12 co-located hours to calibrate")
    y = [s[3] for s in samples]
    tried = {}

    def score(kappa):
        if kappa not in tried:
            rows = _rows(samples, kappa)
            m = least_squares(rows, y, ridge)
            tried[kappa] = (sum((predict(m, f) - t) ** 2 for f, t in zip(rows, y)), kappa, m)
        return tried[kappa]

    if kappa_grid is not None:
        best = min((score(k) for k in kappa_grid), key=lambda b: b[0])
    else:   # coarse-to-fine grid search over kappa in config.KAPPA_RANGE
        lo, hi = C.KAPPA_RANGE
        coarse = [round(lo + i * (hi - lo) / 10.0, 4) for i in range(11)]
        best = min((score(k) for k in coarse), key=lambda b: b[0])
        step = (hi - lo) / 10.0
        fine = [round(best[1] + j * step / 5.0, 4) for j in range(-5, 6)]
        best = min((score(k) for k in fine if lo <= k <= hi), key=lambda b: b[0])
    sse, kappa, m = best
    return {"kappa": kappa, "intercept": m["intercept"], "coef": m["coef"],
            "features": FEATURE_NAMES, "n_train": len(samples)}


def apply(model, raw, rh, temp):
    if raw is None or rh is None or temp is None:
        return None
    v = predict(model, features(raw, rh, temp, model["kappa"]))
    return max(0.0, v)


def explain(model, raw, rh, temp):
    """Contribution of each term to one calibrated value (for the UI 'why')."""
    f = features(raw, rh, temp, model["kappa"])
    parts = [{"term": "intercept", "value": round(model["intercept"], 2)}]
    for name, c, x in zip(FEATURE_NAMES, model["coef"], f):
        parts.append({"term": name, "coef": round(c, 4), "x": round(x, 2), "value": round(c * x, 2)})
    return {"growth_factor": round(growth(rh, model["kappa"]), 3), "parts": parts,
            "calibrated": round(apply(model, raw, rh, temp), 1)}


def calibrate_sensor(train, test):
    """Fit hybrid and MLR-only models on train, report errors on held-out test."""
    hybrid = fit(train)
    mlr = fit(train, kappa_grid=[0.0])
    test = [s for s in test if None not in s]
    ref = [s[3] for s in test]
    raw_pred = [s[0] for s in test]
    mlr_pred = [apply(mlr, s[0], s[1], s[2]) for s in test]
    hyb_pred = [apply(hybrid, s[0], s[1], s[2]) for s in test]
    return {"model": hybrid, "mlr": mlr,
            "test": {"raw": errors(raw_pred, ref), "mlr": errors(mlr_pred, ref),
                     "hybrid": errors(hyb_pred, ref)}}
