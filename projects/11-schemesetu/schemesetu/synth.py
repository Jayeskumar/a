"""Deterministic demo households and a synthetic household generator.

The four demo families are hand-written personas. The generator draws
complete household profiles from an ILLUSTRATIVE correlated model (see
config.py) with a fixed seed - it is for exercising the questionnaire and the
village dashboard, not a statistical picture of any real village.
"""
import random

from . import config

DEMO_HOUSEHOLDS = [
    {
        "id": "demo-farmer",
        "name": {"en": "Murugan & Kavitha", "ta": "முருகன் & கவிதா"},
        "persona": {"en": "Small farmer, 2 acres, son in Class 9", "ta": "சிறு விவசாயி, 2 ஏக்கர், மகன் 9-ஆம் வகுப்பு"},
        "village": config.DEMO_VILLAGE,
        "profile": {
            "rural": True, "land_ha": 1, "cultivates_land": True, "income_tax_payer": False,
            "govt_employee": False, "annual_income": 120000, "ration_card": "PHH",
            "social_category": "OBC", "house_type": "SEMI", "has_toilet": True, "has_lpg": True,
            "adult_woman": True, "woman_head": True, "oldest_age": 59, "widow_age": 0,
            "severe_disability": False, "pregnant_or_lactating": False, "applicant_age": 40,
            "govt_school_girl_in_college": False,
            "govt_school_child_8to12": True, "post_matric_student": False, "willing_manual_work": False,
        },
    },
    {
        "id": "demo-labourer",
        "name": {"en": "Selvi", "ta": "செல்வி"},
        "persona": {"en": "Landless farm labourer, hut, daughter-in-law expecting", "ta": "நிலமற்ற விவசாயத் தொழிலாளி, குடிசை வீடு, மருமகள் கர்ப்பிணி"},
        "village": config.DEMO_VILLAGE,
        "profile": {
            "rural": True, "land_ha": 0, "cultivates_land": False, "income_tax_payer": False,
            "govt_employee": False, "annual_income": 120000, "ration_card": "AAY",
            "social_category": "SC", "house_type": "KUTCHA", "has_toilet": False, "has_lpg": False,
            "adult_woman": True, "woman_head": True, "oldest_age": 59, "widow_age": 0,
            "severe_disability": False, "pregnant_or_lactating": True, "applicant_age": 40,
            "govt_school_girl_in_college": False,
            "govt_school_child_8to12": False, "post_matric_student": False, "willing_manual_work": True,
        },
    },
    {
        "id": "demo-widow",
        "name": {"en": "Lakshmi Ammal", "ta": "லட்சுமி அம்மாள்"},
        "persona": {"en": "Widow, 66, lives alone", "ta": "கைம்பெண், 66 வயது, தனியாக வசிக்கிறார்"},
        "village": config.DEMO_VILLAGE,
        "profile": {
            "rural": True, "land_ha": 0, "cultivates_land": False, "income_tax_payer": False,
            "govt_employee": False, "annual_income": 120000, "ration_card": "PHH",
            "social_category": "OBC", "house_type": "SEMI", "has_toilet": True, "has_lpg": True,
            "adult_woman": True, "woman_head": True, "oldest_age": 69, "widow_age": 79,
            "severe_disability": False, "pregnant_or_lactating": False, "applicant_age": 70,
            "govt_school_girl_in_college": False,
            "govt_school_child_8to12": False, "post_matric_student": False, "willing_manual_work": False,
        },
    },
    {
        "id": "demo-students",
        "name": {"en": "Ravi & Meena", "ta": "ரவி & மீனா"},
        "persona": {"en": "Tenant farmer; daughter in college, son in Class 10", "ta": "குத்தகை விவசாயி; மகள் கல்லூரியில், மகன் 10-ஆம் வகுப்பு"},
        "village": config.DEMO_VILLAGE,
        "profile": {
            "rural": True, "land_ha": 0, "cultivates_land": True, "income_tax_payer": False,
            "govt_employee": False, "annual_income": 250000, "ration_card": "PHH",
            "social_category": "SC", "house_type": "SEMI", "has_toilet": True, "has_lpg": True,
            "adult_woman": True, "woman_head": True, "oldest_age": 59, "widow_age": 0,
            "severe_disability": False, "pregnant_or_lactating": False, "applicant_age": 50,
            "govt_school_girl_in_college": True,
            "govt_school_child_8to12": True, "post_matric_student": True, "willing_manual_work": False,
        },
    },
]

