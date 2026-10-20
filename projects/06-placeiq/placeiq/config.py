"""All tunable assumptions for PlaceIQ live here, in one place.

Nothing in this file is a real-world statistic. The synthetic data model and the
effort costs are illustrative, chosen to be plausible for an Indian engineering
college placement season; every number is a named constant so a placement cell
can replace it with its own experience.
"""

# ----------------------------------------------------------------------------
# Dataset schema
# ----------------------------------------------------------------------------
DEPARTMENTS = ["CSE", "AI&DS", "CSD", "IT", "ECE", "MECH"]

# Aliases accepted in uploaded CSVs (compared after upper-casing and removing spaces).
DEPT_ALIASES = {
    "CSE": "CSE", "CS": "CSE", "COMPUTERSCIENCE": "CSE",
    "AI&DS": "AI&DS", "AIDS": "AI&DS", "AI-DS": "AI&DS", "AIANDDS": "AI&DS",
    "CSD": "CSD", "CSBS": "CSD",
    "IT": "IT", "INFORMATIONTECHNOLOGY": "IT",
    "ECE": "ECE", "EC": "ECE",
    "MECH": "MECH", "ME": "MECH", "MECHANICAL": "MECH",
}

# Numeric model features: (column, label, min, max, is_integer)
FEATURES = [
    ("cgpa", "CGPA", 0.0, 10.0, False),
    ("tenth_pct", "10th %", 0.0, 100.0, False),
    ("twelfth_pct", "12th %", 0.0, 100.0, False),
    ("backlogs", "Backlogs", 0, 40, True),
    ("internships", "Internships", 0, 20, True),
    ("projects", "Projects", 0, 50, True),
    ("certifications", "Certifications", 0, 50, True),
    ("coding_problems", "Coding problems solved", 0, 5000, True),
    ("hackathons", "Hackathons", 0, 50, True),
    ("aptitude_score", "Aptitude score", 0.0, 100.0, False),
    ("communication_score", "Communication score", 0.0, 100.0, False),
    ("mock_interview_score", "Mock interview score", 0.0, 100.0, False),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
FEATURE_LABELS = {f[0]: f[1] for f in FEATURES}
FEATURE_RANGES = {f[0]: (f[2], f[3]) for f in FEATURES}
INTEGER_FEATURES = {f[0] for f in FEATURES if f[4]}

ID_COLUMNS = ["student_id", "name", "dept", "batch"]
TARGET_COLUMNS = ["placed", "package_lpa"]
ALL_COLUMNS = ID_COLUMNS + FEATURE_NAMES + TARGET_COLUMNS
REQUIRED_COLUMNS = ["dept"] + FEATURE_NAMES + ["placed"]  # others optional on upload

# ----------------------------------------------------------------------------
# Modelling
# ----------------------------------------------------------------------------
SEED = 2026                 # fixed seed: same dataset, same split, same model every run
N_STUDENTS = 600
TEST_FRACTION = 0.25        # hold-out share for honest metrics
CV_FOLDS = 5                # out-of-fold predictions for the fairness check
LOGREG_LR = 0.5             # gradient-descent step size on standardised features
LOGREG_L2 = 0.01            # L2 penalty (lambda); small: 12 features, 450 rows
LOGREG_MAX_ITER = 3000
LOGREG_TOL = 1e-6           # stop when max |gradient| falls below this
RIDGE_PACKAGE = 1.0         # ridge penalty for the package regression (normal equations)
MIN_TRAIN_ROWS = 40         # refuse to train on fewer valid rows than this

# ----------------------------------------------------------------------------
# Explainability / counterfactuals
# ----------------------------------------------------------------------------
TARGET_PROBABILITY = 0.70   # "what to fix next" aims to lift P(placed) above this
DEFAULT_RISK_THRESHOLD = 0.50

# Actionable levers: column -> (step, max_total_change, effort_per_step_weeks, verb)
# Effort is a rough "weeks of focused part-time work" per step - an assumption,
# not a measurement. 10th/12th marks are history and are never suggested.
ACTIONS = {
    "coding_problems": (40, 400, 2.0, "Solve {n} more coding problems"),
    "projects": (1, 3, 4.0, "Build {n} more project(s)"),
    "internships": (1, 2, 8.0, "Do {n} more internship(s)"),
    "certifications": (1, 3, 3.0, "Earn {n} more certification(s)"),
    "hackathons": (1, 3, 2.0, "Take part in {n} more hackathon(s)"),
    "backlogs": (-1, -40, 4.0, "Clear {n} backlog(s)"),
    "aptitude_score": (5, 20, 2.5, "Raise aptitude score by {n}"),
    "communication_score": (5, 20, 3.0, "Raise communication score by {n}"),
    "mock_interview_score": (5, 25, 2.0, "Raise mock-interview score by {n}"),
    "cgpa": (0.2, 0.6, 8.0, "Raise CGPA by {n}"),
}
COUNTERFACTUAL_MAX_EXPANSIONS = 6000  # uniform-cost search budget, then greedy fallback

# ----------------------------------------------------------------------------
# Clustering
# ----------------------------------------------------------------------------
DEFAULT_K = 4
CLUSTER_FEATURES = [
    "cgpa", "backlogs", "internships", "projects", "coding_problems",
    "hackathons", "aptitude_score", "communication_score", "mock_interview_score",
]
