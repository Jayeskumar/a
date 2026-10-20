"""All tunable assumptions for KrishiMitra live here, in one place.

EVERY agronomic number below is APPROXIMATE and ILLUSTRATIVE. They are chosen to be in a
plausible range for Tamil Nadu conditions so the demo behaves sensibly, but they are not a
substitute for a Soil Health Card, TNAU crop production guide or the local KVK / agriculture
officer. Where a figure comes from a well-known reference the comment says so; everything
else is a rounded, hand-picked assumption.
"""

# --------------------------------------------------------------------------------------
# Feature order used by the ML models
# --------------------------------------------------------------------------------------
FEATURES = ["N", "P", "K", "ph", "temperature", "humidity", "rainfall"]
FEATURE_UNITS = {
    "N": "kg/ha", "P": "kg/ha", "K": "kg/ha", "ph": "",
    "temperature": "°C", "humidity": "%", "rainfall": "mm",
}
# Hard validation limits for user input (physically sensible bounds, not agronomic advice).
FEATURE_LIMITS = {
    "N": (0, 400), "P": (0, 300), "K": (0, 600), "ph": (3.5, 10.0),
    "temperature": (5, 48), "humidity": (5, 100), "rainfall": (0, 4000),
}

# --------------------------------------------------------------------------------------
# Crops. Names in English + Tamil script.
# --------------------------------------------------------------------------------------
CROPS = [
    "rice", "sugarcane", "banana", "cotton", "maize", "groundnut", "blackgram",
    "greengram", "turmeric", "coconut", "ragi", "tomato", "chilli", "pearlmillet",
]
CROP_NAMES = {
    "rice":        {"en": "Rice (Paddy)",          "ta": "நெல்"},
    "sugarcane":   {"en": "Sugarcane",             "ta": "கரும்பு"},
    "banana":      {"en": "Banana",                "ta": "வாழை"},
    "cotton":      {"en": "Cotton",                "ta": "பருத்தி"},
    "maize":       {"en": "Maize",                 "ta": "மக்காச்சோளம்"},
    "groundnut":   {"en": "Groundnut",             "ta": "நிலக்கடலை"},
    "blackgram":   {"en": "Black gram (Urad)",     "ta": "உளுந்து"},
    "greengram":   {"en": "Green gram (Moong)",    "ta": "பாசிப்பயறு"},
    "turmeric":    {"en": "Turmeric",              "ta": "மஞ்சள்"},
    "coconut":     {"en": "Coconut",               "ta": "தென்னை"},
    "ragi":        {"en": "Ragi (Finger millet)",  "ta": "கேழ்வரகு (ராகி)"},
    "tomato":      {"en": "Tomato",                "ta": "தக்காளி"},
    "chilli":      {"en": "Chilli",                "ta": "மிளகாய்"},
    "pearlmillet": {"en": "Pearl millet (Cumbu)",  "ta": "கம்பு"},
}

# Approximate "typical growing condition" ranges per crop, used ONLY to generate the
# deterministic synthetic training set (uniform sampling inside each range + small noise).
# Order: N, P, K (soil available, kg/ha), pH, temperature (°C, season mean),
#        humidity (%, season mean), rainfall (mm over the season / year incl. assured supply).
# Hand-picked, illustrative ranges – in the spirit of public crop-recommendation datasets.
CROP_RANGES = {
    "rice":        [(60, 100), (30, 55), (30, 50), (5.5, 7.0), (22, 32), (75, 90), (1000, 1800)],
    "sugarcane":   [(90, 140), (40, 70), (80, 130), (6.0, 7.8), (24, 34), (65, 85), (1200, 2000)],
    "banana":      [(90, 130), (60, 90), (150, 220), (6.0, 7.5), (25, 32), (75, 90), (1000, 1800)],
    "cotton":      [(100, 140), (35, 60), (40, 70), (6.0, 8.0), (24, 34), (55, 75), (500, 900)],
    "maize":       [(70, 110), (40, 65), (30, 55), (5.5, 7.5), (20, 30), (55, 75), (500, 900)],
    "groundnut":   [(15, 40), (40, 70), (25, 50), (6.0, 7.5), (25, 33), (50, 70), (450, 750)],
    "blackgram":   [(15, 40), (50, 80), (15, 35), (6.5, 7.8), (26, 34), (60, 80), (600, 900)],
    "greengram":   [(15, 40), (35, 60), (15, 35), (6.2, 7.2), (27, 35), (75, 90), (450, 700)],
    "turmeric":    [(40, 80), (50, 80), (90, 140), (5.0, 7.0), (20, 30), (70, 90), (1500, 2200)],
    "coconut":     [(10, 40), (10, 30), (30, 60), (5.2, 7.5), (25, 32), (85, 98), (1300, 2300)],
    "ragi":        [(30, 60), (20, 40), (20, 40), (5.0, 7.0), (18, 28), (50, 70), (500, 900)],
    "tomato":      [(80, 120), (60, 100), (50, 90), (6.0, 7.0), (18, 27), (60, 80), (400, 700)],
    "chilli":      [(90, 130), (40, 70), (40, 70), (6.0, 7.5), (22, 30), (55, 70), (600, 1000)],
    "pearlmillet": [(20, 50), (15, 35), (15, 35), (6.5, 8.2), (28, 36), (40, 60), (250, 600)],
}

