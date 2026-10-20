"""Deterministic synthetic data for the demo store.

    python -m stocksense.synth          # (re)writes data/*.csv and data/*.json

Daily demand per SKU = base x trend x day-of-week x annual cycle x festival x promotion,
with over-dispersed Poisson noise. Random stock-out episodes censor sales to zero (flagged).
Also generates POS bills (for market-basket analysis) and today's stock on hand.
Only random.Random(seed).random() is used, with our own Poisson / normal samplers, so the
output is identical on every Python version and OS.
"""
import csv
import io
import json
import math
import os
import random
from datetime import timedelta

from . import catalog, config, festivals


def _normal(rng):
    # Box-Muller using only rng.random()
    u1 = max(rng.random(), 1e-12)
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam < 30:  # Knuth's multiplication method
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, int(round(lam + math.sqrt(lam) * _normal(rng))))


def history_dates():
    return [config.HISTORY_START + timedelta(days=i) for i in range(config.HISTORY_DAYS)]


def _promo_days(rng, n):
    """3-5 promotion windows of 4-7 days, at least 21 days apart."""
    days = set()
    count = 3 + int(rng.random() * 3)
    tries = 0
    starts = []
    while len(starts) < count and tries < 200:
        tries += 1
        s = 20 + int(rng.random() * (n - 30))
        if all(abs(s - o) > 21 for o in starts):
            starts.append(s)
    for s in starts:
        length = 4 + int(rng.random() * 4)
        days.update(range(s, min(n, s + length)))
    return days


def generate_sales(items=None):
    """Rows of dict(date, sku, qty, stockout, promo) for every SKU and day."""
    items = items or catalog.build_catalog()
    dates = history_dates()
    n = len(dates)
    fest_rows = festivals.feature_rows(dates)
    rows = []
    for idx, it in enumerate(items):
        rng = random.Random(config.SEED * 1000 + idx)
        prof = catalog.DOW_PROFILES[it["profile"]]
        promo = _promo_days(rng, n) if it["promo"] else set()
        promo_lift = 1.4 + 0.5 * rng.random()
        so_left = 0
        for t, d in enumerate(dates):
            mu = it["base"] * (1.0 + it["growth"] * t / 365.0) * prof[d.weekday()]
            amp = it["annual"]["amp"]
            if amp:
                doy = d.timetuple().tm_yday
                mu *= 1.0 + amp * math.cos(2 * math.pi * (doy - it["annual"]["peak_doy"]) / 365.0)
            f = fest_rows[t]
            mu *= 1.0 + it["fest"]["diwali"] * f[0] + it["fest"]["pongal"] * f[1] + it["fest"]["other"] * f[2]
            is_promo = t in promo
            if is_promo:
                mu *= promo_lift
            lam = mu * math.exp(it["vol"] * _normal(rng) - 0.5 * it["vol"] ** 2)  # mean-preserving
            q = _poisson(rng, lam)
            stockout = 0
            if so_left == 0 and t > 7 and rng.random() < it["stockout_rate"]:
                so_left = 1 + int(rng.random() * 4)
                q = int(q * rng.random())  # ran out part-way through the first day
                stockout = 1
                so_left -= 1
            elif so_left > 0:
                q, stockout = 0, 1
                so_left -= 1
            rows.append({"date": d.isoformat(), "sku": it["sku"], "qty": q,
                         "stockout": stockout, "promo": 1 if is_promo else 0})
    return rows


