"""Benefit estimator: add up fixed amounts only; everything else is "varies".

* annual   - recurring cash with a stated amount (tiers chosen by rule)
* one_time - a stated one-off grant (house, toilet, maternity)
* cover    - insurance cover; listed, never added to cash totals
* future   - pension payable later (e.g. after age 60); listed only
* varies   - no fixed amount (loans, wages, claims, fee waivers)

Schemes sharing an `exclusive_group` (one social-security pension per person)
are counted once, using the largest amount. `conditional` amounts (paid only
after a selection exam) are reported separately from the guaranteed total.
"""
from . import rules


def scheme_amount(scheme, profile, params=None):
    b = scheme["benefit"]
    amount = b.get("amount")
    for t in b.get("tiers", []):
        if rules.status_of(t["when"], profile, params) == rules.PASS:
            amount = t["amount"]
            break
    return amount


def estimate(results, catalogue, profile):
    """results: iterable of {"id", "status"} with status eligible/possibly/not_eligible."""
    annual, one_time, conditional, covers, future, varies = [], [], [], [], [], []
    potential = []
    groups = {}
    for r in results:
        s = catalogue.by_id[r["id"]]
        kind = s["benefit"]["kind"]
        amt = scheme_amount(s, profile, catalogue.params)
        item = {"id": s["id"], "short": s["short"], "amount": amt, "label": s["benefit"]["label"]}
        if r["status"] == "possibly":
            if kind in ("annual", "one_time") and amt:
                potential.append(dict(item, kind=kind))
            continue
        if r["status"] != "eligible":
            continue
        if kind == "annual":
            if s.get("conditional"):
                conditional.append(item)
            elif s.get("exclusive_group"):
                groups.setdefault(s["exclusive_group"], []).append(item)
            else:
                annual.append(item)
        elif kind == "one_time":
            one_time.append(item)
        elif kind == "cover":
            covers.append(item)
        elif kind == "future":
            future.append(item)
        else:
            varies.append(item)
    not_counted = []
    for g, items in sorted(groups.items()):
        items.sort(key=lambda x: -(x["amount"] or 0))
        annual.append(dict(items[0], note="counted once per person (" + g + ")"))
        for other in items[1:]:
            not_counted.append(dict(other, note="same person cannot draw two social pensions"))
    return {
        "annual_total": sum(i["amount"] or 0 for i in annual),
        "one_time_total": sum(i["amount"] or 0 for i in one_time),
        "conditional_total": sum(i["amount"] or 0 for i in conditional),
        "potential_total": sum(i["amount"] or 0 for i in potential),
        "max_health_cover": max([i["amount"] for i in covers if i["id"] in ("pm_jay", "cmchis")] or [0]),
        "annual": annual, "one_time": one_time, "conditional": conditional,
        "covers": covers, "future": future, "varies": varies,
        "potential": potential, "not_counted": not_counted,
    }