DATASET_SEED = 42
SAMPLES_PER_CROP = 120          # 14 crops x 120 = 1680 rows
NOISE_FRACTION = 0.06           # gaussian jitter = 6% of each range width (makes classes overlap)
TEST_FRACTION = 0.25            # stratified hold-out split
RF_PARAMS = {"n_trees": 30, "max_depth": 10, "min_samples_split": 4, "max_features": 3, "seed": 7}

# --------------------------------------------------------------------------------------
# Fertiliser advisor
# --------------------------------------------------------------------------------------
# Approx. blanket recommended dose (kg/ha of N, P2O5, K2O) per crop, rounded from commonly
# cited TNAU-style recommendations (irrigated crop). Illustrative only.
CROP_NPK_REQUIREMENT = {
    "rice": (150, 50, 50),
    "sugarcane": (275, 63, 113),
    "banana": (330, 105, 990),      # ~110:35:330 g per plant x ~3000 plants/ha (approx.)
    "cotton": (80, 40, 40),
    "maize": (250, 75, 75),         # irrigated hybrid maize (approx.)
    "groundnut": (17, 34, 54),
    "blackgram": (25, 50, 25),
    "greengram": (25, 50, 25),
    "turmeric": (125, 60, 108),
    "coconut": (98, 56, 210),       # ~560:320:1200 g per palm/yr x 175 palms/ha (approx.)
    "ragi": (60, 30, 30),
    "tomato": (150, 100, 100),
    "chilli": (120, 80, 80),
    "pearlmillet": (80, 40, 40),
}
# Fraction of the soil-test "available" nutrient credited against the dose. Inspired by the
# STCR targeted-yield form  F = a*T - b*S  (b = soil vs fertiliser efficiency ratio, commonly
# 0.3-0.7). We take a*T = blanket dose and use these rounded b values (assumption).
SOIL_CREDIT = {"N": 0.40, "P": 0.30, "K": 0.30}
# Soil P and K test values are treated as P2O5 / K2O equivalents (simplification).

UREA_N = 0.46                   # urea is 46% N
DAP_N, DAP_P2O5 = 0.18, 0.46    # DAP is 18-46-0
MOP_K2O = 0.60                  # muriate of potash is 60% K2O
HA_PER_ACRE = 0.404686          # 1 acre = 0.404686 ha
BAG_KG = {"urea": 45, "dap": 50, "mop": 50}   # common Indian retail bag sizes

# Organic sources: approx. nutrient content (% N, % P2O5, % K2O); values vary a lot by source.
ORGANIC_SOURCES = {
    "fym":           (0.5, 0.2, 0.5),    # farmyard manure (approx.)
    "vermicompost":  (1.5, 0.8, 0.8),    # (approx.)
    "neemcake":      (5.0, 1.0, 1.5),    # (approx.)
}
ORGANIC_SUBSTITUTION = 0.25     # show how much organic source replaces 25% of the N deficit
LEGUMES = {"groundnut", "blackgram", "greengram"}

# --------------------------------------------------------------------------------------
# Irrigation (FAO-56)
# --------------------------------------------------------------------------------------
GSC = 0.0820                    # solar constant, MJ m-2 min-1 (FAO-56 eq. 21)
MJ_TO_MM = 0.408                # MJ m-2 day-1 -> mm/day equivalent evaporation (FAO-56)
HARGREAVES_COEFF = 0.0023       # Hargreaves & Samani (1985), FAO-56 eq. 52
LITRES_PER_MM_PER_ACRE = 4046.86  # 1 mm of water over 1 acre (4046.86 m2) = 4046.86 litres

