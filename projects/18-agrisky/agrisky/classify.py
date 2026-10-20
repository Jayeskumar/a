"""Explainable stress classification of management zones (an ordered decision list).

Each zone's mean band / index values are compared with a *reference canopy* taken from the
same flight (median of the top-quartile-NDVI crop cells), so the rules adapt to crop stage,
light and camera calibration. Rules are checked in order and the first one that fires wins:

  1. NDWI > 0                                   -> open water / channel   (never sprayed)
  2. NDVI < 0.35                                -> bare soil / bund       (never sprayed)
  3. NDWI >= ref + 0.08 and Red <= 1.35 x ref   -> waterlogging (wet, dark background)
  4. NIR <= 0.87 x ref and Red >= 1.25 x ref
     (or NDVI falling 0.06/week faster than the field) -> pest damage (tissue / canopy lost)
  5. NDRE <= 0.90 x ref (canopy still intact)   -> nitrogen deficiency (chlorophyll loss)
  6. otherwise                                  -> healthy
"""
from . import config


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def median(values):
    return percentile(values, 50)


def reference(feat):
    """Reference canopy values from the top-quartile NDVI crop cells of this flight."""
    ndvi, ndwi = feat["ndvi"], feat["ndwi"]
    crop = [i for i in range(len(ndvi))
            if ndvi[i] >= config.RULE_SOIL_NDVI and ndwi[i] < config.RULE_WATER_NDWI]
    if not crop:
        crop = list(range(len(ndvi)))
    cut = percentile([ndvi[i] for i in crop], config.REFERENCE_PERCENTILE)
    ref_cells = [i for i in crop if ndvi[i] >= cut] or crop
    ref = {k: median([feat[k][i] for i in ref_cells])
           for k in ("ndvi", "gndvi", "ndre", "savi", "ndwi", "red", "nir", "green", "rededge")}
    ref["cells"] = len(ref_cells)
    ref["crop_cells"] = len(crop)
    if "dndvi" in feat:
        ref["dndvi"] = median([feat["dndvi"][i] for i in crop])
    return ref


def _ratio(v, r):
    return v / r if r else 0.0


def _conf(margin, scale):
    """Map how far past a threshold a value is to a 0.55-0.99 confidence."""
    m = max(0.0, margin) / scale
    return round(min(0.99, 0.55 + 0.44 * min(1.0, m)), 2)


