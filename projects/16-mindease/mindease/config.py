"""Every tunable assumption for MindEase lives here, with its source or reasoning.

Nothing in this file is a clinical recommendation. MindEase is a hackathon prototype for
supportive screening and self-help; it does not diagnose or treat anything.
"""

# --- Help resources ---------------------------------------------------------
# Tele-MANAS is the Government of India's national tele-mental-health helpline
# (Ministry of Health & Family Welfare, launched Oct 2022): free, 24x7, multilingual.
# 112 is India's single emergency number (ERSS). We deliberately list no other numbers:
# a wrong helpline number is worse than none. Colleges add their own counselling cell
# contact in COUNSELLING_CELL below.
HELPLINES = [
    {
        "id": "telemanas",
        "name": "Tele-MANAS",
        "numbers": ["14416", "1-800-891-4416"],
        "tel": ["14416", "18008914416"],
        "desc": "Free national mental-health helpline (Govt. of India), 24x7, in many languages.",
    },
    {
        "id": "emergency",
        "name": "Emergency services",
        "numbers": ["112"],
        "tel": ["112"],
        "desc": "If you or someone else is in immediate danger, call 112 now.",
    },
]
# Placeholder on purpose: each college fills in its own counselling cell details.
COUNSELLING_CELL = {
    "name": "Your college counselling cell",
    "how": "Ask the student welfare office or your class mentor for the counsellor's "
           "room and hours. In this demo, 'Ask a counsellor to reach out' sends a "
           "pseudonymous request to the counsellor dashboard.",
}

# --- Questionnaires -----------------------------------------------------------
# Published severity bands (Kroenke, Spitzer & Williams 2001 for PHQ-9;
# Spitzer et al. 2006 for GAD-7). Each tuple is (lowest score, highest score, band id).
PHQ9_BANDS = [
    (0, 4, "minimal"),
    (5, 9, "mild"),
    (10, 14, "moderate"),
    (15, 19, "moderately_severe"),
    (20, 27, "severe"),
]
GAD7_BANDS = [
    (0, 4, "minimal"),
    (5, 9, "mild"),
    (10, 14, "moderate"),
    (15, 21, "severe"),
]
# PHQ-9 >= 10 and GAD-7 >= 10 are the commonly used cut-points for "consider further
# assessment" in the original validation papers.
REFER_CUTOFF = 10

# --- Sentiment analyser -----------------------------------------------------------
# Structure follows the VADER idea (Hutto & Gilbert 2014): word valences on a -4..+4
# scale, rule-based modifiers, and a squashing normaliser. The lexicon and code are ours.
NEGATION_WINDOW = 3          # a negator flips valence words up to 3 tokens after it
NEGATION_SCALAR = -0.74      # VADER's empirically chosen damping for a negated word
INTENSIFIER_BOOST = 0.293    # added to |valence| by "very", "romba", ... (VADER constant)
DIMINISHER_DROP = -0.293     # "slightly", "konjam", ...
BUT_BEFORE_WEIGHT = 0.5      # clause before "but" counts half ...
BUT_AFTER_WEIGHT = 1.5       # ... and the clause after it counts 1.5x
EXCLAIM_BOOST = 0.292        # per "!" (max 3) in the direction of the overall sum
CAPS_BOOST = 0.733           # an ALL-CAPS valence word in mixed-case text
NORMALISE_ALPHA = 15.0       # compound = s / sqrt(s^2 + alpha), maps to (-1, 1)
# VADER uses +/-0.05. Journal text is full of mild words ("okay", "late", "fine") that
# students mean as neutral, so we widened the neutral band to +/-0.2. Tuned on the DEV
# set only (eval_sets.SENTIMENT_DEV); one strong word (|v| >= 0.8) still crosses it.
POSITIVE_THRESHOLD = 0.2     # compound >= 0.2 -> "positive"
NEGATIVE_THRESHOLD = -0.2    # compound <= -0.2 -> "negative"