# Crop coefficients (Kc ini, Kc mid, Kc end) - FAO-56 Table 12 typical values or the nearest
# analogue crop (approx.). Stage lengths (initial, development, mid, late) in days - rounded,
# roughly typical Tamil Nadu durations (approx.).
KC = {
    "rice": (1.05, 1.20, 0.75),
    "sugarcane": (0.40, 1.25, 0.75),
    "banana": (0.50, 1.10, 1.00),
    "cotton": (0.35, 1.15, 0.60),
    "maize": (0.30, 1.20, 0.50),
    "groundnut": (0.40, 1.15, 0.60),
    "blackgram": (0.40, 1.05, 0.35),   # analogue: dry beans
    "greengram": (0.40, 1.05, 0.35),   # analogue: dry beans
    "turmeric": (0.50, 1.05, 0.75),    # no FAO entry - analogue estimate
    "coconut": (0.95, 1.00, 1.00),
    "ragi": (0.30, 1.00, 0.30),        # analogue: millet
    "tomato": (0.60, 1.15, 0.80),
    "chilli": (0.60, 1.05, 0.90),      # analogue: peppers
    "pearlmillet": (0.30, 1.00, 0.30),
}
STAGE_DAYS = {
    "rice": (25, 30, 45, 25),
    "sugarcane": (45, 75, 180, 60),
    "banana": (120, 90, 120, 60),
    "cotton": (25, 45, 55, 40),
    "maize": (20, 30, 40, 20),
    "groundnut": (25, 30, 35, 20),
    "blackgram": (15, 20, 25, 10),
    "greengram": (15, 20, 20, 10),
    "turmeric": (60, 60, 90, 60),
    "coconut": (60, 90, 150, 65),      # one annual cycle of an established palm
    "ragi": (20, 30, 35, 20),
    "tomato": (25, 35, 45, 30),
    "chilli": (30, 40, 60, 30),
    "pearlmillet": (15, 25, 30, 20),
}
TRANSPLANTED = {"rice", "tomato", "chilli", "ragi"}   # nursery + transplanting (simplified)
PERENNIAL = {"coconut"}

# Effective rainfall (fixed-percentage method): rain below the threshold is assumed lost to
# interception/evaporation; above it, this fraction is assumed useful (assumption, approx.).
EFF_RAIN_THRESHOLD_MM = 5.0
EFF_RAIN_FRACTION = 0.8
PADDY_PERCOLATION_MM = 4.0      # extra daily seepage+percolation for puddled rice (approx.)

# Irrigate when the root-zone deficit reaches this depth (mm, approx. readily available water).
SOIL_TYPES = {
    "sandy":    {"refill_mm": 20, "en": "Sandy", "ta": "மணல் மண்"},
    "red":      {"refill_mm": 30, "en": "Red loam", "ta": "செம்மண்"},
    "alluvial": {"refill_mm": 35, "en": "Alluvial", "ta": "வண்டல் மண்"},
    "black":    {"refill_mm": 45, "en": "Black (clay)", "ta": "கரிசல் மண்"},
}
PADDY_REFILL_MM = 50            # rice: refill ~5 cm ponding when it has disappeared (approx.)
# Application efficiency by method (approx., commonly quoted ranges' midpoints).
IRRIGATION_METHODS = {
    "flood":     {"eff": 0.60, "en": "Flood / basin", "ta": "வாய்க்கால் (பாத்தி) பாசனம்"},
    "furrow":    {"eff": 0.70, "en": "Furrow", "ta": "சால் பாசனம்"},
    "sprinkler": {"eff": 0.75, "en": "Sprinkler", "ta": "தெளிப்பு நீர்ப் பாசனம்"},
    "drip":      {"eff": 0.90, "en": "Drip", "ta": "சொட்டு நீர்ப் பாசனம்"},
}

# Approx. monthly climate normals for interior Tamil Nadu (Tmax, Tmin °C, rain mm/month).
# Rounded, illustrative – used only to synthesise a 7-day forecast when none is supplied.
CLIMATE_NORMALS = [
    (30, 19, 10), (33, 20, 10), (35, 22, 15), (37, 25, 50), (37, 25, 80), (34, 24, 40),
    (33, 24, 50), (33, 23, 80), (33, 23, 120), (31, 22, 170), (29, 21, 130), (29, 20, 50),
]

