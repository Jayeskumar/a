"""All tunable assumptions for PulseGuard live here, each with its source or reasoning.

Nothing in this file is a clinical recommendation; it is a hackathon prototype.
"""

# --- Simulation clock -------------------------------------------------------
# A bedside monitor / wearable gives a reading every 15 minutes in our simulation.
# (Assumption: low-cost multi-parameter ward monitors can easily sample this often.)
READING_INTERVAL_MIN = 15
STEPS_PER_HOUR = 60 // READING_INTERVAL_MIN          # 4
SCENARIO_HOURS = 24                                    # one simulated ward day
SCENARIO_STEPS = SCENARIO_HOURS * STEPS_PER_HOUR       # 96 (readings 0..96)
RESET_STEP = 2 * STEPS_PER_HOUR                        # reset shows 2 h of history
SCENARIO_START_CLOCK_MIN = 6 * 60                      # scenario starts at 06:00
REAL_SECONDS_PER_STEP = 1.0                            # at 1x speed: 15 sim-min per real second
ALLOWED_SPEEDS = (1, 4, 8)
DEFAULT_SEED = 42

# Manual observation rounds on a paper-chart ward (comparison baseline).
# NEWS2 recommends a minimum of 4-6 hourly observations for scores 1-4; understaffed
# wards often manage only this. We assume a 4-hourly round (the *best* case of that range).
MANUAL_ROUND_HOURS = 4

# --- NEWS2 escalation thresholds (RCP 2017) --------------------------------
NEWS2_MEDIUM_THRESHOLD = 5     # aggregate 5-6: key threshold for urgent response
NEWS2_HIGH_THRESHOLD = 7       # aggregate >=7: emergency response

# --- Trend-based early warning (our addition on top of NEWS2) ---------------
# Window of readings for least-squares slope estimation: 12 readings = 3 h at 15-min sampling.
# Tuned on the simulator (seeds 1-30, see evaluation.py): shorter windows chase noise,
# longer ones react too late.
TREND_WINDOW = 12
TREND_MIN_READINGS = 8
# How far ahead (hours) to project each significant vital-sign trend.
TREND_HORIZON_H = 4.0
# A vital's trend counts as "significant" only if the line explains the data well (R^2)
# and the projected change over the horizon is clinically meaningful (minimum delta).
TREND_MIN_R2 = 0.55
TREND_MIN_DELTA = {          # change over TREND_HORIZON_H that we consider meaningful
    "rr": 2.0,               # breaths/min
    "spo2": 1.5,             # %
    "sbp": 8.0,              # mmHg
    "hr": 8.0,               # beats/min
    "temp": 0.4,             # deg C
}
# Early warning fires when the projected NEWS2 reaches the medium threshold
# and is at least this many points above the current score...
TREND_MIN_PROJECTED_RISE = 2
# ...and at least this many vitals are trending in a worsening direction.
TREND_MIN_WORSENING_VITALS = 2
# ...or when the aggregate score itself rises steeply (points/hour, with good fit).
SCORE_SLOPE_ALERT = 1.0
SCORE_SLOPE_MIN_R2 = 0.6
SCORE_SLOPE_MIN_CURRENT = 3
# The early-warning condition must hold for this many consecutive readings (debounce noise).
TREND_CONFIRM_READINGS = 2
# Do not repeat a trend alert for the same patient within this many hours.
TREND_ALERT_COOLDOWN_H = 3.0
# A threshold alert re-arms only after the band has stayed lower for this many readings.
THRESHOLD_REARM_READINGS = 4

# --- Manual entry validation: physiologically *possible* input range ---------
# These are sanity limits to catch typos (e.g. 1200 instead of 120), not clinical norms.
VALID_RANGES = {
    "rr": (0, 80),
    "spo2": (40, 100),
    "sbp": (40, 300),
    "hr": (20, 250),
    "temp": (25.0, 45.0),
}
