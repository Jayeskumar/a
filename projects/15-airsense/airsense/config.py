"""All tunable constants for AirSense, in one place.

Official numbers (CPCB National AQI) are marked SOURCE. Everything else is a modelling
assumption for the synthetic demo town and is marked ASSUMPTION with its reasoning.
"""

# ---------------------------------------------------------------------------
# India National Air Quality Index (NAQI)
# SOURCE: Central Pollution Control Board (CPCB), "National Air Quality Index",
#         Control of Urban Pollution Series CUPS/82/2014-15 (launched Oct 2014).
# Each row: (conc_lo, conc_hi, aqi_lo, aqi_hi). Units: ug/m3, except CO in mg/m3.
# The official table lists contiguous integer ranges (0-30, 31-60, ...). A value that
# falls in the gap between two rows (e.g. PM2.5 = 30.4) is interpolated linearly
# between the end of one row and the start of the next, so the sub-index is continuous
# and matches the table exactly at every published breakpoint.
# The "Severe" row is open-ended in the official table ("250+"). ASSUMPTION: like
# common open-source AQI calculators we extend it with the width of the "Very Poor"
# row so that the sub-index reaches 500 there, and cap the AQI at 500 above it.
# ---------------------------------------------------------------------------
AQI_SOURCE = "CPCB National Air Quality Index (CUPS/82/2014-15)"

BREAKPOINTS = {
    "pm25": [(0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200),
             (91, 120, 201, 300), (121, 250, 301, 400), (251, 380, 401, 500)],
    "pm10": [(0, 50, 0, 50), (51, 100, 51, 100), (101, 250, 101, 200),
             (251, 350, 201, 300), (351, 430, 301, 400), (431, 510, 401, 500)],
    "no2": [(0, 40, 0, 50), (41, 80, 51, 100), (81, 180, 101, 200),
            (181, 280, 201, 300), (281, 400, 301, 400), (401, 520, 401, 500)],
    "so2": [(0, 40, 0, 50), (41, 80, 51, 100), (81, 380, 101, 200),
            (381, 800, 201, 300), (801, 1600, 301, 400), (1601, 2400, 401, 500)],
    # CO in mg/m3, 8-hour average
    "co": [(0, 1.0, 0, 50), (1.1, 2.0, 51, 100), (2.1, 10, 101, 200),
           (10.1, 17, 201, 300), (17.1, 34, 301, 400), (34.1, 51, 401, 500)],
    # O3 8-hour average. CPCB notes the 209-748 and 748+ rows use one-hourly
    # monitoring "for mathematical calculation only".
    "o3": [(0, 50, 0, 50), (51, 100, 51, 100), (101, 168, 101, 200),
           (169, 208, 201, 300), (209, 748, 301, 400), (749, 1288, 401, 500)],
    "nh3": [(0, 200, 0, 50), (201, 400, 51, 100), (401, 800, 101, 200),
            (801, 1200, 201, 300), (1201, 1800, 301, 400), (1801, 2400, 401, 500)],
}

POLLUTANTS = {
    # key: (display name, unit, averaging period in hours)   SOURCE: CPCB NAQI table
    "pm25": ("PM2.5", "ug/m3", 24),
    "pm10": ("PM10", "ug/m3", 24),
    "no2": ("NO2", "ug/m3", 24),
    "so2": ("SO2", "ug/m3", 24),
    "co": ("CO", "mg/m3", 8),
    "o3": ("O3", "ug/m3", 8),
    "nh3": ("NH3", "ug/m3", 24),
}
POLLUTANT_ORDER = ["pm25", "pm10", "no2", "so2", "co", "o3", "nh3"]

# SOURCE (CPCB NAQI rules): AQI is reported only when sub-indices are available for at
# least three pollutants, one of which must be PM2.5 or PM10; a 24-hour sub-index needs
# at least 16 hourly values.
MIN_POLLUTANTS = 3
REQUIRED_ANY_OF = ("pm25", "pm10")
MIN_HOURS_24H = 16
# ASSUMPTION: the same 2/3 completeness applied to 8-hour averages (6 of 8 hours).
MIN_HOURS_8H = 6
AQI_MAX = 500