# --------------------------------------------------------------------------------------
# Market timing (SYNTHETIC prices - not real mandi data)
# --------------------------------------------------------------------------------------
# base: synthetic base price, unit; amp: seasonal amplitude; high_month: month with the
# seasonal peak (prices usually dip at harvest glut); noise: weekly log-noise sd;
# hold_cost: storage+quality loss per week (fraction); max_hold: weeks storable.
MARKET = {
    "rice":        {"base": 2300,  "unit": "₹/quintal", "amp": 0.06, "high_month": 9,  "noise": 0.025, "hold_cost": 0.004, "max_hold": 12},
    "sugarcane":   {"base": 350,   "unit": "₹/quintal", "amp": 0.02, "high_month": 3,  "noise": 0.010, "hold_cost": 0.050, "max_hold": 0},
    "banana":      {"base": 2000,  "unit": "₹/quintal", "amp": 0.15, "high_month": 8,  "noise": 0.060, "hold_cost": 0.060, "max_hold": 1},
    "cotton":      {"base": 7000,  "unit": "₹/quintal", "amp": 0.08, "high_month": 7,  "noise": 0.030, "hold_cost": 0.004, "max_hold": 12},
    "maize":       {"base": 2200,  "unit": "₹/quintal", "amp": 0.08, "high_month": 8,  "noise": 0.030, "hold_cost": 0.005, "max_hold": 12},
    "groundnut":   {"base": 6500,  "unit": "₹/quintal", "amp": 0.08, "high_month": 6,  "noise": 0.030, "hold_cost": 0.005, "max_hold": 10},
    "blackgram":   {"base": 8000,  "unit": "₹/quintal", "amp": 0.07, "high_month": 11, "noise": 0.025, "hold_cost": 0.004, "max_hold": 12},
    "greengram":   {"base": 8000,  "unit": "₹/quintal", "amp": 0.07, "high_month": 11, "noise": 0.025, "hold_cost": 0.004, "max_hold": 12},
    "turmeric":    {"base": 12000, "unit": "₹/quintal", "amp": 0.10, "high_month": 10, "noise": 0.035, "hold_cost": 0.003, "max_hold": 12},
    "coconut":     {"base": 1800,  "unit": "₹/100 nuts", "amp": 0.10, "high_month": 1, "noise": 0.030, "hold_cost": 0.015, "max_hold": 4},
    "ragi":        {"base": 3800,  "unit": "₹/quintal", "amp": 0.06, "high_month": 8,  "noise": 0.020, "hold_cost": 0.004, "max_hold": 12},
    "tomato":      {"base": 1800,  "unit": "₹/quintal", "amp": 0.35, "high_month": 7,  "noise": 0.100, "hold_cost": 0.080, "max_hold": 1},
    "chilli":      {"base": 15000, "unit": "₹/quintal", "amp": 0.12, "high_month": 10, "noise": 0.035, "hold_cost": 0.004, "max_hold": 12},
    "pearlmillet": {"base": 2500,  "unit": "₹/quintal", "amp": 0.07, "high_month": 6,  "noise": 0.025, "hold_cost": 0.004, "max_hold": 12},
}
MARKET_SEED = 2026
MARKET_EPOCH = "2022-01-03"     # first Monday of the synthetic weekly series
MARKET_TREND_PER_YEAR = 0.04    # synthetic 4%/yr drift (assumption)
MARKET_MIN_GAIN = 0.02          # suggest holding only if expected net gain >= 2%
MARKET_BAND_Z = 1.28            # ~80% band under a normal approximation

# --------------------------------------------------------------------------------------
# Demo farms (inputs are illustrative, not real soil-test results). Sowing date is given
# relative to today so the demo shows a growing crop whenever it is run.
# --------------------------------------------------------------------------------------
PRESETS = [
    {
        "id": "namakkal", "name": {"en": "Tiruchengode, Namakkal - red soil, drip",
                                   "ta": "திருச்செங்கோடு, நாமக்கல் - செம்மண், சொட்டு நீர்"},
        "inputs": {"N": 28, "P": 55, "K": 38, "ph": 6.9, "temperature": 29, "humidity": 62,
                   "rainfall": 620},
        "lat": 11.38, "soil": "red", "method": "drip", "area_acres": 2.0,
        "sowing_days_ago": 15,
    },
    {
        "id": "delta", "name": {"en": "Thanjavur delta - paddy, canal flood",
                                "ta": "தஞ்சாவூர் டெல்டா - நெல், கால்வாய் பாசனம்"},
        "inputs": {"N": 82, "P": 42, "K": 40, "ph": 6.4, "temperature": 28, "humidity": 82,
                   "rainfall": 1350},
        "lat": 10.79, "soil": "alluvial", "method": "flood", "area_acres": 3.0,
        "sowing_days_ago": 35, "rain_factor": 1.4,
    },
    {
        "id": "erode", "name": {"en": "Erode - turmeric belt, sprinkler",
                                "ta": "ஈரோடு - மஞ்சள் பகுதி, தெளிப்பு நீர்"},
        "inputs": {"N": 62, "P": 66, "K": 112, "ph": 6.2, "temperature": 26, "humidity": 80,
                   "rainfall": 1750},
        "lat": 11.34, "soil": "red", "method": "sprinkler", "area_acres": 1.5,
        "sowing_days_ago": 130,
    },
    {
        "id": "dharmapuri", "name": {"en": "Dharmapuri - rainfed upland",
                                     "ta": "தர்மபுரி - மானாவாரி மேட்டுநிலம்"},
        "inputs": {"N": 44, "P": 30, "K": 29, "ph": 6.1, "temperature": 24, "humidity": 60,
                   "rainfall": 700},
        "lat": 12.13, "soil": "sandy", "method": "furrow", "area_acres": 1.0,
        "sowing_days_ago": 60,
    },
]
