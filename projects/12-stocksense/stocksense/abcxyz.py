"""ABC-XYZ classification: revenue Pareto (ABC) x demand variability (XYZ)."""
from . import config
from .stats import mean, std

STRATEGY = {
    "AX": ("Automate", "High value, steady demand: automatic reorders, lean safety stock, frequent small orders.", 0.98),
    "AY": ("Forecast closely", "High value, seasonal/trending: forecast-driven orders, review weekly, pre-build for festivals.", 0.97),
    "AZ": ("Watch daily", "High value, erratic: keep a buffer, confirm supplier lead times, check stock daily.", 0.95),
    "BX": ("Auto-reorder", "Mid value, steady: standard reorder point at ~95% service, monthly review.", 0.95),
    "BY": ("Standard ROP", "Mid value, variable: reorder point with safety stock, review fortnightly.", 0.94),
    "BZ": ("Order on signal", "Mid value, erratic: smaller orders, rely on festival/promo signals.", 0.90),
    "CX": ("Bulk & forget", "Low value, steady: big infrequent orders (large EOQ), minimal effort.", 0.92),
    "CY": ("Periodic review", "Low value, variable: order on a fixed weekly cycle, modest buffer.", 0.90),
    "CZ": ("Rationalise", "Low value, erratic: stock minimally, order to request or consider delisting.", 0.85),
}


def classify_abc(revenue):
    """revenue: dict sku -> value. Returns (dict sku -> 'A'|'B'|'C', pareto rows)."""
    total = sum(revenue.values()) or 1.0
    order = sorted(revenue, key=lambda s: (-revenue[s], s))
    out, rows, cum = {}, [], 0.0
    for s in order:
        before = cum / total
        cls = "A" if before < config.ABC_A else ("B" if before < config.ABC_B else "C")
        cum += revenue[s]
        out[s] = cls
        rows.append({"sku": s, "revenue": round(revenue[s], 2), "share": round(revenue[s] / total, 4),
                     "cum_share": round(cum / total, 4), "abc": cls})
    return out, rows


def cv(values):
    m = mean(values)
    return std(values) / m if m > 0 else float("inf")


def classify_xyz(weekly):
    """weekly: dict sku -> list of weekly demand. Returns (dict sku -> class, dict sku -> CV)."""
    out, cvs = {}, {}
    for s, w in weekly.items():
        c = cv(w)
        cvs[s] = c
        out[s] = "X" if c < config.XYZ_X else ("Y" if c < config.XYZ_Y else "Z")
    return out, cvs


def matrix(revenue, weekly, names=None):
    abc, pareto = classify_abc(revenue)
    xyz, cvs = classify_xyz(weekly)
    total = sum(revenue.values()) or 1.0
    cells = []
    for a in "ABC":
        for x in "XYZ":
            key = a + x
            skus = [s for s in pareto_order(pareto) if abc[s] == a and xyz[s] == x]
            title, text, sl = STRATEGY[key]
            cells.append({
                "cell": key, "abc": a, "xyz": x, "count": len(skus),
                "revenue_share": round(sum(revenue[s] for s in skus) / total, 4),
                "skus": [{"sku": s, "name": (names or {}).get(s, s), "cv": round(cvs[s], 3)} for s in skus],
                "strategy": title, "advice": text, "service_level": sl,
            })
    per_sku = {s: {"abc": abc[s], "xyz": xyz[s], "class": abc[s] + xyz[s], "cv": round(cvs[s], 3),
                   "strategy": STRATEGY[abc[s] + xyz[s]][0], "advice": STRATEGY[abc[s] + xyz[s]][1],
                   "recommended_service": STRATEGY[abc[s] + xyz[s]][2]} for s in revenue}
    return {"cells": cells, "pareto": pareto, "per_sku": per_sku,
            "thresholds": {"A": config.ABC_A, "B": config.ABC_B, "X": config.XYZ_X, "Y": config.XYZ_Y}}


def pareto_order(pareto):
    return [r["sku"] for r in pareto]
