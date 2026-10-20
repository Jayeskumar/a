"""Tunable constants in one place. Every number here is either a modelling choice
or an ILLUSTRATIVE synthetic-data parameter - none of them are census figures.
"""

# Seeds: priors for the question selector are learnt from one synthetic
# population and the evaluation is run on a different (hold-out) population.
PRIOR_SEED = 7
PRIOR_POPULATION = 2000
EVAL_SEED = 2026
EVAL_POPULATION = 300
VILLAGE_SEED = 11
VILLAGE_SIZE = 36
DEMO_VILLAGE = "Pudhur (demo)"

# Laplace smoothing for answer priors so no answer ever gets probability 0.
PRIOR_SMOOTHING = 1.0

# Question selection strategy used by the API: "ig" (expected information gain,
# summed binary entropy reduction over undecided schemes), "resolve" (expected
# number of schemes decided by the answer) or "static" (question-bank order with
# skip logic). Measured in REPORT.md; "ig" asks the fewest questions on average.
DEFAULT_STRATEGY = "ig"
# Tie-breaker weight: IG score + TIE_WEIGHT * expected schemes resolved.
TIE_WEIGHT = 0.05

APPLICATION_STATUSES = ("not_applied", "applied", "pending", "received")

# --- Illustrative synthetic household model (shape only, NOT real statistics) ---
P_RURAL = 0.85
LAND_DIST_RURAL = [(0, 0.45), (1, 0.30), (2, 0.15), (5, 0.10)]   # hectare bands
LAND_DIST_URBAN = [(0, 0.92), (1, 0.05), (2, 0.02), (5, 0.01)]
P_TENANT_IF_LANDLESS_RURAL = 0.22  # landless families that lease / sharecrop land
P_GOVT_EMPLOYEE = 0.06
INCOME_BANDS = [120000, 250000, 350000, 500000, 1000000]
P_WOMAN_HEAD = 0.65   # TN family cards usually name a woman as head (assumption)
