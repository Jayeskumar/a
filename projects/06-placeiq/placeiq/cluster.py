"""K-means with k-means++ initialisation, plus persona naming from centroid profiles."""

import itertools
import random


def _d2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans_pp_init(X, k, rng):
    """k-means++: first centre uniform, then each next centre with probability
    proportional to squared distance to the nearest chosen centre."""
    centres = [list(X[rng.randrange(len(X))])]
    dist = [_d2(x, centres[0]) for x in X]
    while len(centres) < k:
        total = sum(dist)
        if total == 0:
            centres.append(list(X[rng.randrange(len(X))]))
        else:
            r = rng.random() * total
            acc = 0.0
            pick = len(X) - 1
            for i, d in enumerate(dist):
                acc += d
                if acc >= r:
                    pick = i
                    break
            centres.append(list(X[pick]))
        c = centres[-1]
        dist = [min(d, _d2(x, c)) for d, x in zip(dist, X)]
    return centres


def kmeans(X, k, seed=2026, max_iter=100, n_init=4):
    """Lloyd's algorithm; best of n_init k-means++ restarts by inertia.
    Returns dict(labels, centroids, inertia, iterations)."""
    if k < 1 or k > len(X):
        raise ValueError("k must be between 1 and the number of rows")
    rng = random.Random(seed)
    best = None
    d = len(X[0])
    for _ in range(n_init):
        cents = kmeans_pp_init(X, k, rng)
        labels = [-1] * len(X)
        for it in range(1, max_iter + 1):
            new = [min(range(k), key=lambda c: _d2(x, cents[c])) for x in X]
            changed = new != labels
            labels = new
            for c in range(k):
                members = [X[i] for i, l in enumerate(labels) if l == c]
                if members:
                    cents[c] = [sum(m[j] for m in members) / len(members) for j in range(d)]
                else:  # re-seed an empty cluster at the farthest point
                    far = max(range(len(X)), key=lambda i: _d2(X[i], cents[labels[i]]))
                    cents[c] = list(X[far])
            if not changed:
                break
        inertia = sum(_d2(x, cents[l]) for x, l in zip(X, labels))
        if best is None or inertia < best["inertia"]:
            best = {"labels": labels, "centroids": cents, "inertia": inertia, "iterations": it}
    return best


# Persona templates: (name, description, eligible(z), score(z)) over a centroid profile
# z = z-scores of the cluster means vs. the cohort, plus "_placed" = z of mean P(placed).
# A template that is not eligible scores -100, so a name is only used when it fits.
def _avg(z):
    vals = [v for k, v in z.items() if not k.startswith("_")]
    return sum(vals) / len(vals)


PERSONAS = [
    ("Coding stars", "Heavy coding practice, projects and hackathons - interview-ready on DSA.",
     lambda z: z["coding_problems"] > 0.5,
     lambda z: z["coding_problems"] + z["projects"] + z["hackathons"] + 0.5 * z["internships"]),
    ("Academic toppers lacking projects", "Strong CGPA and aptitude but a thin portfolio - need builds and coding.",
     lambda z: z["cgpa"] > 0.3 and z["projects"] < 0,
     lambda z: z["cgpa"] + 0.5 * z["aptitude_score"] - z["projects"] - 0.7 * z["coding_problems"]),
    ("At risk", "Backlogs, low practice and low mock scores - need intervention now.",
     lambda z: z["_placed"] < -0.3,
     lambda z: -z["_placed"] + z["backlogs"] - 0.5 * z["cgpa"]),
    ("Confident communicators", "Strong communication and mock interviews, average technical depth.",
     lambda z: z["communication_score"] > 0.4 and z["communication_score"] > z["coding_problems"],
     lambda z: z["communication_score"] + z["mock_interview_score"] - 0.5 * z["coding_problems"]),
    ("Quiet builders", "Projects and internships, weaker communication - practise interviews.",
     lambda z: (z["projects"] + z["internships"]) / 2 > 0.3 and z["communication_score"] < 0.2,
     lambda z: z["projects"] + z["internships"] - z["communication_score"]),
    ("Late starters", "Below average across the board but few backlogs - a skills push converts them.",
     lambda z: _avg(z) < -0.2 and z["backlogs"] < 0.5,
     lambda z: -_avg(z) - z["backlogs"]),
    ("Placement-ready achievers", "Above average on academics and interviews - keep them sharp for top offers.",
     lambda z: z["_placed"] > 0.3,
     lambda z: z["_placed"]),
    ("Steady all-rounders", "Close to the cohort average on everything - polish to convert.",
     lambda z: True,
     lambda z: 0.5 - 2.0 * abs(_avg(z))),
]


def name_clusters(profiles):
    """profiles: list of z-score dicts (one per cluster). Returns list of
    (name, description) maximising the total template score (names are unique)."""
    k = len(profiles)
    scores = [[(fn(p) if ok(p) else -100.0) for (_, _, ok, fn) in PERSONAS] for p in profiles]
    best, best_perm = None, None
    for perm in itertools.permutations(range(len(PERSONAS)), k):
        s = sum(scores[c][perm[c]] for c in range(k))
        if best is None or s > best:
            best, best_perm = s, perm
    return [(PERSONAS[i][0], PERSONAS[i][1]) for i in best_perm]
