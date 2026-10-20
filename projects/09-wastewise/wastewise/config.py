"""Every tunable assumption of WasteWise lives here, with the reasoning behind it.

Numbers marked "approx." are rough planning values, not measured facts. Replace them with
the figures of your own municipality / fleet before using the projections for decisions.
"""

# --------------------------------------------------------------------------- simulation
SEED = 2026                    # one seed -> the whole town, history and demo reports
START_DATE = "2026-10-27"      # simulated "day 0" (a Tuesday; the market day follows)
HISTORY_DAYS = 42              # 6 weeks of sensor history before day 0 (fits weekly seasonality)
MONTH_DAYS = 30                # horizon of the "simulated month" evaluation

# --------------------------------------------------------------------------- town (fictional)
# A grid town loosely sized like a small Tamil Nadu municipality core (e.g. Tiruchengode).
# Coordinates are kilometres on a street grid; distances are Manhattan (you drive along streets).
TOWN_W_KM = 6.0
TOWN_H_KM = 4.0
STREET_KM = 0.25               # block size: bins sit on street intersections
N_BINS = 40
DEPOT_XY = (3.25, -0.75)       # transfer station / compost yard just south of town
MARKET_WEEKDAY = 2             # 0=Mon ... 2=Wed: weekly shandy (santhai) day - fictional, set yours

# --------------------------------------------------------------------------- fleet (approx.)
N_TRUCKS = 3
TRUCK_CAPACITY_L = 6000        # approx. loose-waste hopper volume of a small tipper/compactor
PLAN_CAPACITY_SHARE = 0.92     # plan to 92% of capacity: buffer for forecast error
SPEED_KMPH = 15.0              # approx. average town speed incl. junctions and stops
SERVICE_MIN_PER_BIN = 8.0      # approx. lift, tip, sweep spillage, check segregation
UNLOAD_MIN = 20.0              # approx. queue + tip at the transfer station
SHIFT_START_H = 6.0            # trucks leave the depot at 06:00
SHIFT_MIN = 210.0              # 3.5 h collection window (06:00-09:30, before school/office traffic)

# --------------------------------------------------------------------------- fuel & money
TRUCK_KM_PER_L = 4.0           # approx. diesel mileage of a loaded tipper in stop-go town driving
IDLE_L_PER_H = 1.5             # approx. idling + hydraulic lift fuel while servicing a bin
DIESEL_INR_PER_L = 90.0        # approx. Indian retail diesel price (update to today's price)
CO2_KG_PER_L_DIESEL = 2.68     # approx. tailpipe CO2 from burning 1 litre of diesel (widely used)
COLLECTION_DAYS_PER_YEAR = 365 # Indian towns typically collect daily, including Sundays

# --------------------------------------------------------------------------- waste deposit model
# Households/shops drop waste between 05:00 and 23:00, assumed uniform over that window.
DEPOSIT_START_H = 5.0
DEPOSIT_END_H = 23.0
SENSOR_NOISE = 0.02            # std-dev of the fill-sensor reading (fraction of capacity)

# --------------------------------------------------------------------------- smart policy
COLLECT_THRESHOLD = 0.75       # Rule A: collect if predicted >= 75% full when the truck passes
PLAN_ARRIVAL_H = 7.75          # planning assumption for "when the truck passes" (mid-window)
OVERFLOW_LIMIT = 1.0           # Rule B: collect if skipping would overflow before tomorrow's run
SAFETY_SIGMA = 1.0             # ... using forecast + 1 sigma of the bin's forecast error

# --------------------------------------------------------------------------- segregation game
POINTS_CORRECT = 10            # green points for a correctly segregated report
POINTS_REPORT = 2              # participation points even when the bin was wrong
DEMO_REPORTS = 320             # deterministic demo reports generated on first run

# --------------------------------------------------------------------------- display
TRUCK_COLORS = ["#059669", "#d97706", "#6366f1"]  # validated CVD-distinct set (labels T1-T3 too)


def assumptions():
    """The constants shown in the Impact panel (name, value, unit, note)."""
    return [
        {"name": "DIESEL_INR_PER_L", "value": DIESEL_INR_PER_L, "unit": "INR/L",
         "note": "approx. retail diesel price in India; update locally"},
        {"name": "TRUCK_KM_PER_L", "value": TRUCK_KM_PER_L, "unit": "km/L",
         "note": "approx. loaded tipper, stop-and-go town driving"},
        {"name": "IDLE_L_PER_H", "value": IDLE_L_PER_H, "unit": "L/h",
         "note": "approx. idling + hydraulic lift while servicing"},
        {"name": "CO2_KG_PER_L_DIESEL", "value": CO2_KG_PER_L_DIESEL, "unit": "kg/L",
         "note": "approx. CO2 per litre of diesel burned"},
        {"name": "SPEED_KMPH", "value": SPEED_KMPH, "unit": "km/h",
         "note": "approx. average town speed"},
        {"name": "SERVICE_MIN_PER_BIN", "value": SERVICE_MIN_PER_BIN, "unit": "min",
         "note": "approx. time to empty one bin"},
        {"name": "TRUCK_CAPACITY_L", "value": TRUCK_CAPACITY_L, "unit": "L",
         "note": "approx. hopper volume (loose waste)"},
        {"name": "SHIFT_MIN", "value": SHIFT_MIN, "unit": "min",
         "note": "collection window per truck (06:00-09:30)"},
        {"name": "COLLECTION_DAYS_PER_YEAR", "value": COLLECTION_DAYS_PER_YEAR, "unit": "days",
         "note": "daily collection incl. Sundays"},
        {"name": "COLLECT_THRESHOLD", "value": COLLECT_THRESHOLD, "unit": "fill",
         "note": "Rule A trigger level at truck arrival"},
    ]