# --- Trend engine -----------------------------------------------------------------
BASELINE_MIN_POINTS = 5      # need at least 5 earlier days to know "your usual"
BASELINE_MAX_POINTS = 21     # baseline = up to 21 entries before the recent window
RECENT_WINDOW = 5            # the "recent" window that we compare with the baseline
ROLLING_WINDOW = 7           # 7-day trailing rolling average for charts
# Floors on the baseline spread so a very steady baseline does not make tiny changes
# look dramatic (mood is 1-5, sleep in hours, sentiment compound in -1..1).
SD_FLOOR = {"mood": 0.5, "sleep": 0.6, "sentiment": 0.25}
# One-sided lower CUSUM on standardised values (Page 1954). k = 0.5 sd is the textbook
# choice for detecting a ~1 sd shift. h = 5 was tuned on simulated journals (tuning
# seed 7, see evaluation.trend_eval): h = 4 with extra run/slope triggers flagged 21% of
# stable weeks; CUSUM h = 5 + a 2-day run flags ~3%. Held-out seed 101 is reported.
CUSUM_K = 0.5
CUSUM_H = 5.0
# "Dip run": consecutive most-recent days below baseline mean - DIP_SD * sd.
DIP_SD = 1.0
# A CUSUM alarm becomes an insight only if the latest DIP_RUN_MIN+ days are still below
# the dip threshold (so a dip that has already recovered says nothing).
DIP_RUN_MIN = 2
# OLS slope test over the most recent SLOPE_WINDOW days (one-sided t-test, 95%).
SLOPE_WINDOW = 7
# Sleep: adults 18-25 are advised 7-9 h (US National Sleep Foundation / AASM consensus).
SLEEP_LOW_HOURS = 6.0        # recent average below 6 h -> gentle sleep insight
SLEEP_RECOMMENDED = (7, 9)

# One-sided 95% critical values of Student's t for df = 1..30 (standard t table).
T_CRIT_95_ONE_SIDED = {
    1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860,
    9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782, 13: 1.771, 14: 1.761, 15: 1.753,
    16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729, 20: 1.725, 21: 1.721, 22: 1.717,
    23: 1.714, 24: 1.711, 25: 1.708, 26: 1.706, 27: 1.703, 28: 1.701, 29: 1.699,
    30: 1.697,
}

# --- Study planner ------------------------------------------------------------------
POMODORO_FOCUS_MIN = 25      # Cirillo's Pomodoro Technique: 25 min focus ...
POMODORO_BREAK_MIN = 5       # ... 5 min break ...
POMODORO_LONG_BREAK_MIN = 15  # ... longer break after every 4 pomodoros
POMODOROS_PER_SET = 4
MAX_STUDY_HOURS_PER_DAY = 8  # we refuse to plan more than this; rest matters
LATEST_STUDY_END = "22:30"   # protect sleep: no study block ends after this
PLANNER_MAX_DAYS = 30

# --- Demo data & counsellor dashboard --------------------------------------------------
# Seed picked by scanning seeds 1-199 for a demo-friendly cohort (a visible exam spike, a
# mix of new / acknowledged / followed-up alerts). The data is synthetic either way.
DEMO_SEED = 78
COHORT_SIZE = 60
COHORT_WEEKS = 8
EXAM_WEEKS = (7, 8)          # semester exams in weeks 7-8 of the demo term
WEEKLY_CHECKIN_RATE = 0.7    # assumption: ~70% of opted-in students check in each week
CONTACT_OPT_IN_RATE = 0.2    # assumption: ~1 in 5 opt in to "a counsellor may contact me"
# Small-cell suppression: any breakdown narrower than the whole cohort hides counts
# below this (a common statistical-disclosure-control rule of thumb).
SMALL_CELL_MIN = 3
DEMO_COUNSELLOR_PIN = "2468"  # demo only - real deployments use the college SSO
DEMO_STUDENT_NAME = "Ananya"
