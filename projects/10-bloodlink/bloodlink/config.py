"""Every tunable assumption of BloodLink lives here, with its source or reasoning.

Medical rules are commonly cited Indian values for *whole-blood* donation and are marked
"verify": always check them against the current NBTC / Drugs & Cosmetics Rules guidance
and the local blood bank's SOP before any real use. Everything marked "assumption" is a
modelling choice for the simulator, not a measured statistic.
"""
import datetime as _dt

# --------------------------------------------------------------------------------------
# Demo clock and seeds
# --------------------------------------------------------------------------------------
# The synthetic registry is generated relative to this date so the demo is identical on
# every run (QUANTIX 2K26 day 1). The donor self-check page uses the viewer's real date.
DEMO_TODAY = _dt.date(2026, 10, 23)
DEMO_NOW = _dt.datetime(2026, 10, 23, 10, 0)
SEED = 2026                 # donor registry + blood bank network
N_DONORS = 300

DISCLAIMER = ("Prototype for a hackathon demo with synthetic data. BloodLink only helps find "
              "and contact donors and move stock; every transfusion decision follows ABO/Rh "
              "grouping, antibody screening and cross-matching by qualified blood bank staff.")

# --------------------------------------------------------------------------------------
# Blood groups
# --------------------------------------------------------------------------------------
BLOOD_GROUPS = ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]

# Share of each group used ONLY to synthesise donors and demand (approx.). India-wide
# surveys put O+ and B+ as the most common groups and Rh-negative at roughly 5%; the
# exact split varies by region, so treat these as rough, not as a statistic.
GROUP_SHARE = {"O+": 0.36, "B+": 0.31, "A+": 0.22, "AB+": 0.06,
               "O-": 0.02, "B-": 0.015, "A-": 0.01, "AB-": 0.005}

# --------------------------------------------------------------------------------------
# Donor eligibility (whole blood) -- commonly cited Indian values, VERIFY before real use
# --------------------------------------------------------------------------------------
AGE_MIN = 18
AGE_MAX = 65
WEIGHT_MIN_KG = 45.0          # minimum for a 350 mL bag (verify; 450 mL bags need more)
MIN_INTERVAL_DAYS = {"M": 90, "F": 120}   # between whole-blood donations (verify vs NBTC)
HB_MIN_G_DL = 12.5            # self-reported haemoglobin, optional (verify vs NBTC)
ELIGIBILITY_SOURCE = "Commonly cited Indian whole-blood criteria - verify against current NBTC/blood-bank guidelines"

# --------------------------------------------------------------------------------------
# Geography and travel (approx.)
# --------------------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0088   # IUGG mean Earth radius
ROAD_CIRCUITY = 1.3           # road km ~ 1.2-1.4 x straight-line km for regional roads (approx.)
AVG_SPEED_KMPH = 35.0         # assumption: mixed district roads by two-wheeler/car
PREP_MIN = 10.0               # assumption: time for a donor to leave home/work

# Approximate town-centre coordinates (rounded, approx.) used to place synthetic data.
TOWNS = [
    {"name": "Salem", "lat": 11.664, "lon": 78.146, "weight": 0.27},
    {"name": "Erode", "lat": 11.341, "lon": 77.717, "weight": 0.23},
    {"name": "Namakkal", "lat": 11.219, "lon": 78.167, "weight": 0.15},
    {"name": "Tiruchengode", "lat": 11.380, "lon": 77.894, "weight": 0.15},
    {"name": "Rasipuram", "lat": 11.460, "lon": 78.183, "weight": 0.08},
    {"name": "Sankagiri", "lat": 11.475, "lon": 77.868, "weight": 0.06},
    {"name": "Bhavani", "lat": 11.446, "lon": 77.682, "weight": 0.06},
]
# Extra labels for the map only (approx.)
MAP_LABELS = [
    {"name": "Perundurai", "lat": 11.275, "lon": 77.588},
    {"name": "Omalur", "lat": 11.740, "lon": 78.047},
    {"name": "Paramathi", "lat": 11.153, "lon": 78.024},
    {"name": "Mettur", "lat": 11.790, "lon": 77.800},
]

# Fictional demo hospitals and blood banks (names are placeholders, not real institutions)
HOSPITALS = [
    {"id": "H1", "name": "Tiruchengode Hospital (demo)", "town": "Tiruchengode", "lat": 11.383, "lon": 77.898},
    {"id": "H2", "name": "Salem City Hospital (demo)", "town": "Salem", "lat": 11.668, "lon": 78.152},
    {"id": "H3", "name": "Erode Medical Centre (demo)", "town": "Erode", "lat": 11.338, "lon": 77.725},
    {"id": "H4", "name": "Namakkal Care Hospital (demo)", "town": "Namakkal", "lat": 11.226, "lon": 78.160},
    {"id": "H5", "name": "Rasipuram Clinic (demo)", "town": "Rasipuram", "lat": 11.456, "lon": 78.177},
    {"id": "H6", "name": "Bhavani Hospital (demo)", "town": "Bhavani", "lat": 11.450, "lon": 77.690},
]

