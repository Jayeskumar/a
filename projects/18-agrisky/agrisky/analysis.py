"""Per-flight analytics: indices -> k-means zones -> smoothing -> components -> stress labels."""
import time

from . import classify, config, indices, kmeans, segment
from .field import W, H

STAT_KEYS = ("ndvi", "gndvi", "ndre", "savi", "ndwi", "green", "red", "rededge", "nir")


def features_for(flight, prev=None):
    feat = indices.compute_all(flight["bands"])
    for b in config.BANDS:
        feat[b] = flight["bands"][b]
    if prev is not None:
        pv = prev["features"]["ndvi"] if "features" in prev else \
            indices.compute_all(prev["bands"])["ndvi"]
        feat["dndvi"] = [a - b for a, b in zip(feat["ndvi"], pv)]
    return feat


def crop_mask(feat):
    """Cells that are obviously not crop are masked before clustering (standard practice for
    management-zone delineation): open water (NDWI > 0) and bare soil / bunds (NDVI < 0.35)."""
    ndvi, ndwi = feat["ndvi"], feat["ndwi"]
    out = []
    for i in range(len(ndvi)):
        if ndwi[i] > config.RULE_WATER_NDWI:
            out.append("water")
        elif ndvi[i] < config.RULE_SOIL_NDVI:
            out.append("soil")
        else:
            out.append("crop")
    return out


def _clip(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def cluster(feat, k=config.KMEANS_K, seed=0, step=config.KMEANS_SAMPLE_STEP):
    """k-means over crop cells. Returns labels for every cell: crop clusters 0..k-1 (ordered by
    NDVI), k = bare soil / bund mask, k+1 = open-water mask."""
    mask = crop_mask(feat)
    crop_idx = [i for i, m in enumerate(mask) if m == "crop"]
    if len(crop_idx) < k:
        raise ValueError("not enough crop cells to form %d zones" % k)
    cols = []
    for name in config.KMEANS_FEATURES:
        lo, hi = indices.INDEX_INFO[name]["range"]
        src = feat[name]
        cols.append([_clip(src[i], lo, hi) for i in crop_idx])
    rows, means, stds = kmeans.standardize(cols)
    pos = {i: p for p, i in enumerate(crop_idx)}
    sample = [rows[pos[y * W + x]] for y in range(0, H, step) for x in range(0, W, step)
              if (y * W + x) in pos]
    res = kmeans.kmeans(sample, k, seed=seed, n_init=config.KMEANS_N_INIT,
                        max_iter=config.KMEANS_MAX_ITER, tol=config.KMEANS_TOL)
    crop_labels, inertia = kmeans.assign(rows, res["centroids"])
    order = sorted(range(k), key=lambda j: res["centroids"][j][0])
    rank = {j: r for r, j in enumerate(order)}
    labels = [k if m == "soil" else k + 1 for m in mask]
    for p, i in enumerate(crop_idx):
        labels[i] = rank[crop_labels[p]]
    counts = [0] * (k + 2)
    for l in labels:
        counts[l] += 1
    cents = []
    for r, j in enumerate(order):
        z = res["centroids"][j]
        c = {name: round(z[d] * stds[d] + means[d], 4)
             for d, name in enumerate(config.KMEANS_FEATURES)}
        c["cells"] = counts[r]
        cents.append(c)
    return {"labels": labels, "centroids": cents, "iterations": res["iterations"],
            "converged": res["converged"], "history": [round(h, 2) for h in res["history"]],
            "inertia_all": round(inertia, 2), "sample_size": len(sample), "k": k,
            "crop_cells": len(crop_idx), "masked_soil": counts[k], "masked_water": counts[k + 1],
            "features": list(config.KMEANS_FEATURES)}


def zone_stats(comp, n_zone, feat, cluster_labels):
    cells_of = [[] for _ in range(n_zone)]
    for i, z in enumerate(comp):
        cells_of[z].append(i)
    total = len(comp)
    zones = []
    has_d = "dndvi" in feat
    for zid, cells in enumerate(cells_of):
        n = len(cells)
        st = {k: sum(feat[k][i] for i in cells) / n for k in STAT_KEYS}
        if has_d:
            st["dndvi"] = sum(feat["dndvi"][i] for i in cells) / n
        votes = {}
        for i in cells:
            votes[cluster_labels[i]] = votes.get(cluster_labels[i], 0) + 1
        x0, y0, x1, y1 = segment.bbox(cells, W)
        st.update({
            "id": zid, "cells": n, "area_m2": round(n * config.CELL_AREA_M2, 1),
            "pct_field": round(100.0 * n / total, 2),
            "cluster": max(votes.items(), key=lambda kv: kv[1])[0],
            "bbox": [x0, y0, x1, y1],
            "centroid": [round(sum(i % W for i in cells) / n + 0.5, 1),
                         round(sum(i // W for i in cells) / n + 0.5, 1)],
        })
        zones.append((st, cells))
    return zones


def _classify_all(comp, n, feat, smooth, ref, weeks):
    zones_raw = zone_stats(comp, n, feat, smooth)
    zones = []
    for st, cells in zones_raw:
        c = classify.classify_zone(st, ref, weeks)
        z = {key: (round(v, 4) if isinstance(v, float) else v) for key, v in st.items()}
        z.update(c)
        zones.append(z)
    return zones


def analyse_flight(flight, prev=None, k=config.KMEANS_K, seed=0):
    """Full analysis of one flight. `prev` is the previous analysed flight (or None)."""
    t0 = time.perf_counter()
    feat = features_for(flight, prev)
    t1 = time.perf_counter()
    cl = cluster(feat, k, seed=seed)
    t2 = time.perf_counter()
    smooth = segment.majority_smooth(cl["labels"], W, H, protected=(k, k + 1))
    comp, n = segment.connected_components(smooth, W, H)
    first = {}
    for i, c in enumerate(comp):
        first.setdefault(c, smooth[i])
    comp, n = segment.merge_small(comp, n, W, H,
                                  group=lambda c: "crop" if first[c] < k else first[c])
    raw_zones = n
    t3 = time.perf_counter()
    ref = classify.reference(feat)
    weeks = None
    if prev is not None:
        weeks = (flight["day"] - prev["day"]) / 7.0 or None
    zones = _classify_all(comp, n, feat, smooth, ref, weeks)
    for _ in range(3):        # management zones: merge touching zones that need the same action
        comp2, n2, _m = segment.merge_by_label(comp, n, [z["label"] for z in zones], W, H)
        if n2 == n:
            break
        comp, n = comp2, n2
        zones = _classify_all(comp, n, feat, smooth, ref, weeks)
    cell_class = [zones[c]["label"] for c in comp]
    t4 = time.perf_counter()
    truth = [config.CLASSES[t] for t in flight["truth"]]
    acc = classify.confusion(truth, cell_class)
    return {
        "day": flight["day"], "index": flight["index"],
        "features": feat, "kmeans": cl, "smoothed": smooth, "zones_grid": comp,
        "raw_zone_count": raw_zones,
        "zones": zones, "cell_class": cell_class, "reference": {
            kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in ref.items()},
        "accuracy": acc, "weeks_since_prev": weeks,
        "timing_ms": {"indices": round((t1 - t0) * 1000, 1), "kmeans": round((t2 - t1) * 1000, 1),
                      "segment": round((t3 - t2) * 1000, 1),
                      "classify": round((t4 - t3) * 1000, 1),
                      "total": round((t4 - t0) * 1000, 1)},
    }
