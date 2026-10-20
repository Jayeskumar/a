"""Demo SKU master for a neighbourhood kirana store in Tamil Nadu.

Prices are illustrative MRP-like rupee values (approx., not sourced from any retailer).
Generator-only fields (base demand, growth, volatility, festival uplifts, ...) shape the
synthetic history; the analytics never read them - they learn everything from sales.
"""

# Day-of-week demand profiles, Monday .. Sunday (assumption; normalised to mean 1 below).
DOW_PROFILES = {
    "staple": [0.92, 0.88, 0.90, 0.95, 1.02, 1.20, 1.13],
    "fresh": [1.00, 0.97, 0.96, 0.98, 1.00, 1.06, 1.03],
    "snack": [0.82, 0.80, 0.84, 0.90, 1.06, 1.33, 1.25],
    "care": [0.90, 0.88, 0.90, 0.94, 1.00, 1.22, 1.16],
    "pooja": [0.88, 0.95, 0.90, 0.95, 1.42, 0.97, 0.93],   # Friday pooja shopping
}
for _k, _v in DOW_PROFILES.items():
    _m = sum(_v) / 7.0
    DOW_PROFILES[_k] = [x / _m for x in _v]

# (sku, name, category, profile, price, cost, shelf_life_days, lead_time_days, lead_sd,
#  case_pack, base_units_per_day, yearly_growth, volatility, promo?, stockout_rate,
#  (diwali, pongal, other) peak uplift, (annual_amplitude, peak_day_of_year))
_RAW = [
    ("RICE-PON5", "Ponni Rice 5 kg", "Staples", "staple", 340, 300, 365, 3, 1.0, 5, 6.0, 0.06, 0.20, False, 0.004, (0.35, 0.5, 0.1), (0, 0)),
    ("ATTA-5", "Wheat Atta 5 kg", "Staples", "staple", 285, 250, 120, 3, 1.0, 4, 2.6, 0.10, 0.25, False, 0.004, (0.45, 0.1, 0.05), (0, 0)),
    ("DAL-TOOR1", "Toor Dal 1 kg", "Staples", "staple", 165, 142, 240, 3, 1.0, 10, 4.8, 0.03, 0.22, False, 0.004, (0.3, 0.4, 0.1), (0, 0)),
    ("SUGAR-1", "Sugar 1 kg", "Staples", "staple", 48, 42, 365, 2, 0.5, 10, 9.5, 0.02, 0.20, False, 0.005, (0.7, 0.9, 0.2), (0, 0)),
    ("SALT-1", "Iodised Salt 1 kg", "Staples", "staple", 28, 22, 540, 4, 1.0, 25, 3.8, 0.0, 0.25, False, 0.003, (0.05, 0.1, 0.0), (0, 0)),
    ("OIL-SUN1", "Sunflower Oil 1 L", "Staples", "staple", 155, 136, 270, 3, 1.0, 12, 7.2, 0.05, 0.20, False, 0.005, (0.9, 0.3, 0.15), (0, 0)),
    ("OIL-GN1", "Groundnut Oil 1 L", "Staples", "staple", 195, 168, 270, 4, 1.0, 12, 2.8, 0.12, 0.30, False, 0.004, (0.8, 0.3, 0.1), (0, 0)),
    ("GHEE-500", "Cow Ghee 500 ml", "Staples", "staple", 340, 295, 180, 4, 1.5, 6, 1.4, 0.08, 0.35, False, 0.004, (2.2, 0.8, 0.3), (0, 0)),
    ("JAGG-1", "Jaggery 1 kg", "Staples", "staple", 72, 56, 180, 3, 1.0, 10, 1.3, 0.0, 0.35, False, 0.004, (0.4, 3.5, 0.6), (0, 0)),
    ("RAVA-500", "Bombay Rava 500 g", "Staples", "staple", 38, 31, 120, 3, 1.0, 10, 2.4, 0.0, 0.30, False, 0.003, (0.5, 0.4, 0.1), (0, 0)),
    ("MILK-500", "Toned Milk 500 ml", "Dairy & Bakery", "fresh", 27, 24.5, 2, 1, 0.0, 6, 62.0, 0.04, 0.10, False, 0.008, (0.25, 0.35, 0.1), (0, 0)),
    ("CURD-400", "Curd 400 g", "Dairy & Bakery", "fresh", 35, 29, 5, 1, 0.0, 6, 17.0, 0.06, 0.18, False, 0.006, (0.1, 0.2, 0.1), (0.15, 130)),
    ("PANEER-200", "Paneer 200 g", "Dairy & Bakery", "fresh", 95, 78, 7, 1, 0.0, 5, 3.5, 0.15, 0.30, False, 0.005, (0.8, 0.2, 0.3), (0, 0)),
    ("BUTTER-100", "Butter 100 g", "Dairy & Bakery", "fresh", 60, 53, 90, 2, 0.5, 10, 2.8, 0.0, 0.30, False, 0.004, (0.4, 0.1, 0.4), (0, 0)),
    ("BREAD-400", "Sandwich Bread 400 g", "Dairy & Bakery", "fresh", 45, 37, 4, 1, 0.0, 5, 19.0, 0.03, 0.15, False, 0.010, (0.05, 0.0, 0.2), (0, 0)),
    ("EGG-6", "Eggs (pack of 6)", "Dairy & Bakery", "fresh", 45, 38, 14, 2, 0.5, 5, 11.0, 0.0, 0.20, False, 0.005, (0.0, 0.0, 0.2), (0, 0)),
    ("BISC-GLU", "Glucose Biscuits 100 g", "Snacks & Beverages", "snack", 10, 8.4, 180, 3, 1.0, 48, 42.0, 0.02, 0.18, True, 0.004, (0.2, 0.2, 0.1), (0, 0)),
    ("BISC-CRM", "Cream Biscuits 150 g", "Snacks & Beverages", "snack", 30, 24.5, 180, 3, 1.0, 24, 11.0, 0.10, 0.25, True, 0.004, (0.3, 0.2, 0.2), (0, 0)),
    ("RUSK-300", "Milk Rusk 300 g", "Snacks & Beverages", "snack", 55, 45, 150, 3, 1.0, 12, 3.6, 0.0, 0.30, False, 0.003, (0.2, 0.2, 0.1), (0, 0)),
    ("NOOD-70", "Instant Noodles 70 g", "Snacks & Beverages", "snack", 15, 12.6, 270, 3, 1.0, 48, 24.0, 0.12, 0.22, True, 0.005, (0.1, 0.1, 0.2), (0, 0)),
    ("CHIPS-50", "Potato Chips 50 g", "Snacks & Beverages", "snack", 20, 15.5, 120, 2, 0.5, 30, 21.0, 0.08, 0.25, True, 0.006, (0.3, 0.2, 0.4), (0.10, 130)),
    ("MIXT-200", "Namkeen Mixture 200 g", "Snacks & Beverages", "snack", 55, 43, 90, 2, 0.5, 12, 5.5, 0.0, 0.30, False, 0.004, (1.6, 0.6, 0.4), (0, 0)),
    ("SWEET-500", "Assorted Sweets 500 g", "Snacks & Beverages", "snack", 260, 195, 10, 2, 0.5, 4, 1.2, 0.05, 0.45, False, 0.003, (5.5, 1.2, 1.0), (0, 0)),
    ("DRYF-250", "Dry Fruit Gift Pack 250 g", "Snacks & Beverages", "snack", 330, 255, 180, 5, 1.5, 6, 0.45, 0.0, 0.50, False, 0.002, (7.0, 0.5, 0.8), (0, 0)),
    ("TEA-250", "Tea Powder 250 g", "Snacks & Beverages", "staple", 145, 121, 365, 3, 1.0, 12, 6.2, 0.0, 0.20, True, 0.004, (0.3, 0.3, 0.1), (0, 0)),
    ("COFF-200", "Filter Coffee 200 g", "Snacks & Beverages", "staple", 165, 136, 180, 3, 1.0, 12, 4.2, 0.06, 0.20, False, 0.004, (0.4, 0.5, 0.1), (0, 0)),
    ("COLA-750", "Cold Drink 750 ml", "Snacks & Beverages", "snack", 45, 35, 180, 2, 0.5, 24, 13.0, 0.10, 0.25, True, 0.006, (0.5, 0.3, 0.6), (0.35, 130)),
    ("JUICE-1L", "Mango Drink 1 L", "Snacks & Beverages", "snack", 99, 79, 180, 3, 1.0, 12, 3.0, 0.0, 0.30, True, 0.004, (0.4, 0.2, 0.3), (0.40, 130)),
    ("WATER-1L", "Packaged Water 1 L", "Snacks & Beverages", "snack", 20, 13, 180, 2, 0.5, 12, 17.0, 0.05, 0.20, False, 0.005, (0.1, 0.1, 0.2), (0.45, 130)),
    ("SOAP-100", "Bath Soap 100 g", "Personal & Home Care", "care", 40, 32, 730, 4, 1.0, 36, 9.5, 0.0, 0.20, True, 0.003, (0.3, 0.3, 0.1), (0, 0)),
    ("SHAMP-180", "Shampoo 180 ml", "Personal & Home Care", "care", 155, 124, 730, 5, 1.5, 12, 2.3, 0.05, 0.30, True, 0.003, (0.3, 0.2, 0.1), (0, 0)),
    ("PASTE-150", "Toothpaste 150 g", "Personal & Home Care", "care", 99, 80, 540, 4, 1.0, 24, 4.1, 0.0, 0.25, True, 0.003, (0.1, 0.1, 0.05), (0, 0)),
    ("DETG-1", "Detergent Powder 1 kg", "Personal & Home Care", "care", 125, 101, 540, 4, 1.0, 12, 3.9, 0.03, 0.25, True, 0.003, (0.5, 0.4, 0.1), (0, 0)),
    ("DISH-BAR", "Dishwash Bar 200 g", "Personal & Home Care", "care", 22, 17, 540, 4, 1.0, 40, 6.8, 0.0, 0.20, False, 0.003, (0.4, 0.3, 0.1), (0, 0)),
    ("HWASH-R", "Hand Wash Refill 750 ml", "Personal & Home Care", "care", 105, 84, 540, 5, 1.5, 12, 1.1, 0.20, 0.45, True, 0.002, (0.1, 0.1, 0.1), (0, 0)),
    ("MOSQ-COIL", "Mosquito Coil (10)", "Personal & Home Care", "care", 45, 36, 730, 4, 1.0, 24, 3.0, 0.0, 0.35, False, 0.003, (0.1, 0.1, 0.1), (0.40, 320)),
    ("AGAR-STK", "Agarbatti 100 sticks", "Pooja", "pooja", 45, 33, 730, 4, 1.0, 24, 4.0, 0.0, 0.25, False, 0.003, (1.2, 1.0, 1.2), (0, 0)),
    ("CAMPH-50", "Camphor 50 g", "Pooja", "pooja", 35, 25, 730, 4, 1.0, 24, 2.2, 0.0, 0.30, False, 0.003, (1.4, 1.5, 1.4), (0, 0)),
    ("LAMP-OIL", "Lamp (Pooja) Oil 1 L", "Pooja", "pooja", 135, 108, 365, 4, 1.0, 12, 1.0, 0.0, 0.40, False, 0.003, (3.0, 0.8, 1.0), (0, 0)),
    ("BATT-AA", "AA Batteries (2)", "Personal & Home Care", "care", 40, 29, 1095, 6, 2.0, 12, 0.7, 0.0, 0.55, False, 0.002, (0.5, 0.1, 0.2), (0, 0)),
]

# Generator-only keys (not exposed as item master data).
GEN_KEYS = ("profile", "base", "growth", "vol", "promo", "stockout_rate", "fest", "annual")


def build_catalog():
    """Ordered list of item dicts (public fields + generator fields)."""
    items = []
    for r in _RAW:
        items.append({
            "sku": r[0], "name": r[1], "category": r[2], "profile": r[3],
            "price": float(r[4]), "cost": float(r[5]), "shelf_life": int(r[6]),
            "lead_time": int(r[7]), "lead_sd": float(r[8]), "pack": int(r[9]),
            "base": float(r[10]), "growth": float(r[11]), "vol": float(r[12]),
            "promo": bool(r[13]), "stockout_rate": float(r[14]),
            "fest": {"diwali": r[15][0], "pongal": r[15][1], "other": r[15][2]},
            "annual": {"amp": r[16][0], "peak_doy": r[16][1]},
        })
    return items


def public_item(item):
    """Item master fields the analytics may use."""
    return {k: v for k, v in item.items() if k not in GEN_KEYS}