def classify_zone(z, ref, weeks=None):
    """z: zone stats dict (means). weeks: weeks since previous flight (None = no history).

    Returns {"label", "severity", "confidence", "trace": [...], "why": str, "spreading"}.
    """
    trace = []

    def test(name, desc, value, op, threshold, fmt="%.3f"):
        ok = value > threshold if op == ">" else value >= threshold if op == ">=" else \
            value < threshold if op == "<" else value <= threshold
        trace.append({"rule": name, "test": desc, "value": round(value, 4), "op": op,
                      "threshold": round(threshold, 4), "passed": ok,
                      "text": "%s = %s %s %s" % (desc, fmt % value, op, fmt % threshold)})
        return ok

    ndvi, ndwi, red, nir, ndre = z["ndvi"], z["ndwi"], z["red"], z["nir"], z["ndre"]
    d_ndwi = ndwi - ref["ndwi"]
    red_r = _ratio(red, ref["red"])
    nir_r = _ratio(nir, ref["nir"])
    ndre_r = _ratio(ndre, ref["ndre"])
    rate = None
    if weeks and "dndvi" in z and "dndvi" in ref:
        rate = (z["dndvi"] - ref["dndvi"]) / weeks
    spreading = rate is not None and rate <= config.RULE_ACTIVE_DECLINE_WEEK

    result = None
    if test("water", "NDWI", ndwi, ">", config.RULE_WATER_NDWI):
        result = ("water", 1.0, _conf(ndwi - config.RULE_WATER_NDWI, 0.2),
                  "NDWI %.2f is above 0: the surface reflects more green than NIR, which only "
                  "open water does. Irrigation channel - never spray here." % ndwi)
    elif test("soil", "NDVI", ndvi, "<", config.RULE_SOIL_NDVI):
        result = ("soil", 1.0, _conf(config.RULE_SOIL_NDVI - ndvi, 0.15),
                  "NDVI %.2f is below %.2f: almost no green canopy - bund or bare soil."
                  % (ndvi, config.RULE_SOIL_NDVI))
    else:
        wet = test("waterlogging", "NDWI − ref", d_ndwi, ">=", config.RULE_WATERLOG_NDWI_DELTA)
        dark = test("waterlogging", "Red ÷ ref", red_r, "<=", config.RULE_WATERLOG_RED_RATIO)
        if wet and dark:
            sev = min(1.0, d_ndwi / 0.3)
            result = ("waterlogging", sev,
                      min(_conf(d_ndwi - config.RULE_WATERLOG_NDWI_DELTA, 0.08),
                          _conf(config.RULE_WATERLOG_RED_RATIO - red_r, 0.25)),
                      "NDWI is %.2f above the healthy canopy (wetter) and red stays dark "
                      "(%.2f x reference): standing water under the plants, not exposed soil. "
                      "Drain the patch; hold urea until it dries." % (d_ndwi, red_r))
        else:
            lost = test("pest", "NIR ÷ ref", nir_r, "<=", config.RULE_PEST_NIR_RATIO)
            if lost:
                lost = test("pest", "Red ÷ ref", red_r, ">=", config.RULE_PEST_RED_RATIO)
            fast = False
            if rate is not None:
                fast = test("pest", "ΔNDVI/week vs field", rate, "<=",
                            2 * config.RULE_ACTIVE_DECLINE_WEEK)
            if lost or fast:
                sev = min(1.0, max(0.0, (1.0 - nir_r) / 0.5))
                why = ("NIR is only %.0f%% of the healthy canopy: leaf tissue and canopy are "
                       "being lost while red rises (%.2f x)" % (nir_r * 100, red_r))
                if spreading:
                    why += ", and NDVI fell %.3f/week faster than the rest of the field - an " \
                           "active, spreading attack" % -rate
                why += ". Spot-spray this zone plus a %d m ring." % config.PEST_BUFFER_M
                result = ("pest", sev,
                          _conf(config.RULE_PEST_NIR_RATIO - nir_r, 0.15) if lost else 0.6, why)
            elif test("nitrogen", "NDRE ÷ ref", ndre_r, "<=", config.RULE_N_NDRE_RATIO):
                deficit = 1.0 - ndre_r
                sev = min(1.0, deficit / (2 * config.UREA_DEFICIT_REF))
                result = ("nitrogen", sev, _conf(config.RULE_N_NDRE_RATIO - ndre_r, 0.15),
                          "Canopy is intact (NIR %.0f%% of reference) but the red-edge index "
                          "NDRE is %.0f%% lower: chlorophyll loss, the classic sign of nitrogen "
                          "deficiency. Top-dress urea here only." % (nir_r * 100, deficit * 100))
            else:
                margin = min(nir_r - config.RULE_PEST_NIR_RATIO, ndre_r - config.RULE_N_NDRE_RATIO)
                result = ("healthy", 0.0, _conf(margin, 0.08),
                          "All stress tests fail: NIR %.0f%% and NDRE %.0f%% of the reference "
                          "canopy. No treatment needed." % (nir_r * 100, ndre_r * 100))
    label, sev, conf, why = result
    return {"label": label, "severity": round(sev, 3), "confidence": conf, "why": why,
            "spreading": bool(spreading and label == "pest"),
            "ndvi_rate_week": None if rate is None else round(rate, 4),
            "ratios": {"nir": round(nir_r, 3), "red": round(red_r, 3), "ndre": round(ndre_r, 3),
                       "ndwi_delta": round(d_ndwi, 3)},
            "trace": trace}


def confusion(truth, pred, classes=config.CLASSES):
    """truth/pred: lists of class names. Returns accuracy, per-class P/R/F1, matrix."""
    idx = {c: i for i, c in enumerate(classes)}
    k = len(classes)
    m = [[0] * k for _ in range(k)]
    for t, p in zip(truth, pred):
        m[idx[t]][idx[p]] += 1
    n = len(truth)
    correct = sum(m[i][i] for i in range(k))
    per = {}
    f1s = []
    for c, i in idx.items():
        tp = m[i][i]
        fp = sum(m[r][i] for r in range(k)) - tp
        fn = sum(m[i]) - tp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[c] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                  "support": tp + fn}
        if tp + fn:
            f1s.append(f1)
    return {"accuracy": round(correct / n, 4) if n else 0.0,
            "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
            "per_class": per, "matrix": m, "classes": list(classes), "cells": n}
