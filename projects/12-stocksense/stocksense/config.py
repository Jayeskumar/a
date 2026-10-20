"""Every tunable assumption of StockSense lives here, with the reasoning behind it.

Numbers marked "assumption" are modelling choices, not measured facts. Change them here
and every module (forecasting, inventory policy, simulation, UI) picks them up.
"""
from datetime import date

PRODUCT = "StockSense"
TAGLINE = "Demand forecasting and smart reordering for neighbourhood stores"

# ---------------------------------------------------------------- synthetic data
SEED = 2026                       # fixed seed -> identical demo data on every machine
HISTORY_START = date(2025, 9, 15)  # ~13 months of daily sales, so last year's Diwali is in history
HISTORY_DAYS = 400                 # 2025-09-15 .. 2026-10-19 inclusive
N_BASKETS = 3000                   # synthetic POS bills used for market-basket analysis
BASKET_DAYS = 56                   # bills are spread over the last 8 weeks

# Festival dates are approximate (they follow lunar / solar calendars and vary by region).
# Each entry: (display name, effect group, approx. date). Effect groups share a learned uplift.
FESTIVALS = [
    ("Diwali", "diwali", date(2025, 10, 20)),
    ("Christmas", "other", date(2025, 12, 25)),
    ("Pongal", "pongal", date(2026, 1, 14)),
    ("Tamil New Year", "other", date(2026, 4, 14)),
    ("Ganesh Chaturthi", "other", date(2026, 9, 14)),
    ("Diwali", "diwali", date(2026, 11, 8)),
    ("Christmas", "other", date(2026, 12, 25)),
    ("Pongal", "pongal", date(2027, 1, 14)),
]
FESTIVAL_GROUPS = ["diwali", "pongal", "other"]
# Shape of a festival effect relative to the festival day (fraction of peak uplift).
# Shoppers stock up during the week before; demand falls back right after (assumption).
FEST_SHAPE = {-6: 0.15, -5: 0.22, -4: 0.32, -3: 0.45, -2: 0.62, -1: 0.85, 0: 1.0, 1: 0.25}

# ---------------------------------------------------------------- forecasting
SEASON = 7                 # weekly seasonality on daily data
FORECAST_HORIZON = 28      # days shown and used for reorder maths
MA_WINDOW = 14             # moving-average look-back (days)
HW_PHI = 0.98              # damped trend (Gardner & McKenzie) stops runaway trend extrapolation
HW_ALPHAS = (0.05, 0.15, 0.3, 0.5)   # grid searched on training data only
HW_BETAS = (0.0, 0.03, 0.1)
HW_GAMMAS = (0.05, 0.15, 0.3)
RIDGE_LAMBDA = 0.5         # tiny ridge penalty keeps the regression solvable with rare features

BACKTEST_FOLDS = 4         # rolling-origin folds
BACKTEST_HORIZON = 14      # each fold forecasts 14 days ahead
BACKTEST_STEP = 14         # origins 14 days apart -> the last 56 days are tested out of sample
MIN_TRAIN_DAYS = 28
SELECT_METRIC = "smape"    # "smape" is robust to zero-sales days; "mape" also supported
MODEL_ORDER = ["snaive", "ma", "hw", "linreg"]   # ties go to the simpler model
MODEL_NAMES = {
    "snaive": "Seasonal naive",
    "ma": "Moving average (14 d)",
    "hw": "Holt-Winters (additive, weekly)",
    "linreg": "Regression (day-of-week + festival)",
}
STOCKOUT_P0 = 0.01         # a zero-sales day is a probable stock-out if P(0 | Poisson mean) < 1%

# ---------------------------------------------------------------- inventory policy
SERVICE_LEVEL = 0.95       # default cycle service level (probability of no stock-out per cycle)
ORDER_COST = 50.0          # Rs per order line: ~10 min of owner time + share of delivery charge (assumption)
HOLDING_RATE = 0.24        # per year, as a fraction of unit cost: ~12% cost of capital
                           # + ~12% space, shrinkage, damage (assumption)
SELLABLE_FRACTION = 0.75   # sell perishables within 75% of shelf life (customers avoid near-expiry)
PERISHABLE_DAYS = 30       # shelf life at or below this is treated as perishable
MAX_COVER_DAYS = 30        # never order more than ~a month of demand: small shop, limited cash/space
REVIEW_DAYS = 1            # stock reviewed every morning: protection interval = lead time + 1 day
SERVICE_GRID = (0.80, 0.85, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 0.999)

# ---------------------------------------------------------------- ABC-XYZ
ABC_A = 0.80               # A = items making the first 80% of revenue (Pareto)
ABC_B = 0.95               # B = next 15%, C = last 5%
XYZ_X = 0.20               # CV of weekly demand (whole history) below 0.20 = steady (X)
XYZ_Y = 0.35               # 0.20-0.35 = variable (Y); above = erratic/festival-driven (Z)
                           # (assumption tuned for weekly data of a small store; adjust per store)

# ---------------------------------------------------------------- market basket
MIN_SUPPORT = 0.02         # itemset must appear in at least 2% of bills
MIN_CONFIDENCE = 0.30
MIN_LIFT = 1.2

# ---------------------------------------------------------------- simulation
SIM_DAYS = 90              # compare policies over the last 90 days of history
SIM_WARMUP = 14            # both policies run 14 days before measurement starts
SIM_REFIT_EVERY = 7        # StockSense re-forecasts weekly in the simulation
GUT_BUFFER = 1.10          # gut-feel order = recent average demand + 10% "to be safe" (assumption)

# ---------------------------------------------------------------- upload limits
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_ROWS = 300000
MAX_SKUS = 60
MIN_HISTORY_DAYS = 90
MAX_HISTORY_DAYS = 730
DEFAULT_ITEM = {           # used for uploaded SKUs we know nothing about (shown as "assumed")
    "name": None, "category": "Uploaded", "price": 100.0, "cost": 80.0,
    "shelf_life": 365, "lead_time": 3, "lead_sd": 1.0, "pack": 1,
}
