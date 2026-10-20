"""Village-level dashboard for field workers: where is support going unclaimed?

A (household, scheme) pair is *unclaimed* when the household is eligible and
its tracker status is still "not_applied". Value of unclaimed support counts
only fixed annual / one-time amounts (same rules as the benefit estimator).
"""
from . import benefits


def dashboard(households, engine, village=None):
    cat = engine.cat
    rows = dict((s["id"], {"id": s["id"], "short": s["short"], "name": s["name"],
                           "category": s["category"], "eligible": 0, "possibly": 0,
                           "applied": 0, "pending": 0, "received": 0, "unclaimed": 0,
                           "unclaimed_annual": 0, "unclaimed_one_time": 0})
                for s in cat.schemes)
    hh_rows = []
    tot = {"households": 0, "eligible_pairs": 0, "unclaimed_pairs": 0, "received_pairs": 0,
           "in_progress_pairs": 0, "unclaimed_annual": 0, "unclaimed_one_time": 0}
    for h in households:
        if village and h["village"] != village:
            continue
        tot["households"] += 1
        statuses = engine.statuses(h["profile"])
        apps = h.get("applications", {})
        unclaimed, unclaimed_val = [], 0
        eligible_n = 0
        for sid, st in statuses.items():
            r = rows[sid]
            if st == "possibly":
                r["possibly"] += 1
                continue
            if st != "eligible":
                continue
            eligible_n += 1
            tot["eligible_pairs"] += 1
            app = (apps.get(sid) or {}).get("status", "not_applied")
            if app in ("applied", "pending", "received"):
                r[app] += 1
                r["eligible"] += 1
                if app == "received":
                    tot["received_pairs"] += 1
                else:
                    tot["in_progress_pairs"] += 1
                continue
            r["eligible"] += 1
            r["unclaimed"] += 1
            tot["unclaimed_pairs"] += 1
            s = cat.by_id[sid]
            amt = benefits.scheme_amount(s, h["profile"], cat.params) or 0
            kind = s["benefit"]["kind"]
            if kind == "annual" and not s.get("conditional"):
                r["unclaimed_annual"] += amt
                tot["unclaimed_annual"] += amt
                unclaimed_val += amt
            elif kind == "one_time":
                r["unclaimed_one_time"] += amt
                tot["unclaimed_one_time"] += amt
            unclaimed.append(sid)
        hh_rows.append({"id": h["id"], "name": h["name"], "village": h["village"],
                        "eligible": eligible_n, "unclaimed": len(unclaimed),
                        "unclaimed_annual": unclaimed_val, "unclaimed_schemes": unclaimed,
                        "received": sum(1 for a in apps.values() if a.get("status") == "received")})
    scheme_rows = [r for r in rows.values() if r["eligible"] or r["possibly"]]
    scheme_rows.sort(key=lambda r: (-r["unclaimed"], -r["unclaimed_annual"], r["id"]))
    hh_rows.sort(key=lambda r: (-r["unclaimed_annual"], -r["unclaimed"], r["id"]))
    claimed = tot["received_pairs"] + tot["in_progress_pairs"]
    tot["claim_rate"] = round(claimed / float(tot["eligible_pairs"]), 3) if tot["eligible_pairs"] else 0.0
    return {"village": village, "totals": tot, "schemes": scheme_rows, "households": hh_rows}
