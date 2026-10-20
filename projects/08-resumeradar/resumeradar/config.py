"""Every tunable assumption lives here, with the reasoning behind it.

None of these numbers are real-world statistics; they are design choices that a
recruiter can inspect and change. The demo results in REPORT.md use these values.
"""
from collections import OrderedDict

# Month used for "Present" / "Current" in date ranges. Fixed (not today's date) so the
# demo scores are reproducible; set to the hackathon month (Oct 2026).
AS_OF_YEAR = 2026
AS_OF_MONTH = 10

# Weighted match score. Must-have skills dominate because they are what the hiring
# manager wrote down as non-negotiable; TF-IDF similarity catches context the skill
# ontology misses; evidence rewards skills shown in real work over skills only listed.
WEIGHTS = OrderedDict([
    ("must_have", 0.40),
    ("nice_to_have", 0.10),
    ("semantic", 0.20),
    ("experience", 0.15),
    ("education", 0.05),
    ("evidence", 0.10),
])

COMPONENT_LABELS = {
    "must_have": "Must-have skills",
    "nice_to_have": "Nice-to-have skills",
    "semantic": "Context similarity (TF-IDF)",
    "experience": "Relevant experience",
    "education": "Education level & field",
    "evidence": "Skills proven in work/projects",
}

# Partial credit when the exact skill is absent.
IMPLIED_CREDIT_DIRECT = 0.8    # e.g. JD wants Python, resume shows Django (Django requires Python)
IMPLIED_CREDIT_INDIRECT = 0.6  # two or more prerequisite hops away
RELATED_CREDIT = 0.4           # same family, e.g. Flask vs Django, Angular vs React

# Importance of a requirement inside the must-have average.
TITLE_SKILL_WEIGHT = 2.0       # skill named in the job title ("Python Backend Developer")
STRONG_CUE_WEIGHT = 1.5        # line says "strong", "expert", "proficient", ...

# TF-IDF cosine at which the context component is considered full (1.0). Calibrated on the
# bundled demo set, where the best resume/JD pairs reach a cosine of about 0.30-0.35.
SEMANTIC_COS_FULL = 0.35

# Internship months count at half weight towards experience (they are real but supervised).
INTERNSHIP_WEIGHT = 0.5

# Recommendation bands (score out of 100). Nobody is auto-rejected: "Low" means
# "send coaching feedback", and a human makes every decision.
SHORTLIST_AT = 75
REVIEW_AT = 55

# In the evidence component a nice-to-have counts half as much as a must-have.
NICE_EVIDENCE_WEIGHT = 0.5

# Keyword-stuffing heuristic: many listed skills but few of the JD skills shown in work.
STUFFING_MIN_SKILLS = 25
STUFFING_MAX_EVIDENCE = 0.25

# Learning plan pacing for students (approx. hours per week alongside college).
HOURS_PER_WEEK = 8

# Request limits for the HTTP API.
MAX_RESUMES = 500
MAX_TEXT_CHARS = 60_000
MAX_BODY_BYTES = 8_000_000
