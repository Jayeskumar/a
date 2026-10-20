"""Per-student explanations and the counterfactual "what to fix next" planner.

Contribution of feature j (in log-odds) = w_j * z_j, where z_j is the student's
standardised value. Because the model is linear in log-odds, these contributions
add up exactly: logit = b + sum_j w_j z_j, so the bar chart is a faithful
decomposition of the prediction, relative to an average student (z = 0).

Counterfactual search
---------------------
Each actionable lever j (config.ACTIONS) can be applied s_j = 0..S_j times; one step
changes the logit by g_j = w_j * step_j / std_j and costs e_j weeks of effort.
We want the plan with the *smallest total effort* such that
    sigmoid(logit + sum_j s_j g_j) >= target.
Only levers that help (g_j > 0) are considered. Because the logit is additive this
is a bounded multiple-choice knapsack, which we solve *exactly* by dynamic
programming over effort budgets in half-week units: best[c] = largest achievable
logit gain using exactly budget c. The answer is the smallest c whose gain clears
the required margin. Ties are broken by larger gain.
"""

import math

from . import config as C
from .models import sigmoid

HALF_WEEK = 0.5


def contributions(model, scaler, x, names=C.FEATURE_NAMES):
    z = scaler.transform_row(x)
    out = []
    for name, wj, zj, xv in zip(names, model.w, z, x):
        out.append({"feature": name, "label": C.FEATURE_LABELS.get(name, name), "value": xv,
                    "z": zj, "contribution": wj * zj})
    out.sort(key=lambda d: -abs(d["contribution"]))
    return out


def _levers(model, scaler, x, names):
    pos = {n: i for i, n in enumerate(names)}
    levers = []
    for feat, (step, max_total, effort, verb) in C.ACTIONS.items():
        if feat not in pos:
            continue
        j = pos[feat]
        gain = model.w[j] * step / scaler.std[j]
        if gain <= 1e-9:
            continue  # this lever would not raise P(placed) under the current model
        lo, hi = C.FEATURE_RANGES[feat]
        cur = x[j]
        if step > 0:
            room = min(max_total, hi - cur)
        else:
            room = max(max_total, lo - cur)  # both negative
        max_steps = int(math.floor(room / step + 1e-9))
        if max_steps <= 0:
            continue
        units = max(1, int(round(effort / HALF_WEEK)))
        levers.append({"feature": feat, "index": j, "step": step, "gain": gain, "units": units,
                       "max_steps": max_steps, "verb": verb, "effort": units * HALF_WEEK})
    return levers


def _fmt_change(feat, amount):
    if feat == "cgpa":
        return "%.1f" % abs(amount)
    if isinstance(amount, float) and amount != int(amount):
        return "%.1f" % abs(amount)
    return "%d" % abs(int(round(amount)))


def _action(lv, steps, x):
    change = lv["step"] * steps
    cur = x[lv["index"]]
    new = cur + change
    if lv["feature"] == "cgpa":
        new = round(new, 2)
    return {
        "feature": lv["feature"],
        "label": C.FEATURE_LABELS[lv["feature"]],
        "from": cur, "to": new, "change": round(change, 2), "steps": steps,
        "text": lv["verb"].format(n=_fmt_change(lv["feature"], change)),
        "effort_weeks": steps * lv["effort"],
        "logit_gain": steps * lv["gain"],
    }


def counterfactual(model, scaler, x, target=C.TARGET_PROBABILITY, names=C.FEATURE_NAMES):
    """Return the minimum-effort plan that lifts P(placed) to >= target."""
    target = min(max(float(target), 0.01), 0.99)
    base_logit = model.decision(scaler.transform_row(x))
    p0 = sigmoid(base_logit)
    need = math.log(target / (1 - target)) - base_logit
    levers = _levers(model, scaler, x, names)
    result = {"p_before": p0, "target": target, "levers_considered": [l["feature"] for l in levers]}

    alternatives = []
    for lv in levers:  # single-lever options, ranked by effort
        if need <= 0:
            break
        s = int(math.ceil(need / lv["gain"] - 1e-12))
        if s <= lv["max_steps"]:
            a = _action(lv, s, x)
            a["p_after"] = sigmoid(base_logit + a["logit_gain"])
            alternatives.append(a)
    alternatives.sort(key=lambda a: (a["effort_weeks"], -a["p_after"]))
    result["single_lever_options"] = alternatives

    if need <= 0:
        result.update({"reachable": True, "already_above": True, "actions": [],
                       "p_after": p0, "total_effort_weeks": 0.0})
        result["boosters"] = _boosters(levers, x, base_logit)
        return result

    # Exact DP: best[c] = (gain, steps-per-lever) using total budget c half-weeks.
    max_budget = sum(l["units"] * l["max_steps"] for l in levers)
    NEG = float("-inf")
    best = [NEG] * (max_budget + 1)
    best[0] = 0.0
    choice = []  # choice[i][c] = steps of lever i used to reach budget c
    for lv in levers:
        new = [NEG] * (max_budget + 1)
        pick = [0] * (max_budget + 1)
        for c in range(max_budget + 1):
            if best[c] == NEG:
                continue
            for s in range(lv["max_steps"] + 1):
                cc = c + s * lv["units"]
                if cc > max_budget:
                    break
                g = best[c] + s * lv["gain"]
                if g > new[cc] + 1e-12:
                    new[cc], pick[cc] = g, s
        choice.append((pick, best))
        best = new
    found = None
    for c in range(max_budget + 1):
        if best[c] >= need - 1e-12:
            found = c
            break
    reachable = found is not None
    if not reachable:  # report the strongest plan possible within the levers' limits
        found = max(range(max_budget + 1), key=lambda c: (best[c], -c))
    # Backtrack
    steps = [0] * len(levers)
    c = found
    for i in range(len(levers) - 1, -1, -1):
        pick, _ = choice[i]
        s = pick[c]
        steps[i] = s
        c -= s * levers[i]["units"]
    actions = [_action(lv, s, x) for lv, s in zip(levers, steps) if s > 0]
    # Order by effort (cheapest first) and show the cumulative probability staircase.
    actions.sort(key=lambda a: (a["effort_weeks"], -a["logit_gain"]))
    run = base_logit
    for a in actions:
        run += a["logit_gain"]
        a["p_after"] = sigmoid(run)
    result.update({
        "reachable": reachable, "already_above": False, "actions": actions,
        "p_after": sigmoid(base_logit + sum(a["logit_gain"] for a in actions)),
        "total_effort_weeks": sum(a["effort_weeks"] for a in actions),
    })
    return result


def _boosters(levers, x, base_logit):
    """For students already above target: one step of each lever, best gain/effort first."""
    out = []
    for lv in levers:
        a = _action(lv, 1, x)
        a["p_after"] = sigmoid(base_logit + a["logit_gain"])
        out.append(a)
    out.sort(key=lambda a: -a["logit_gain"] / a["effort_weeks"])
    return out[:4]


def top_gap(plan):
    """The single most impactful fix in a plan (largest logit gain)."""
    acts = plan.get("actions") or plan.get("boosters") or []
    if not acts:
        return None
    return max(acts, key=lambda a: a["logit_gain"])
