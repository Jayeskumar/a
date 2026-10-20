"""Deterministic synthetic data: ~300 donors around Salem / Erode / Namakkal districts and
the 5-bank inventory snapshot. Run `python -m bloodlink.dataset` to regenerate data/*.json.

Everything here is synthetic. Names are generic first names + initial; there are no real
people, phone numbers or institutions.
"""
import datetime as dt
import json
import math
import os
import random

from .config import BLOOD_GROUPS, DEMO_NOW, DEMO_TODAY, GROUP_SHARE, N_DONORS, SEED, TOWNS
from .inventory import build_snapshot

MALE = ["Arun", "Karthik", "Vignesh", "Prakash", "Senthil", "Murugan", "Saravanan", "Dinesh",
        "Ramesh", "Suresh", "Gokul", "Naveen", "Bala", "Hari", "Manoj", "Praveen", "Sathish",
        "Vijay", "Ajith", "Selvam", "Ganesh", "Mohan", "Rajesh", "Siva", "Surya", "Velu",
        "Yuvaraj", "Lokesh", "Kavin", "Madhan", "Nithish", "Sanjay", "Tamil", "Elango"]
FEMALE = ["Priya", "Divya", "Kavya", "Lakshmi", "Meena", "Revathi", "Sangeetha", "Anitha",
          "Deepa", "Gayathri", "Keerthana", "Nandhini", "Pavithra", "Sowmya", "Swathi", "Yamuna",
          "Janani", "Abinaya", "Harini", "Indhu", "Vaishnavi", "Mathi"]
INITIALS = "ABCDEGJKLMNPRSTV"

MALE_SHARE = 0.78   # assumption: most registered donors in India are men; synthetic only


def _choice_weighted(rng, items, weights):
    r, acc = rng.random() * sum(weights), 0.0
    for it, w in zip(items, weights):
        acc += w
        if r < acc:
            return it
    return items[-1]


def _group(rng):
    return _choice_weighted(rng, BLOOD_GROUPS, [GROUP_SHARE[g] for g in BLOOD_GROUPS])


def generate_donors(seed=SEED, n=N_DONORS, today=DEMO_TODAY, now=DEMO_NOW):
    rng = random.Random(seed)
    donors = []
    # guarantee a few rare-group donors so every group is demonstrable
    forced = ["O-"] * 6 + ["A-"] * 4 + ["B-"] * 5 + ["AB-"] * 3
    for i in range(n):
        sex = "M" if rng.random() < MALE_SHARE else "F"
        group = forced[i] if i < len(forced) else _group(rng)
        town = _choice_weighted(rng, TOWNS, [t["weight"] for t in TOWNS])
        # scatter ~5 km around the town centre (0.045 deg lat ~ 5 km)
        r = abs(rng.gauss(0, 0.045))
        ang = rng.random() * 2 * math.pi
        lat = round(town["lat"] + r * math.sin(ang), 5)
        lon = round(town["lon"] + r * math.cos(ang) / math.cos(math.radians(town["lat"])), 5)
        u = rng.random()
        if u < 0.45:
            age = rng.randint(18, 25)      # college donors
        elif u < 0.85:
            age = rng.randint(26, 45)
        elif u < 0.98:
            age = rng.randint(46, 65)
        else:
            age = rng.randint(66, 68)      # aged out but still on old lists
        dob = today - dt.timedelta(days=int(age * 365.25 + rng.randint(1, 360)))
        if sex == "M":
            weight = max(43.0, min(105.0, rng.gauss(68, 10)))
        else:
            weight = max(42.0, min(92.0, rng.gauss(56, 8)))
        weight = round(weight, 1)
        if rng.random() < 0.2:
            last = None
            donations = 0
        else:
            ago = rng.randint(5, 119) if rng.random() < 0.35 else rng.randint(120, 520)
            last = today - dt.timedelta(days=ago)
            donations = 1 + min(24, int(rng.expovariate(1 / 3.5)))
        willing = round(rng.betavariate(2.2, 2.8), 3)   # latent, simulator-only
        received = 0 if donations == 0 and rng.random() < 0.5 else rng.randint(0, 14)
        accepted = sum(1 for _ in range(received) if rng.random() < willing)
        if received and rng.random() < 0.55:
            hours = rng.uniform(4, 60 * 24)
            last_contacted = (now - dt.timedelta(hours=hours)).isoformat(timespec="minutes")
        else:
            last_contacted = None
        deferred = None
        if rng.random() < 0.03:
            deferred = (today + dt.timedelta(days=rng.randint(10, 180))).isoformat()
        available = rng.random() > 0.07
        reg = today - dt.timedelta(days=rng.randint(30, 2000))
        if last and last < reg:
            reg = last - dt.timedelta(days=rng.randint(0, 200))
        first = rng.choice(MALE if sex == "M" else FEMALE)
        donors.append({
            "id": "D-%04d" % (i + 1),
            "name": "%s %s." % (first, rng.choice(INITIALS)),
            "sex": sex,
            "dob": dob.isoformat(),
            "weight_kg": weight,
            "group": group,
            "town": town["name"],
            "lat": lat,
            "lon": lon,
            "last_donation": last.isoformat() if last else None,
            "donations": donations,
            "alerts_received": received,
            "alerts_accepted": accepted,
            "last_contacted": last_contacted,
            "available": available,
            "deferred_until": deferred,
            "registered": reg.isoformat(),
            "sim_willingness": willing,
        })
    # shuffle registration order deterministically: ids stay, but the forced rare donors
    # should not all sit at the top of the "first-come" phone list
    order = list(range(n))
    rng.shuffle(order)
    for new_idx, d in zip(order, list(donors)):
        d["list_order"] = new_idx
    return donors


def write_data(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    donors = generate_donors()
    with open(os.path.join(data_dir, "donors.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_for": DEMO_TODAY.isoformat(), "seed": SEED, "donors": donors}, f, indent=1)
    net = build_snapshot(SEED)
    with open(os.path.join(data_dir, "network.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_for": DEMO_TODAY.isoformat(), "seed": SEED, "network": net.to_json()}, f)
    return donors, net


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d, n = write_data(os.path.join(here, "data"))
    print("wrote %d donors and %d stock units" % (len(d), sum(len(v) for v in n.stock.values())))
