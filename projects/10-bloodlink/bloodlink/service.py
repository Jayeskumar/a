"""Application service: holds the in-memory demo state and turns logic results into JSON.

No HTTP code here (app.py does that). State lives in memory; the deterministic source data
(data/donors.json, data/network.json) is generated on first run if missing. POST
/api/demo/reset restores the original state.
"""
import copy
import datetime as dt
import json
import os
import threading

from . import compat, config, dataset, inventory, ranking, simulation
from .eligibility import ProfileError, donor_profile, evaluate, parse_date

PUBLIC_DONOR_FIELDS = ("id", "name", "sex", "group", "town", "lat", "lon", "weight_kg", "dob",
                       "last_donation", "donations", "alerts_received", "alerts_accepted",
                       "last_contacted", "available", "deferred_until", "registered")


class NotFound(Exception):
    pass


class BadRequest(ValueError):
    pass


def _day_iso(day):
    return (config.DEMO_TODAY + dt.timedelta(days=int(day))).isoformat()


class Service:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.lock = threading.RLock()          # guards mutable demo state
        self.cache_lock = threading.Lock()     # guards slow, cached analytics on pristine data
        self._eval_cache = {}
        self._month_cache = None
        self._backtest = None
        self._load()

    # ---------------------------------------------------------------- state
    def _load(self):
        dpath = os.path.join(self.data_dir, "donors.json")
        npath = os.path.join(self.data_dir, "network.json")
        if not (os.path.exists(dpath) and os.path.exists(npath)):
            dataset.write_data(self.data_dir)
        with open(dpath, encoding="utf-8") as f:
            self.base_donors = json.load(f)["donors"]
        with open(npath, encoding="utf-8") as f:
            self.base_net = inventory.Network.from_json(json.load(f)["network"])
        self.reset()

    def reset(self):
        with self.lock:
            self.donors = copy.deepcopy(self.base_donors)
            self.by_id = {d["id"]: d for d in self.donors}
            self.net = self.base_net.clone()
            self.activity = []
            self.now = config.DEMO_NOW
            return {"ok": True, "donors": len(self.donors),
                    "units": sum(len(v) for v in self.net.stock.values())}

    # ---------------------------------------------------------------- meta
    def meta(self):
        c = config
        return {
            "product": "BloodLink",
            "tagline": "Find the right blood donor in minutes, not hours",
            "disclaimer": c.DISCLAIMER,
            "demo_today": c.DEMO_TODAY.isoformat(),
            "demo_now": c.DEMO_NOW.isoformat(timespec="minutes"),
            "groups": c.BLOOD_GROUPS,
            "urgencies": c.URGENCIES,
            "hospitals": c.HOSPITALS,
            "banks": [{k: b[k] for k in ("id", "name", "town", "lat", "lon", "demand_per_day")} for b in c.BANKS],
            "towns": [{k: t[k] for k in ("name", "lat", "lon")} for t in c.TOWNS] + c.MAP_LABELS,
            "donor_count": len(self.donors),
            "constants": self.constants(),
            "compatibility": self.compatibility(),
        }

    def constants(self):
        c = config
        return [
            {"group": "Eligibility (verify)", "name": "Age", "value": "%d-%d years" % (c.AGE_MIN, c.AGE_MAX), "source": c.ELIGIBILITY_SOURCE},
            {"group": "Eligibility (verify)", "name": "Minimum weight", "value": "%g kg" % c.WEIGHT_MIN_KG, "source": c.ELIGIBILITY_SOURCE},
            {"group": "Eligibility (verify)", "name": "Whole-blood interval", "value": "%d days men / %d days women" % (c.MIN_INTERVAL_DAYS["M"], c.MIN_INTERVAL_DAYS["F"]), "source": c.ELIGIBILITY_SOURCE},
            {"group": "Eligibility (verify)", "name": "Haemoglobin (self-check, optional)", "value": ">= %g g/dL" % c.HB_MIN_G_DL, "source": c.ELIGIBILITY_SOURCE},
            {"group": "Ranking", "name": "Weights", "value": "compat %.2f / proximity %.2f / response %.2f / fairness %.2f" % (c.W_COMPAT, c.W_DISTANCE, c.W_RESPONSE, c.W_FAIRNESS), "source": "Design choice; sums to 1"},
            {"group": "Ranking", "name": "Proximity decay tau", "value": ", ".join("%s %g min" % (k, v) for k, v in c.URGENCY_TAU_MIN.items()), "source": "Design choice"},
            {"group": "Ranking", "name": "Fairness window", "value": "%g days" % c.FAIRNESS_WINDOW_DAYS, "source": "Design choice"},
            {"group": "Travel (approx.)", "name": "Road circuity x speed", "value": "%.1f x straight km at %g km/h + %g min prep" % (c.ROAD_CIRCUITY, c.AVG_SPEED_KMPH, c.PREP_MIN), "source": "Assumption"},
            {"group": "Simulator (assumptions)", "name": "Show-up / on-site pass", "value": "%d%% / %d%%" % (c.SHOWUP_PROB * 100, c.SCREEN_PASS_PROB * 100), "source": "Assumption"},
            {"group": "Simulator (assumptions)", "name": "Reply delay / donation time", "value": "mean %g min / %g min" % (c.RESPONSE_MEAN_MIN, c.DONATION_MIN), "source": "Assumption"},
            {"group": "Simulator (assumptions)", "name": "Broadcast reach / response factor", "value": "mean %g min / x%.1f" % (c.BROADCAST_REACH_MEAN_MIN, c.BROADCAST_RESPONSE_FACTOR), "source": "Assumption (set factor 1.0 to disable)"},
            {"group": "Inventory", "name": "Red-cell shelf life", "value": "CPDA-1 %d d, SAGM %d d" % (c.SHELF_LIFE_DAYS["CPDA-1"], c.SHELF_LIFE_DAYS["SAGM"]), "source": "Standard storage limits for these additives (approx.)"},
            {"group": "Inventory", "name": "Forecast / target cover", "value": "%d-day moving average / %g days" % (c.MA_WINDOW_DAYS, c.TARGET_COVER_DAYS), "source": "Design choice"},
        ]

    def compatibility(self):
        return {
            "groups": config.BLOOD_GROUPS,
            "red": compat.matrix("red"),
            "plasma": compat.matrix("plasma"),
            "donors_for": {g: compat.red_cell_donors_for(g) for g in config.BLOOD_GROUPS},
            "notes": [
                "Red cells: donor ABO antigens must be a subset of the recipient's; RhD-positive cells only to RhD-positive patients.",
                "Plasma: reversed ABO rule (AB plasma is universal); RhD not considered.",
                "Platelets and cryoprecipitate are out of scope.",
                "Final compatibility is always confirmed by cross-matching in the blood bank.",
            ],
        }

    # ---------------------------------------------------------------- donors
    def _public(self, d):
        out = {k: d.get(k) for k in PUBLIC_DONOR_FIELDS}
        out["response_rate"] = round(ranking.response_estimate(d["alerts_received"], d["alerts_accepted"]), 3)
        return out

    def _eligibility(self, d):
        return evaluate(donor_profile(d), self.now.date())

    def map_points(self):
        with self.lock:
            pts = []
            for d in self.donors:
                el = self._eligibility(d)
                pts.append({"id": d["id"], "lat": d["lat"], "lon": d["lon"], "group": d["group"],
                            "eligible": el["eligible"] and d["available"]})
            return {"donors": pts}

    def donors_list(self, q="", group="", limit=50):
        q = (q or "").strip().lower()
        if group:
            try:
                group = compat.normalize(group)
            except compat.GroupError as e:
                raise BadRequest(str(e))
        with self.lock:
            out = []
            for d in self.donors:
                if group and d["group"] != group:
                    continue
                if q and q not in d["name"].lower() and q not in d["id"].lower() and q not in d["town"].lower():
                    continue
                el = self._eligibility(d)
                row = self._public(d)
                row["eligible"] = el["eligible"]
                row["next_eligible_date"] = el["next_eligible_date"]
                out.append(row)
            return {"total": len(out), "donors": out[:max(1, min(int(limit), 300))]}

    def donor(self, donor_id):
        with self.lock:
            d = self.by_id.get(donor_id)
            if d is None:
                raise NotFound("no donor %s" % donor_id)
            el = self._eligibility(d)
            return {"donor": self._public(d), "eligibility": el, "badges": badges(d, el),
                    "lives_helped_upto": d["donations"] * 3,
                    "history": [a for a in self.activity if donor_id in a["notified_ids"]][-10:]}

    def set_availability(self, donor_id, body):
        if not isinstance(body.get("available"), bool):
            raise BadRequest("available must be true or false")
        with self.lock:
            d = self.by_id.get(donor_id)
            if d is None:
                raise NotFound("no donor %s" % donor_id)
            d["available"] = body["available"]
            return self.donor(donor_id)

    def self_check(self, body):
        if not isinstance(body, dict):
            raise BadRequest("body must be an object")
        today = parse_date(body.get("today")) or dt.date.today()
        profile = {k: body.get(k) for k in ("sex", "age", "dob", "weight_kg", "last_donation", "hb", "unwell")}
        res = evaluate(profile, today)
        res["today"] = today.isoformat()
        res["badges"] = []
        return res

    # ---------------------------------------------------------------- matching
    def _req(self, body):
        try:
            return ranking.normalize_request(body, config.HOSPITALS)
        except ranking.RequestError as e:
            raise BadRequest(str(e))

    def match(self, body):
        req = self._req(body)
        with self.lock:
            r = ranking.rank(self.donors, req, self.now, self.now.date())
        limit = body.get("limit", 30)
        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            raise BadRequest("limit must be an integer")
        groups = compat.red_cell_donors_for(req["group"])
        return {"request": req, "counts": r["counts"], "first_wave": r["first_wave"],
                "acceptable_groups": groups, "ranked": r["ranked"][:limit], "ranked_total": len(r["ranked"]),
                "ranked_ids": [x["id"] for x in r["ranked"]],
                "excluded": r["excluded"][:150], "weights": {"compat": config.W_COMPAT, "distance": config.W_DISTANCE,
                                                             "response": config.W_RESPONSE, "fairness": config.W_FAIRNESS}}

    def _seed(self, body):
        try:
            return int(body.get("seed", 1)) % 1000000
        except (TypeError, ValueError):
            raise BadRequest("seed must be an integer")

    def simulate(self, body):
        req = self._req(body)
        seed = self._seed(body)
        with self.lock:
            res = simulation.compare(self.donors, req, self.now, self.now.date(), seed=seed)
        return {"request": req, "seed": seed, "strategies": res, "order": list(simulation.STRATEGIES)}

    def broadcast(self, body):
        """Run the BloodLink wave plan and commit its outcome to the registry (demo):
        alerted donors get last_contacted = now, acceptors +1 accepted, donors who gave
        blood get last_donation = today (so they become ineligible for 90/120 days)."""
        req = self._req(body)
        seed = self._seed(body)
        with self.lock:
            cands = simulation.build_candidates("waves", self.donors, req, self.now, self.now.date())
            res = simulation.run("waves", cands, req["units"], seed)
            stamp = self.now.isoformat(timespec="minutes")
            for i in res["notified_ids"]:
                d = self.by_id[i]
                d["alerts_received"] += 1
                d["last_contacted"] = stamp
            for i in res["accepted_ids"]:
                self.by_id[i]["alerts_accepted"] += 1
            for i in res["donated_ids"]:
                d = self.by_id[i]
                d["last_donation"] = self.now.date().isoformat()
                d["donations"] += 1
            entry = {"n": len(self.activity) + 1, "request": req, "time_to_fulfil": res["time_to_fulfil"],
                     "fulfilled": res["fulfilled"], "notified_ids": res["notified_ids"],
                     "accepted_ids": res["accepted_ids"], "donated_ids": res["donated_ids"]}
            self.activity.append(entry)
        return {"request": req, "seed": seed, "result": res,
                "applied": {"alerted": len(res["notified_ids"]), "accepted": len(res["accepted_ids"]),
                            "donated": len(res["donated_ids"])}}

    def evaluate(self, n=200, seed=11, factor=None):
        try:
            n = max(10, min(int(n), 500))
            seed = int(seed)
            factor = None if factor in (None, "") else max(0.1, min(float(factor), 1.5))
        except (TypeError, ValueError):
            raise BadRequest("n, seed and factor must be numbers")
        key = (n, seed, factor)
        with self.cache_lock:
            if key not in self._eval_cache:
                # evaluated on the pristine registry so results are reproducible
                self._eval_cache[key] = simulation.evaluate_strategies(
                    self.base_donors, config.HOSPITALS, config.DEMO_NOW, config.DEMO_TODAY, n=n, seed=seed,
                    broadcast_factor=factor)
            return self._eval_cache[key]

    # ---------------------------------------------------------------- inventory
    def inventory(self):
        with self.lock:
            net = self.net
            rates = net.rates()
            banks = []
            network = {g: {"units": 0, "at_risk": 0, "rate": 0.0} for g in config.BLOOD_GROUPS}
            for b in config.BANKS:
                bid = b["id"]
                groups = {}
                for g in config.BLOOD_GROUPS:
                    units = [u for u in net.stock[bid] if u["group"] == g]
                    s = inventory.group_status(units, rates[bid][g], 0)
                    groups[g] = s
                    network[g]["units"] += s["units"]
                    network[g]["at_risk"] += s["at_risk"]
                    network[g]["rate"] += rates[bid][g]
                banks.append({"id": bid, "name": b["name"], "town": b["town"], "lat": b["lat"], "lon": b["lon"],
                              "total_units": sum(s["units"] for s in groups.values()),
                              "at_risk": sum(s["at_risk"] for s in groups.values()),
                              "short_groups": [g for g, s in groups.items() if s["status"] in ("short", "low")],
                              "demand_ma": round(sum(rates[bid].values()), 1),
                              "groups": groups,
                              "history": [sum(net.history[bid][g][i] for g in config.BLOOD_GROUPS)
                                          for i in range(len(net.history[bid][config.BLOOD_GROUPS[0]]))]})
            for g, s in network.items():
                s["rate"] = round(s["rate"], 2)
                s["days_cover"] = round(s["units"] / s["rate"], 1) if s["rate"] > 0 else None
            sugg = inventory.suggest_transfers(net.stock, rates, 0)
            expiring = sorted((u for st in net.stock.values() for u in st if u["expires"] <= 5),
                              key=lambda u: (u["expires"], u["id"]))
            return {
                "today": config.DEMO_TODAY.isoformat(), "ma_window": config.MA_WINDOW_DAYS,
                "target_cover_days": config.TARGET_COVER_DAYS, "banks": banks, "network": network,
                "transfers": [dict({k: v for k, v in s.items() if k != "unit_ids"}, unit_ids=s["unit_ids"][:6])
                              for s in sugg],
                "transfer_units": sum(s["units"] for s in sugg),
                "expiring_soon": [self._unit(u) for u in expiring[:12]],
                "expiring_soon_total": len(expiring),
                "forecast_backtest": self.backtest(),
            }

    def _unit(self, u):
        return {"id": u["id"], "group": u["group"], "bank": u["bank"], "additive": u["additive"],
                "collected": _day_iso(u["collected"]), "expires": _day_iso(u["expires"]),
                "days_left": u["expires"], "moved": bool(u.get("moved"))}

    def warm_up(self):
        """Pre-compute the cached analytics the dashboard shows (runs in a background thread)."""
        self.evaluate(300, 11)
        self.evaluate(300, 11, 1.0)
        self.month(20)
        self.backtest()

    def backtest(self):
        if self._backtest is None:
            evs = inventory.generate_events(config.SEED + 99, 180)
            maes, naive, n = 0.0, 0.0, 0
            for b in config.BANKS:
                series = [sum(e["banks"][b["id"]]["demand"].values()) for e in evs]
                r = inventory.backtest_moving_average(series)
                maes += r["mae_ma"] * r["n"]
                naive += r["mae_naive"] * r["n"]
                n += r["n"]
            self._backtest = {"mae_ma7": round(maes / n, 2), "mae_naive": round(naive / n, 2),
                              "days": 180, "series": "daily red-cell demand per bank (synthetic)"}
        return self._backtest

    def issue(self, body):
        bid = body.get("bank_id")
        if bid not in self.net.stock:
            raise BadRequest("unknown bank_id")
        try:
            group = compat.normalize(body.get("group", ""))
            units = int(body.get("units", 1))
        except (compat.GroupError, TypeError, ValueError) as e:
            raise BadRequest(str(e) or "bad group/units")
        if not 1 <= units <= 20:
            raise BadRequest("units must be 1-20")
        allow = body.get("allow_substitutes", True) is not False
        with self.lock:
            st = self.net.stock[bid]
            before = sorted((u for u in st if u["group"] == group and u["expires"] > 0), key=lambda u: u["expires"])
            got, short = inventory.fefo_issue(st, group, units, 0, allow_substitutes=allow)
        issued = [dict(self._unit(u), tier="exact" if u["group"] == group else "substitute") for u in got]
        expl = "FEFO: the %d %s unit%s expiring soonest went first" % (
            sum(1 for u in issued if u["tier"] == "exact"), group, "" if units == 1 else "s")
        subs = [u for u in issued if u["tier"] == "substitute"]
        if subs:
            expl += "; %d compatible substitute%s (%s) used because exact stock ran out" % (
                len(subs), "" if len(subs) == 1 else "s", ", ".join(sorted({u["group"] for u in subs})))
        if short:
            expl += "; %d unit%s could not be supplied - see transfer suggestions" % (short, "" if short == 1 else "s")
        return {"issued": issued, "unmet": short, "explanation": expl,
                "exact_stock_before": [self._unit(u) for u in before[:8]]}

    def apply_transfers(self):
        with self.lock:
            sugg = inventory.suggest_transfers(self.net.stock, self.net.rates(), 0)
            moved = 0
            for s in sugg:
                src = self.net.stock[s["from"]]
                ids = set(s["unit_ids"])
                units = [u for u in src if u["id"] in ids]
                src[:] = [u for u in src if u["id"] not in ids]
                for u in units:   # demo shortcut: delivered immediately (sim uses 1-day transit)
                    self.net.stock[s["to"]].append(dict(u, moved=True, bank=s["to"]))
                moved += len(units)
            return {"moved": moved, "shipments": len({(s["from"], s["to"]) for s in sugg}), "suggestions": len(sugg)}

    def month(self, seeds=20):
        try:
            seeds = max(1, min(int(seeds), 40))
        except (TypeError, ValueError):
            raise BadRequest("seeds must be an integer")
        with self.cache_lock:
            if self._month_cache is None or self._month_cache[0] != seeds:
                self._month_cache = (seeds, inventory.compare_month(self.base_net, range(1, seeds + 1)))
            return self._month_cache[1]


def badges(d, el):
    out = []
    n = d["donations"]
    rate = ranking.response_estimate(d["alerts_received"], d["alerts_accepted"])
    rules = [
        (n >= 1, "First Drop", "Donated at least once"),
        (n >= 3, "Regular", "3+ donations"),
        (n >= 5, "Life Saver", "5+ donations"),
        (n >= 10, "10+ Club", "10 or more donations"),
        (d["group"].endswith("-"), "Rare Hero", "Rh-negative donor - rare in India (~5%, approx.)"),
        (d["group"] == "O-", "Universal Red Cells", "O- red cells suit every group in emergencies"),
        (d["alerts_received"] >= 3 and rate >= 0.7, "Rapid Responder", "Accepts most alerts"),
        (el["eligible"] and d["available"], "Ready Now", "Eligible and available today"),
    ]
    for ok, name, desc in rules:
        out.append({"name": name, "desc": desc, "earned": bool(ok)})
    return out