NAMES = [
    ("Arumugam", "ஆறுமுகம்"), ("Valli", "வள்ளி"), ("Senthil", "செந்தில்"), ("Saraswathi", "சரஸ்வதி"),
    ("Palanisamy", "பழனிசாமி"), ("Parvathi", "பார்வதி"), ("Kannan", "கண்ணன்"), ("Malar", "மலர்"),
    ("Ganesan", "கணேசன்"), ("Sumathi", "சுமதி"), ("Muthu", "முத்து"), ("Revathi", "ரேவதி"),
    ("Velu", "வேலு"), ("Jaya", "ஜெயா"), ("Chinnasamy", "சின்னசாமி"), ("Rani", "ராணி"),
    ("Ponnusamy", "பொன்னுசாமி"), ("Devi", "தேவி"), ("Mariappan", "மாரியப்பன்"), ("Amudha", "அமுதா"),
    ("Subramani", "சுப்பிரமணி"), ("Kamala", "கமலா"), ("Ramasamy", "ராமசாமி"), ("Selvam", "செல்வம்"),
    ("Karuppan", "கருப்பன்"), ("Pushpa", "புஷ்பா"), ("Thangaraj", "தங்கராஜ்"), ("Vasantha", "வசந்தா"),
]


INITIALS = [("K", "க"), ("M", "ம"), ("S", "ச"), ("P", "ப"), ("R", "ர"), ("A", "அ"), ("V", "வ"), ("T", "த")]


def _pick(rng, dist):
    r = rng.random()
    acc = 0.0
    for v, p in dist:
        acc += p
        if r < acc:
            return v
    return dist[-1][0]