# --------------------------------------------------------------------------------------
# Donor ranking (transparent weighted score, weights sum to 1)
# --------------------------------------------------------------------------------------
W_COMPAT = 0.30
W_DISTANCE = 0.30
W_RESPONSE = 0.25
W_FAIRNESS = 0.15
# Reasoning: compatible-but-not-identical units use scarce groups (Rh-negative, O) that
# other patients may need, so an exact match is preferred.
COMPAT_PENALTY_RH = 0.25      # Rh- donor for an Rh+ patient
COMPAT_PENALTY_ABO = 0.25     # e.g. O donor for an A patient
# Distance score = exp(-travel_min / tau); urgent cases decay faster with travel time.
URGENCY_TAU_MIN = {"critical": 25.0, "urgent": 45.0, "planned": 90.0}
URGENCIES = ["critical", "urgent", "planned"]
RESPONSE_PRIOR = (2.0, 2.0)   # Beta(2,2) prior: a donor with no history scores 0.5
FAIRNESS_WINDOW_DAYS = 14.0   # a donor contacted N days ago gets N/14 of the fairness points
MAX_UNITS_PER_REQUEST = 10

# --------------------------------------------------------------------------------------
# Broadcast simulator (assumptions, used for every strategy alike unless noted)
# --------------------------------------------------------------------------------------
RESPONSE_MEAN_MIN = 6.0       # mean reply delay to an app/SMS alert (assumption)
DECLINE_SHARE = 0.6           # of non-accepting donors, share that reply "no" (rest: silent)
SHOWUP_PROB = 0.9             # accepted donors who actually arrive (assumption)
SCREEN_PASS_PROB = 0.92       # on-site Hb/BP/questionnaire pass for registry-eligible donors (assumption)
DONATION_MIN = 30.0           # registration + screening + draw (approx.)
TRAVEL_NOISE = (0.85, 1.35)   # uniform multiplier on estimated travel time (assumption)
DISTANCE_WILLINGNESS_KM = 40.0  # accept prob x 1/(1 + km/40): farther donors less willing (assumption)
RECENT_CONTACT_FATIGUE = 0.7    # accept prob x 0.7 if alerted in the last 3 days (assumption)
RECENT_CONTACT_DAYS = 3.0
WAVE_INTERVAL_MIN = 10.0
WAVE_MIN = 3
WAVE_MAX = 12
WAVE_BUFFER = 0.25            # keep ~25% more confirmed donors than units as no-show cover
NOSHOW_GRACE_MIN = 15.0
SIM_HORIZON_MIN = 360.0
# Baseline 1: forward to everyone (WhatsApp-style). Family asks for the exact group only,
# cannot check eligibility, cannot stop people once they set off.
BROADCAST_REACH_MEAN_MIN = 20.0   # forward chains reach people over time (assumption)
BROADCAST_RESPONSE_FACTOR = 0.6   # diffusion of responsibility in mass forwards (assumption; set 1.0 to disable)
BROADCAST_RADIUS_KM = 60.0
# Baseline 2: first-come phone list (register order, exact group, one coordinator).
CALL_MIN = 3.0                    # per call incl. ringing / no answer (assumption)

# --------------------------------------------------------------------------------------
# Blood bank inventory network
# --------------------------------------------------------------------------------------
# Packed red cells: 35 days in CPDA-1, up to 42 days with SAGM additive solution.
SHELF_LIFE_DAYS = {"CPDA-1": 35, "SAGM": 42}
SAGM_SHARE = 0.5              # assumption: half the units use SAGM bags
MA_WINDOW_DAYS = 7            # moving-average window for demand forecasting
TARGET_COVER_DAYS = 3.0       # stock target = 3 days of forecast demand
LOW_COVER_DAYS = 2.0          # below this the group is flagged "low"
MAX_TRANSFER_KM = 90.0
TRANSIT_DAYS = 1              # a transferred unit is usable at the receiver the next day
NETWORK_HISTORY_DAYS = 28     # demand history shown/used for the snapshot
NETWORK_WARMUP_DAYS = 90     # simulated days before the snapshot so stock ages reach steady state (> shelf life)

# Fictional demo blood banks. Daily red-cell demand / regular collections are synthetic;
# small towns get periodic college/community camps that create short-lived gluts.
BANKS = [
    {"id": "BB1", "name": "Salem Blood Centre (demo)", "town": "Salem", "lat": 11.660, "lon": 78.140,
     "demand_per_day": 14.0, "collect_ratio": 0.88, "camp_every_days": 0, "camp_size": (0, 0)},
    {"id": "BB2", "name": "Erode Blood Centre (demo)", "town": "Erode", "lat": 11.345, "lon": 77.710,
     "demand_per_day": 10.0, "collect_ratio": 0.88, "camp_every_days": 0, "camp_size": (0, 0)},
    {"id": "BB3", "name": "Namakkal Blood Centre (demo)", "town": "Namakkal", "lat": 11.222, "lon": 78.172,
     "demand_per_day": 6.0, "collect_ratio": 0.85, "camp_every_days": 15, "camp_size": (30, 50)},
    {"id": "BB4", "name": "Tiruchengode Blood Centre (demo)", "town": "Tiruchengode", "lat": 11.376, "lon": 77.890,
     "demand_per_day": 4.0, "collect_ratio": 0.8, "camp_every_days": 12, "camp_size": (30, 50)},
    {"id": "BB5", "name": "Rasipuram Blood Centre (demo)", "town": "Rasipuram", "lat": 11.465, "lon": 78.188,
     "demand_per_day": 2.0, "collect_ratio": 0.8, "camp_every_days": 20, "camp_size": (20, 40)},
]