# Shopping "missions": (weight, [(sku, inclusion probability), ...])
MISSIONS = [
    (0.14, [("TEA-250", 0.45), ("MILK-500", 0.70), ("SUGAR-1", 0.45), ("BISC-GLU", 0.60), ("RUSK-300", 0.20)]),
    (0.13, [("BREAD-400", 0.85), ("BUTTER-100", 0.40), ("EGG-6", 0.55), ("MILK-500", 0.45)]),
    (0.14, [("RICE-PON5", 0.50), ("DAL-TOOR1", 0.55), ("OIL-SUN1", 0.45), ("SALT-1", 0.20), ("RAVA-500", 0.20), ("ATTA-5", 0.20)]),
    (0.11, [("CHIPS-50", 0.70), ("COLA-750", 0.60), ("MIXT-200", 0.30), ("WATER-1L", 0.20)]),
    (0.07, [("NOOD-70", 0.85), ("EGG-6", 0.30), ("CHIPS-50", 0.15)]),
    (0.08, [("SOAP-100", 0.80), ("SHAMP-180", 0.35), ("PASTE-150", 0.40), ("HWASH-R", 0.10)]),
    (0.07, [("DETG-1", 0.75), ("DISH-BAR", 0.60), ("HWASH-R", 0.15)]),
    (0.07, [("AGAR-STK", 0.75), ("CAMPH-50", 0.60), ("LAMP-OIL", 0.30), ("SWEET-500", 0.10)]),
    (0.12, [("MILK-500", 0.90), ("CURD-400", 0.55), ("PANEER-200", 0.12)]),
    (0.04, [("COFF-200", 0.80), ("MILK-500", 0.70), ("SUGAR-1", 0.40)]),
    (0.03, [("JUICE-1L", 0.70), ("BISC-CRM", 0.50), ("WATER-1L", 0.30)]),
]


def generate_baskets(items=None):
    """List of dict(bill, date, items) - synthetic POS bills over the last BASKET_DAYS days."""
    items = items or catalog.build_catalog()
    rng = random.Random(config.SEED + 77)
    weights = [w for w, _ in MISSIONS]
    total_w = sum(weights)
    pop = [(it["sku"], it["base"]) for it in items]
    pop_total = sum(b for _, b in pop)
    end = config.HISTORY_START + timedelta(days=config.HISTORY_DAYS - 1)

    def pick_mission():
        r = rng.random() * total_w
        for w, m in MISSIONS:
            r -= w
            if r <= 0:
                return m
        return MISSIONS[-1][1]

    bills = []
    for b in range(config.N_BASKETS):
        r = rng.random()
        k = 1 if r < 0.65 else (2 if r < 0.93 else 3)
        basket = set()
        for _ in range(k):
            mission = pick_mission()
            chosen = [s for s, p in mission if rng.random() < p]
            if not chosen:
                chosen = [max(mission, key=lambda x: x[1])[0]]
            basket.update(chosen)
        if rng.random() < 0.25:  # impulse item, weighted by popularity
            r = rng.random() * pop_total
            for s, w in pop:
                r -= w
                if r <= 0:
                    basket.add(s)
                    break
        day = end - timedelta(days=int(rng.random() * config.BASKET_DAYS))
        bills.append({"bill": "B%05d" % (b + 1), "date": day.isoformat(), "items": sorted(basket)})
    bills.sort(key=lambda x: (x["date"], x["bill"]))
    return bills


def generate_inventory(sales_rows, items=None):
    """Stock on hand this morning: a deterministic mix of urgent, due, healthy and overstocked."""
    items = items or catalog.build_catalog()
    rng = random.Random(config.SEED + 99)
    recent = {}
    for r in sales_rows:
        recent.setdefault(r["sku"], []).append(r["qty"])
    covers = [0.4, 0.8, 1.5, 2.5, 4, 6, 9, 12, 16, 20, 28, 50]
    out = {}
    for it in items:
        q = recent[it["sku"]][-28:]
        mean28 = sum(q) / len(q)
        days = covers[int(rng.random() * len(covers))]
        if it["shelf_life"] <= config.PERISHABLE_DAYS:
            days = min(days, it["shelf_life"] * 0.8)
        out[it["sku"]] = {"on_hand": int(round(mean28 * days)), "on_order": 0}
    return out


def sales_csv_text(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["date", "sku", "qty", "stockout", "promo"], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def write_all(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    items = catalog.build_catalog()
    sales = generate_sales(items)
    with open(os.path.join(data_dir, "sales_history.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(sales_csv_text(sales))
    bills = generate_baskets(items)
    with open(os.path.join(data_dir, "baskets.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["bill", "date", "items"])
        for b in bills:
            w.writerow([b["bill"], b["date"], ";".join(b["items"])])
    with open(os.path.join(data_dir, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump([catalog.public_item(i) for i in items], f, indent=1)
    with open(os.path.join(data_dir, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(generate_inventory(sales, items), f, indent=1, sort_keys=True)
    return {"sales_rows": len(sales), "bills": len(bills), "skus": len(items)}


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(write_all(os.path.join(here, "data")))