# SOURCE: CPCB category names, ranges and "associated health impacts" text.
# Colours: approx. hex of the CPCB AQI colour chart (dark green, light green, yellow,
# orange, red, maroon). "ink" is the readable text colour on that fill.
CATEGORIES = [
    {"key": "good", "name": "Good", "lo": 0, "hi": 50, "color": "#00B050", "ink": "#06210f",
     "health": "Minimal impact."},
    {"key": "satisfactory", "name": "Satisfactory", "lo": 51, "hi": 100, "color": "#92D050",
     "ink": "#1b2b0a", "health": "May cause minor breathing discomfort to sensitive people."},
    {"key": "moderate", "name": "Moderate", "lo": 101, "hi": 200, "color": "#FFFF00",
     "ink": "#2b2b00",
     "health": "May cause breathing discomfort to people with lung disease such as asthma, "
               "and discomfort to people with heart disease, children and older adults."},
    {"key": "poor", "name": "Poor", "lo": 201, "hi": 300, "color": "#FF9900", "ink": "#2e1a00",
     "health": "May cause breathing discomfort to people on prolonged exposure, and "
               "discomfort to people with heart disease."},
    {"key": "very_poor", "name": "Very Poor", "lo": 301, "hi": 400, "color": "#FF0000",
     "ink": "#ffffff",
     "health": "May cause respiratory illness to people on prolonged exposure. Effect may be "
               "more pronounced in people with lung and heart diseases."},
    {"key": "severe", "name": "Severe", "lo": 401, "hi": 500, "color": "#C00000",
     "ink": "#ffffff",
     "health": "May cause respiratory impact even on healthy people, and serious health "
               "impacts on people with lung/heart disease. The health impacts may be "
               "experienced even during light physical activity."},
]

# ---------------------------------------------------------------------------
# Personal advice. ASSUMPTION: our own guidance layered on the CPCB statements
# (sensitive groups act one category earlier than the general public). Not medical advice.
# alert_from = lowest AQI at which this profile receives a push alert.
# ---------------------------------------------------------------------------
PROFILES = {
    "general": {"name": "General public", "alert_from": 201, "run_max": 100,
                "advice": {
                    "good": "Great day to be outside.",
                    "satisfactory": "Fine for outdoor activity.",
                    "moderate": "OK for most people; take breaks during long outdoor exercise.",
                    "poor": "Cut down long or heavy outdoor exertion; prefer indoor workouts.",
                    "very_poor": "Avoid long outdoor activity; keep windows shut at peak hours.",
                    "severe": "Stay indoors; wear an N95/FFP2 mask if you must go out."}},
    "asthma": {"name": "Asthma / COPD", "alert_from": 101, "run_max": 50,
               "advice": {
                   "good": "Normal activity. Keep your reliever inhaler with you as usual.",
                   "satisfactory": "Watch for symptoms during exercise; carry your inhaler.",
                   "moderate": "Limit outdoor exertion; carry reliever inhaler; avoid busy roads.",
                   "poor": "Avoid outdoor exercise; stay away from traffic and smoke; follow your action plan.",
                   "very_poor": "Stay indoors with windows shut; contact your doctor if symptoms rise.",
                   "severe": "Stay indoors; use an air purifier if available; seek care if breathless."}},
    "children": {"name": "Children & schools", "alert_from": 101, "run_max": 100,
                 "advice": {
                     "good": "Outdoor play and PE are fine.",
                     "satisfactory": "Outdoor play is fine; sensitive children should take breaks.",
                     "moderate": "Shorten PE and outdoor play; prefer shaded areas away from roads.",
                     "poor": "Move PE and assembly indoors.",
                     "very_poor": "No outdoor activity; keep classrooms closed at peak hours.",
                     "severe": "Keep children indoors; schools should consider closure."}},
    "outdoor_worker": {"name": "Outdoor workers", "alert_from": 201, "run_max": 100,
                       "advice": {
                           "good": "No restrictions.",
                           "satisfactory": "No restrictions.",
                           "moderate": "Schedule heavy work for the cleanest hours; drink water.",
                           "poor": "Wear an N95/FFP2 mask; rotate tasks and take indoor breaks.",
                           "very_poor": "Mask mandatory; reduce shift length and heavy labour.",
                           "severe": "Stop non-essential outdoor work."}},
    "elderly": {"name": "Elderly & heart patients", "alert_from": 101, "run_max": 50,
                "advice": {
                    "good": "Normal activity.",
                    "satisfactory": "Normal activity; take it easy if you feel unwell.",
                    "moderate": "Avoid strenuous outdoor walks; go out when it is cleanest.",
                    "poor": "Stay indoors at peak hours; watch for chest pain or breathlessness.",
                    "very_poor": "Stay indoors; keep medicines handy.",
                    "severe": "Stay indoors; seek medical help for any chest symptoms."}},
}
RUN_WINDOW_HOURS = (5, 21)   # ASSUMPTION: consider runs between 05:00 and 21:59

