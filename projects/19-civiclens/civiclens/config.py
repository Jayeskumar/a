"""Every tunable assumption of CivicLens lives here, with the reason for its value.

Nothing in this file is a real-world statistic. The town, its wards, complaint volumes,
SLA targets and resolution speeds are *demo assumptions* chosen to look like a mid-sized
Tamil Nadu municipality; change them to match your own citizen charter and data.
"""

# ----------------------------------------------------------------------------- data stream
SEED = 2026                      # every random draw in the generator derives from this
START_DATE = "2026-07-20"        # Monday; 13 full weeks of history
N_WEEKS = 13
N_DAYS = N_WEEKS * 7             # 91 days, i.e. ~3 months
NOW_HOUR = 20.0                  # the dashboard "clock" is the last day at 20:00
BACKGROUND_INCIDENTS_PER_DAY = 18.0   # tuned so the stream has ~3,000 complaints with duplicates
DOW_FACTOR = [1.30, 1.10, 1.0, 1.0, 0.95, 0.85, 0.80]   # Mon..Sun filing volume (Monday catch-up)
MONSOON_FROM_WEEK = 9            # NE-monsoon onset is roughly mid-October in TN (approx.)
MONSOON_DRAINAGE_FACTOR = 1.6    # extra drainage / stagnant-water complaints once rains start

# ----------------------------------------------------------------------------- the town
# A synthetic 5 x 4 grid of 1 km wards. Coordinates are only approximately those of a
# Namakkal-district town so the map looks plausible; no real ward boundaries are implied.
TOWN_NAME = "Demo Municipality"
ORIGIN_LAT = 11.3620             # south-west corner (approx.)
ORIGIN_LON = 77.8720
GRID_COLS = 5
GRID_ROWS = 4
WARD_KM = 1.0
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON = 109.02          # 111.32 * cos(11.37 deg)

# ----------------------------------------------------------------------------- departments
# code, display name, share of background complaints, assumed SLA target (days),
# assumed median resolution (days) before ward / backlog / weekday / priority effects.
DEPARTMENTS = [
    ("ROADS", "Roads & Potholes", 0.150, 7, 4.6),
    ("SANITATION", "Sanitation & Garbage", 0.220, 2, 1.25),
    ("STREETLIGHT", "Streetlights & Electrical", 0.160, 3, 1.9),
    ("WATER", "Water Supply", 0.140, 2, 1.25),
    ("DRAINAGE", "Drainage & Sewerage", 0.130, 3, 1.9),
    ("ANIMAL", "Animal Control", 0.070, 5, 3.0),
    ("HOSTEL", "Hostel & Campus", 0.050, 3, 1.6),
    ("OTHER", "General / Other", 0.080, 10, 6.0),
]
DEPT_CODES = [d[0] for d in DEPARTMENTS]
DEPT_NAME = {d[0]: d[1] for d in DEPARTMENTS}
DEPT_SHARE = {d[0]: d[2] for d in DEPARTMENTS}
SLA_DAYS = {d[0]: d[3] for d in DEPARTMENTS}
MEDIAN_RES_DAYS = {d[0]: d[4] for d in DEPARTMENTS}

RES_SIGMA = 0.55                 # log-normal spread of resolution times
PRIORITY_SPEED = {1: 0.40, 2: 0.65, 3: 1.0, 4: 1.45}   # P1 handled ~2.5x faster (assumed)
WEEKEND_SLOWDOWN = [1.0, 1.0, 1.0, 1.05, 1.30, 1.35, 1.15]  # filed Mon..Sun; Fri/Sat wait over the weekend
BACKLOG_REF = 18                 # backlog (open incidents in dept) at which work slows noticeably
BACKLOG_EXPONENT = 0.55          # resolution multiplier = (1 + backlog / BACKLOG_REF) ** exponent
NEVER_FIXED_RATE = 0.025         # share of incidents that fall through the cracks (x4 slower)