def synth_profile(rng):
    """One complete household profile from the illustrative model."""
    p = {}
    p["rural"] = rng.random() < config.P_RURAL
    p["land_ha"] = _pick(rng, config.LAND_DIST_RURAL if p["rural"] else config.LAND_DIST_URBAN)
    if p["land_ha"] > 0:
        p["cultivates_land"] = rng.random() < 0.92
    else:
        p["cultivates_land"] = p["rural"] and rng.random() < config.P_TENANT_IF_LANDLESS_RURAL
    p["govt_employee"] = rng.random() < config.P_GOVT_EMPLOYEE
    # income band index: poorer for landless rural, richer with land / govt job
    base = [0.42, 0.33, 0.12, 0.08, 0.05]
    if p["govt_employee"]:
        base = [0.02, 0.13, 0.25, 0.30, 0.30]
    elif p["land_ha"] >= 2:
        base = [0.15, 0.30, 0.25, 0.18, 0.12]
    elif not p["rural"]:
        base = [0.25, 0.35, 0.18, 0.12, 0.10]
    band = _pick(rng, list(enumerate(base)))
    p["annual_income"] = config.INCOME_BANDS[band]
    p["income_tax_payer"] = (band >= 4 and rng.random() < 0.7) or (band == 3 and rng.random() < 0.25) \
        or (p["govt_employee"] and band >= 2 and rng.random() < 0.6)
    if band == 0:
        rc = [("AAY", 0.22), ("PHH", 0.68), ("NPHH", 0.07), ("NONE", 0.03)]
    elif band == 1:
        rc = [("AAY", 0.05), ("PHH", 0.60), ("NPHH", 0.31), ("NONE", 0.04)]
    else:
        rc = [("AAY", 0.01), ("PHH", 0.20), ("NPHH", 0.72), ("NONE", 0.07)]
    p["ration_card"] = _pick(rng, rc)
    p["social_category"] = _pick(rng, [("SC", 0.21), ("ST", 0.02), ("OBC", 0.68), ("GEN", 0.09)])
    if band == 0:
        ht = [("HOUSELESS", 0.06), ("KUTCHA", 0.34), ("SEMI", 0.35), ("PUCCA", 0.25)]
    elif band == 1:
        ht = [("HOUSELESS", 0.02), ("KUTCHA", 0.14), ("SEMI", 0.38), ("PUCCA", 0.46)]
    else:
        ht = [("HOUSELESS", 0.01), ("KUTCHA", 0.03), ("SEMI", 0.21), ("PUCCA", 0.75)]
    p["house_type"] = _pick(rng, ht)
    p_toilet = {"HOUSELESS": 0.2, "KUTCHA": 0.5, "SEMI": 0.85, "PUCCA": 0.96}[p["house_type"]]
    p["has_toilet"] = rng.random() < p_toilet
    p["has_lpg"] = rng.random() < (0.72 if band == 0 else 0.92)
    p["adult_woman"] = rng.random() < 0.97
    p["oldest_age"] = _pick(rng, [(59, 0.55), (69, 0.26), (79, 0.15), (85, 0.04)])
    widow = rng.random() < (0.10 if p["oldest_age"] == 59 else 0.30)
    if widow and p["adult_woman"]:
        # a widow's age band cannot start above the oldest member's age
        lower = {39: 18, 59: 40, 79: 60, 85: 80}
        bands = [(b, w) for b, w in [(39, 0.1), (59, 0.35), (79, 0.45), (85, 0.10)]
                 if lower[b] <= p["oldest_age"]]
        tot = sum(w for _, w in bands)
        p["widow_age"] = _pick(rng, [(b, w / tot) for b, w in bands])
    else:
        p["widow_age"] = 0
    p["woman_head"] = p["adult_woman"] and (p["widow_age"] > 0 or rng.random() < config.P_WOMAN_HEAD)
    p["severe_disability"] = rng.random() < 0.04
    p["pregnant_or_lactating"] = p["adult_woman"] and rng.random() < 0.08
    if p["oldest_age"] >= 79 and rng.random() < 0.5:
        p["applicant_age"] = _pick(rng, [(70, 0.6), (75, 0.4)])
    else:
        p["applicant_age"] = _pick(rng, [(40, 0.45), (50, 0.27), (70, 0.26), (75, 0.02)])
    p["govt_school_girl_in_college"] = rng.random() < 0.10
    p["govt_school_child_8to12"] = rng.random() < 0.24
    p["post_matric_student"] = p["govt_school_girl_in_college"] or rng.random() < 0.12
    p["willing_manual_work"] = p["rural"] and rng.random() < (0.65 if band <= 1 else 0.12)
    return p


def population(n, seed):
    rng = random.Random(seed)
    return [synth_profile(rng) for _ in range(n)]


def village_households(n=config.VILLAGE_SIZE, seed=config.VILLAGE_SEED, village=config.DEMO_VILLAGE):
    """Synthetic households for the field-worker demo village (rural only).

    Returns dicts with id, name, village, profile and a seeded application
    history (some eligible schemes already applied / received) so the
    "unclaimed benefits" dashboard has something realistic to show.
    """
    rng = random.Random(seed)
    out = []
    i = 0
    while len(out) < n:
        prof = synth_profile(rng)
        if not prof["rural"]:
            continue
        en, ta = NAMES[i % len(NAMES)]
        ien, ita = INITIALS[i % len(INITIALS)]
        i += 1
        out.append({
            "id": "v%03d" % len(out),
            "name": {"en": "%s. %s family" % (ien, en), "ta": "%s. %s குடும்பம்" % (ita, ta)},
            "village": village,
            "profile": prof,
            "seed_uptake": rng.random(),  # used to decide which eligible schemes are already claimed
        })
    return out


def main():
    """Write the deterministic demo data files to data/ (also regenerated in code on demand)."""
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(here, "data")
    files = {
        "demo_households.json": {"_comment": "Hand-written demo personas (see schemesetu/synth.py).",
                                 "households": DEMO_HOUSEHOLDS},
        "demo_village.json": {"_comment": "Synthetic demo village, seed %d - illustrative, not census data." % config.VILLAGE_SEED,
                              "households": village_households()},
        "synthetic_sample.json": {"_comment": "First 50 households of the evaluation population (seed %d)." % config.EVAL_SEED,
                                  "households": population(50, config.EVAL_SEED)},
    }
    for name, obj in files.items():
        with open(os.path.join(data, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print("wrote data/" + name)


if __name__ == "__main__":
    main()