# ---------------------------------------------------------------------------
# Synthetic demo town (Tiruchengode/Namakkal-like layout, NOT real geography).
# Coordinates are km east (x) / north (y) of the south-west corner.
# ---------------------------------------------------------------------------
SEED = 2026
MAP_W_KM = 12.0
MAP_H_KM = 8.0
START_DATE = "2026-09-25"     # first field hour (00:00 local). Synthetic period.
FIELD_DAYS = 28
COLOC_DAYS = 7                 # pre-deployment co-location week before START_DATE
COLOC_TRAIN_DAYS = 5           # first 5 days train calibration, last 2 days test

TOWN_CENTRE = (6.0, 4.6)
HIGHWAY = [(0.0, 7.9), (2.5, 7.3), (4.8, 6.6), (8.0, 6.0), (10.0, 5.3), (12.0, 4.4)]
INDUSTRY = (9.9, 2.1)
CONSTRUCTION = (5.3, 5.9)
FIELDS = (0.7, 3.3)
HILL = (3.6, 2.6)

LANDMARKS = [
    {"id": "centre", "name": "Town centre & bus stand", "x": 6.0, "y": 4.6, "kind": "traffic"},
    {"id": "highway", "name": "Highway corridor (heavy trucks at night)", "kind": "road"},
    {"id": "industry", "name": "Industrial cluster (boilers, lorry-body workshops)",
     "x": INDUSTRY[0], "y": INDUSTRY[1], "kind": "industry"},
    {"id": "construction", "name": "Flyover construction site", "x": CONSTRUCTION[0],
     "y": CONSTRUCTION[1], "kind": "construction"},
    {"id": "fields", "name": "Farm fields (crop-residue burning)", "x": FIELDS[0], "y": FIELDS[1],
     "kind": "burning"},
    {"id": "hill", "name": "Hill & temple (green)", "x": HILL[0], "y": HILL[1], "kind": "green"},
]

REFERENCE_STATIONS = [
    # Continuous ambient monitoring stations measuring all 7 NAQI pollutants.
    {"id": "REF-A", "name": "Reference A (Govt Hospital)", "x": 6.3, "y": 4.2},
    {"id": "REF-B", "name": "Reference B (Industrial Estate)", "x": 9.0, "y": 2.9},
]

# 25 low-cost optical PM sensors. "coloc" = reference station used for the
# pre-deployment co-location week. S01 and S14 stay next to the references in the field.
SENSORS = [
    ("S01", "Govt Hospital (at REF-A)", 6.3, 4.2, "REF-A"),
    ("S02", "Bus Stand", 6.0, 4.7, "REF-A"),
    ("S03", "Market Street", 6.6, 5.0, "REF-A"),
    ("S04", "Car Street", 5.4, 4.3, "REF-A"),
    ("S05", "Hill Road", 4.3, 3.1, "REF-A"),
    ("S06", "Temple Foothill", 3.5, 2.3, "REF-A"),
    ("S07", "Weavers' Colony", 8.2, 2.5, "REF-A"),
    ("S08", "Railway Gate", 7.6, 3.4, "REF-A"),
    ("S09", "College Campus", 2.2, 5.6, "REF-A"),
    ("S10", "Highway Toll Plaza", 1.8, 7.4, "REF-A"),
    ("S11", "Highway Junction", 4.6, 6.5, "REF-A"),
    ("S12", "Flyover Site", 5.2, 5.8, "REF-A"),
    ("S13", "Workshop Row", 8.6, 5.75, "REF-A"),
    ("S14", "Industrial Estate (at REF-B)", 9.0, 2.9, "REF-B"),
    ("S15", "Dyeing Units", 10.6, 1.5, "REF-B"),
    ("S16", "East Bypass", 10.8, 3.4, "REF-B"),
    ("S17", "Primary School", 7.0, 6.6, "REF-B"),
    ("S18", "North Residential", 6.4, 7.8, "REF-B"),
    ("S19", "Lake View", 3.0, 4.2, "REF-B"),
    ("S20", "Farm Village West", 1.2, 2.4, "REF-B"),
    ("S21", "Agri Market", 2.4, 3.3, "REF-B"),
    ("S22", "South Layout", 6.2, 1.5, "REF-B"),
    ("S23", "East Residential", 8.0, 4.4, "REF-B"),
    ("S24", "Highway East", 11.0, 4.6, "REF-B"),
    ("S25", "North-East Colony", 10.2, 7.0, "REF-B"),
]