LANG_MIX = [("en", 0.42), ("ta", 0.25), ("tg", 0.33)]    # English, Tamil script, Tanglish
CHANNELS = [("App", 0.40), ("Call centre", 0.22), ("WhatsApp", 0.18), ("Social media", 0.12), ("Walk-in", 0.08)]
CALL_CENTRE_ENGLISH = 0.80       # operators mostly type call-centre complaints in English
TYPO_RATE = 0.20                 # share of Latin-script complaints with 1-2 typos
SECONDARY_RATE = 0.06            # complaints that also mention a minor problem of another department
VAGUE_RATE = 0.04                # complaints that barely say what is wrong ("problem near X, no action")
HIDDEN_SEVERITY_RATE = 0.06      # true urgency shifted by context the text does not contain

# duplicates: how many *extra* reports an incident attracts (index = extra count)
DUP_EXTRA_PROBS_NORMAL = [0.70, 0.17, 0.08, 0.03, 0.02]
DUP_EXTRA_PROBS_URGENT = [0.52, 0.24, 0.13, 0.07, 0.04]
DUP_MEAN_DELAY_DAYS = 0.8        # reporters follow up within about a day
DUP_MAX_DELAY_DAYS = 4.0
DUP_JITTER_M = 45                # reporter GPS scatter around the incident
DUP_SAME_PLACE_PHRASE = 0.85     # duplicate names the same landmark / street

# ----------------------------------------------------------------------------- features & models
CHAR_NGRAMS = (3, 4)             # grapheme n-grams inside word boundaries
MIN_DF = 2
# word, grapheme-n-gram and concept blocks of the TF-IDF vector. Chosen by accuracy on *unseen complaint
# templates* in two validation towns (seeds 2027/2028): heavy char weight memorises template strings.
BLOCK_WEIGHTS = {"w": 0.7, "c": 0.3, "k": 1.0}
NB_ALPHA = 0.3
LR_EPOCHS = 6
LR_RATE = 0.6
LR_L2 = 2e-5
TEST_FRACTION = 0.2              # hold-out share, split by incident so duplicates never leak

# ----------------------------------------------------------------------------- urgency
PRIORITY_LABELS = {1: "P1 Critical", 2: "P2 High", 3: "P3 Normal", 4: "P4 Low"}
PRIORITY_TARGET_HOURS = {1: 12, 2: 48}   # informational, shown next to the badge

# ----------------------------------------------------------------------------- duplicates
MINHASH_PERM = 64
LSH_BANDS = 32                   # 32 bands x 2 rows -> S-curve threshold ~ (1/32)^(1/2) = 0.18 (recall first;
LSH_ROWS = 2                     # the geo cell in the bucket key keeps the candidate list short)
DUP_GEO_CELL_M = 300.0           # LSH buckets are per ~300 m cell; queries look at the 3 x 3 neighbourhood
DUP_MAX_DIST_M = 300.0
DUP_MAX_GAP_DAYS = 5.0
DUP_MIN_JACCARD = 0.15           # below this the texts share almost nothing
DUP_SCORE_WEIGHTS = (0.50, 0.30, 0.20)   # hand-set fallback scorer: text Jaccard, geo closeness, time closeness
DUP_SCORE_THRESHOLD = 0.55       # fallback threshold; the engine learns a pair scorer + threshold instead

# ----------------------------------------------------------------------------- hotspots
HOTSPOT_DEPTS = [d for d in DEPT_CODES if d != "HOSTEL"]   # campus issues cluster at buildings by design
DBSCAN_EPS_M = 100.0             # eps / minPts chosen on two *other* synthetic towns (seeds 2027, 2028)
DBSCAN_MIN_PTS = 9               # by bench.py, then scored on this one: >= 9 incidents within 100 m
HOTSPOT_MATCH_M = 250.0          # detected centroid within this of a planted centre = hit
EMERGING_BASELINE_WEEKS = 4
EMERGING_Z = 3.0
EMERGING_MIN_COUNT = 5
EMERGING_LAMBDA_FLOOR = 0.5      # keeps z finite for wards with an empty baseline

# ----------------------------------------------------------------------------- SLA
SURVIVAL_MAX_DAYS = 21
BREACH_EPOCHS = 30
BREACH_RATE = 0.15
BREACH_L2 = 1e-3
BREACH_TEST_WEEKS = 3            # time-based hold-out: the last 3 weeks with known outcomes
AT_RISK_THRESHOLD = 0.5

# ----------------------------------------------------------------------------- topics
TOPIC_K_RANGE = (3, 8)
TOPIC_RESTARTS = 4
