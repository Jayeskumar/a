"""Change detection between flights, pest spread-rate estimation and early warning.

* NDVI difference map  d = NDVI_t2 - NDVI_t1, made relative by subtracting the field's median
  change (so normal crop growth or a brighter day does not look like stress).
* Decline hotspots: connected groups of cells whose relative drop is below -0.08.
* Front advance between two flights: for every newly infested cell, the distance to the nearest
  previously infested cell; the 90th percentile is how far the front moved.
* Spread trend: a radially spreading patch has area ~ r^2, so sqrt(area) grows linearly in
  time. OLS on sqrt(area) vs day gives the trend, today's growth in m^2/day and a projection of
  when the patch will reach ALERT_FIELD_SHARE of the crop.
"""
import math

from . import config, segment
from .classify import median
from .field import W, H


def ols(xs, ys):
    """Least squares y = a + b x. Returns (a, b, r2)."""
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two points")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("x values must differ")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


def ndvi_difference(ndvi_a, ndvi_b, crop_mask, threshold=config.CHANGE_DECLINE_THRESHOLD,
                    min_cells=config.CHANGE_MIN_HOTSPOT_CELLS):
    """Relative NDVI change from flight a to flight b with decline hotspots."""
    diff = [b - a for a, b in zip(ndvi_a, ndvi_b)]
    crop_d = [d for d, c in zip(diff, crop_mask) if c]
    shift = median(crop_d) if crop_d else 0.0
    rel = [d - shift for d in diff]
    declining = [c and r <= threshold for r, c in zip(rel, crop_mask)]
    hotspots = []
    for cells in segment.mask_components(declining, W, H, connectivity=8):
        if len(cells) < min_cells:
            continue
        x0, y0, x1, y1 = segment.bbox(cells, W)
        hotspots.append({
            "cells": len(cells), "area_m2": round(len(cells) * config.CELL_AREA_M2, 1),
            "mean_change": round(sum(rel[i] for i in cells) / len(cells), 4),
            "bbox": [x0, y0, x1, y1],
            "centroid": [round(sum(i % W for i in cells) / len(cells) + 0.5, 1),
                         round(sum(i // W for i in cells) / len(cells) + 0.5, 1)]})
    hotspots.sort(key=lambda h: -h["cells"])
    return {"diff": diff, "relative": rel, "field_shift": round(shift, 4),
            "declining_cells": sum(1 for d in declining if d), "hotspots": hotspots,
            "threshold": threshold}


def front_advance(prev_mask, cur_mask):
    """How far (m) the infested area's edge moved: p90 distance of new cells to old cells."""
    old = [i for i, v in enumerate(prev_mask) if v]
    new = [i for i, (a, b) in enumerate(zip(prev_mask, cur_mask)) if b and not a]
    if not old or not new:
        return None
    oldset = set(old)
    edge = [i for i in old if any(j not in oldset for j in segment.neighbours4(i, W, H))] or old
    ex = [((i % W) + 0.5, (i // W) + 0.5) for i in edge]
    dists = []
    for i in new:
        x, y = (i % W) + 0.5, (i // W) + 0.5
        best = min((x - a) ** 2 + (y - b) ** 2 for a, b in ex)
        dists.append(math.sqrt(best))
    dists.sort()
    p90 = dists[min(len(dists) - 1, int(0.9 * len(dists)))]
    return {"new_cells": len(new), "p90_m": round(p90, 2),
            "mean_m": round(sum(dists) / len(dists), 2)}


def spread(days, pest_masks, crop_cells, decline_rate=None):
    """Pest-patch trend over flights. days: list of flight days; pest_masks: bool lists.

    decline_rate: the steepest relative NDVI fall (per week) of a pest zone in the latest
    flight, if the zone rules flagged it as spreading - lets a brand-new patch raise the alarm
    before two flights of area history exist."""
    areas = [sum(1 for v in m if v) * config.CELL_AREA_M2 for m in pest_masks]
    series = [{"day": d, "area_m2": round(a, 1),
               "pct_crop": round(100.0 * a / (crop_cells * config.CELL_AREA_M2), 2)
               if crop_cells else 0.0} for d, a in zip(days, areas)]
    intervals = []
    for k in range(1, len(days)):
        fa = front_advance(pest_masks[k - 1], pest_masks[k])
        dd = days[k] - days[k - 1]
        if fa and dd > 0:
            intervals.append({"from_day": days[k - 1], "to_day": days[k],
                              "advance_m": fa["p90_m"], "speed_m_day": round(fa["p90_m"] / dd, 3),
                              "new_m2": fa["new_cells"] * config.CELL_AREA_M2})
    pts = [(d, math.sqrt(a)) for d, a in zip(days, areas) if a > 0]
    out = {"series": series, "intervals": intervals, "trend": None, "projection": None}
    if len(pts) >= 2:
        a, b, r2 = ols([p[0] for p in pts], [p[1] for p in pts])
        last_day, last_area = days[-1], areas[-1]
        growth = 2.0 * math.sqrt(last_area) * b if last_area > 0 else 0.0
        out["trend"] = {"sqrt_a": round(a, 4), "sqrt_b": round(b, 4), "r2": round(r2, 4),
                        "growth_m2_day": round(growth, 2),
                        "fit": [{"day": d, "area_m2": round(max(0.0, a + b * d) ** 2, 1)}
                                for d in days]}
        target = config.ALERT_FIELD_SHARE * crop_cells * config.CELL_AREA_M2
        if b > 0:
            t = (math.sqrt(target) - a) / b
            out["projection"] = {"target_m2": round(target, 1),
                                 "target_pct": round(100 * config.ALERT_FIELD_SHARE),
                                 "day": round(t, 1),
                                 "days_from_last": round(max(0.0, t - last_day), 1),
                                 "already_reached": last_area >= target,
                                 "curve": [{"day": d, "area_m2": round((a + b * d) ** 2, 1)}
                                           for d in range(int(days[0]), int(max(t, last_day)) + 8, 2)
                                           if a + b * d > 0]}
    speeds = [iv["speed_m_day"] for iv in intervals]
    out["front_speed_m_day"] = round(sum(speeds[-2:]) / len(speeds[-2:]), 3) if speeds else None
    out["decline_rate_week"] = decline_rate
    out["alert"] = alert(out, areas[-1] if areas else 0.0, decline_rate)
    return out


def alert(sp, last_area, decline_rate=None):
    speed = sp.get("front_speed_m_day")
    proj = sp.get("projection")
    trend = sp.get("trend")
    if last_area <= 0:
        return {"level": "green", "title": "No pest patch detected",
                "en": "No pest damage detected. Keep weekly flights.",
                "ta": "பூச்சித் தாக்குதல் இல்லை. வாரந்தோறும் ட்ரோன் கண்காணிப்பைத் தொடரவும்."}
    if speed is not None and speed >= config.ALERT_FRONT_SPEED_M_DAY:
        days = proj["days_from_last"] if proj else None
        en = ("Pest patch is spreading: front advancing ~%.1f m/day, +%.0f m²/day." %
              (speed, trend["growth_m2_day"] if trend else 0))
        ta = "பூச்சித் தாக்குதல் பரவுகிறது: நாளொன்றுக்கு சுமார் %.1f மீ முன்னேறுகிறது." % speed
        if proj and not proj["already_reached"]:
            en += " At this rate it covers %d%% of the crop in ~%.0f days. Spot-spray within 48 h." % (
                proj["target_pct"], days)
            ta += " இதே வேகத்தில் %.0f நாட்களில் பயிரின் %d%% பரவும். 48 மணி நேரத்திற்குள் தெளிக்கவும்." % (
                days, proj["target_pct"])
        else:
            en += " Spot-spray within 48 h."
            ta += " 48 மணி நேரத்திற்குள் தெளிக்கவும்."
        return {"level": "red", "title": "Early warning: active pest spread", "en": en, "ta": ta}
    if decline_rate is not None and decline_rate <= config.RULE_ACTIVE_DECLINE_WEEK:
        return {"level": "red", "title": "Early warning: new pest patch",
                "en": "New pest damage on %.0f m²: NDVI there is falling %.2f per week faster than "
                      "the rest of the field. Spot-spray within 48 h before it spreads."
                      % (last_area, -decline_rate),
                "ta": "%.0f ச.மீ பரப்பில் புதிய பூச்சித் தாக்குதல்: மற்ற வயலை விட வாரத்திற்கு %.2f "
                      "வேகமாக NDVI குறைகிறது. பரவும் முன் 48 மணி நேரத்திற்குள் தெளிக்கவும்."
                      % (last_area, -decline_rate)}
    return {"level": "amber", "title": "Pest damage present, not spreading fast",
            "en": "Pest damage on %.0f m², front stable. Spot-spray and re-fly in 7 days." % last_area,
            "ta": "%.0f ச.மீ பரப்பில் பூச்சித் தாக்குதல்; பரவல் நிலையானது. தெளித்து 7 நாளில் மீண்டும் "
                  "பறக்கவிடவும்." % last_area}