# Scenario calendar (day index from START_DATE). ASSUMPTION: synthetic scenario.
BURN_DAYS = [4, 11, 23]                 # evenings 17:00-23:00
CONSTRUCTION_FROM_DAY = 10              # Mon-Sat 08:00-18:00 from this day on
FESTIVAL_DAY = 19                       # fireworks 18:00 to 02:00 next morning
RAIN_SPELLS = [(14 * 24 + 4, 14 * 24 + 40, 9.0),   # (start hour, end hour, mm/h peak)
               (25 * 24 + 14, 25 * 24 + 22, 14.0),
               (2 * 24 + 15, 2 * 24 + 18, 3.0)]
COLOC_RAIN = [(-5 * 24 + 12, -5 * 24 + 22, 6.0), (-1 * 24 + 2, -1 * 24 + 9, 3.0)]
WIND_SHIFT_DAY = 13.5     # SW-monsoon westerlies give way to north-east monsoon easterlies

# Injected sensor faults (ground truth for evaluating the detector).
# drift: kind gain -> multiplier grows by rate per day; offset -> ug/m3 per day.
FAULTS = [
    {"sensor": "S05", "type": "drift", "kind": "gain", "start_day": 12, "rate": 0.035},
    {"sensor": "S17", "type": "drift", "kind": "offset", "start_day": 14, "rate": 3.0},
    {"sensor": "S21", "type": "drift", "kind": "gain", "start_day": 8, "rate": -0.03},
    {"sensor": "S09", "type": "stuck", "start_hour": 9 * 24 + 14, "hours": 30},
    {"sensor": "S18", "type": "stuck", "start_hour": 21 * 24 + 3, "hours": 16},
    {"sensor": "S03", "type": "stuck", "start_hour": 25 * 24 + 8, "hours": 10},
]
N_SPIKES = 14                  # isolated one-hour spikes (insects, dust puffs, EMI)
MISSING_RATE = 0.004           # random missing hours (packet loss)
OUTAGES = [("S15", 17 * 24 + 1, 9)]   # (sensor, start hour, hours): power cut

# ---------------------------------------------------------------------------
# Detector / model settings (ASSUMPTION: tuned on the synthetic data, see REPORT.md)
# ---------------------------------------------------------------------------
STUCK_MIN_RUN = 5            # identical consecutive readings (0.1 ug/m3 resolution)
SPIKE_Z = 15.0               # temporal robust z (vs. both neighbouring hours)
SPIKE_SPATIAL_RATIO = 2.2    # and at least this many times the neighbour median
SPIKE_MIN_EXCESS = 25.0      # ug/m3
DRIFT_Z = 3.0                # robust z of the daily log-ratio change vs. neighbours
DRIFT_MIN_DAYS = 3           # consecutive days above threshold to raise a drift flag
DRIFT_BASELINE_DAYS = 4      # first days after calibration taken as healthy baseline
DRIFT_QUANTILE = 35          # daily lower quantile of the hourly log-ratio to neighbours
NEIGHBOURS_K = 6             # spatial neighbours used for medians
IDW_POWER = 2.0
KRIGING_MAX_RANGE_KM = 8.0
KAPPA_RANGE = (0.0, 1.0)     # hygroscopic growth parameter search range
RIDGE_LAMBDA = 1e-3
FORECAST_HOLDOUT_DAYS = 7
FORECAST_ORIGIN_STEP_H = 6
