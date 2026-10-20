"""All tunable constants for PhishGuard live here, with the reasoning behind each.

Nothing in this file is a measured real-world statistic; they are design choices
for a hackathon prototype and can be re-tuned on real data.
"""

# Deterministic seed for the synthetic corpus and the train/test split.
SEED = 2026

# Fraction of the corpus held out for testing (stratified per class).
TEST_FRACTION = 0.25

# Fraction of templates (per class) held out entirely for the harder
# "unseen template" generalisation check.
HELDOUT_TEMPLATE_FRACTION = 0.2

# ---------------------------------------------------------------- Naive Bayes
# Laplace (add-one) smoothing.
NB_ALPHA = 1.0
# Character n-gram lengths taken inside each word ("#kyc#" -> "#ky", "kyc", ...).
CHAR_NGRAM_MIN = 3
CHAR_NGRAM_MAX = 4
# Each word's char n-grams share a total weight of 1 so they do not swamp words.
# NB still double counts correlated evidence (word + bigram + char grams of the
# same word), so its posterior is far too confident.  We divide the log-odds by
# this temperature before the sigmoid.  8 was picked by hand so that a message
# needs several independent scam cues before the text score passes 0.95.
NB_TEMPERATURE = 8.0
# The training corpus is balanced 50/50, so a message with no evidence at all
# would sit at p = 0.5 ("Suspicious").  We swap the balanced training prior for
# an assumed deployment prior: roughly 1 in 5 messages a user bothers to check
# is a scam.  This is an assumption, not a measured statistic - tune it.
NB_DEPLOY_PRIOR = 0.2

# ------------------------------------------------------- Logistic regression
LR_LEARNING_RATE = 0.8
LR_EPOCHS = 900
LR_L2 = 0.002

# ------------------------------------------------------------ Combined score
# Noisy-OR combination: risk = 1 - prod(1 - weight_i * score_i).
# Weights < 1 mean no single soft signal can reach 100 on its own.
W_TEXT = 0.85    # Naive Bayes text probability
W_URL = 0.92     # worst embedded URL (logistic regression)
W_ENTITY = 0.55  # worst phone number / UPI ID heuristic score
# Rule weights are defined per rule in rules.py and enter the noisy-OR directly.

# Verdict thresholds on the 0-100 risk score.
SAFE_BELOW = 35
DANGEROUS_FROM = 65

# ------------------------------------------------------------ Server limits
MAX_INPUT_CHARS = 5000
MAX_BULK_LINES = 200
MAX_BODY_BYTES = 256 * 1024

# --------------------------------------------------------------- Reporting
# India's national cyber-fraud helpline and reporting portal (Govt. of India, I4C).
HELPLINE = "1930"
PORTAL = "cybercrime.gov.in"
# DoT's Sanchar Saathi "Chakshu" facility for reporting suspected fraud calls/SMS.
CHAKSHU = "sancharsaathi.gov.in (Chakshu)"
