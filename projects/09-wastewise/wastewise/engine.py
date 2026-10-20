"""Facade used by the HTTP layer: owns the simulation state and shapes JSON responses."""

import json
import os
import threading
import time

from . import classifier
from . import config as C
from . import impact
from .forecast import DOW, SeasonalES, backtest, hours_to_full
from .planner import naive_all_bins
from .segregation import ReportStore
from .simulator import POLICIES, Simulation, simulate_month
from .town import Town, date_of, is_market_day, weekday_of


class NotFound(Exception):
    pass


class BadRequest(Exception):
    pass


def _clock(minutes_from_start):
    h = C.SHIFT_START_H + minutes_from_start / 60.0
    return "%02d:%02d" % (int(h), int(round((h - int(h)) * 60)) % 60)


class Engine:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        t0 = time.perf_counter()
        self.town = Town()
        self.sim = Simulation(self.town)
        self.lock = threading.RLock()
        self.reports = ReportStore(os.path.join(data_dir, "reports.json"))
        self._month = None
        self._evaluation = None
        self._export()
        self.startup_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    # ------------------------------------------------------------------ files
    def _export(self):
        """Write the generated town + sensor history to data/ for transparency (first run)."""
        path = os.path.join(self.data_dir, "town.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.town.to_json(), f, ensure_ascii=False, indent=1)
        hpath = os.path.join(self.data_dir, "sensor_history.csv")
        if not os.path.exists(hpath):
            with open(hpath, "w", encoding="utf-8") as f:
                f.write("bin,day,date,weekday,daily_fill_fraction\n")
                for b in self.town.bins:
                    for d, dow, v in self.town.history(b):
                        f.write("%s,%d,%s,%s,%.4f\n" % (b.id, d, date_of(d).isoformat(),
                                                        DOW[dow], v))

    # ------------------------------------------------------------------ basics
    def health(self):
        return {"status": "ok", "day": self.sim.day, "bins": len(self.town.bins),
                "trucks": len(self.town.trucks), "startup_ms": self.startup_ms}

    def town_json(self):
        t = self.town.to_json()
        t["constants"] = {
            "truck_capacity_l": C.TRUCK_CAPACITY_L, "shift_min": C.SHIFT_MIN,
            "shift_start_h": C.SHIFT_START_H, "speed_kmph": C.SPEED_KMPH,
            "service_min": C.SERVICE_MIN_PER_BIN, "unload_min": C.UNLOAD_MIN,
            "collect_threshold": C.COLLECT_THRESHOLD, "market_weekday": DOW[C.MARKET_WEEKDAY],
        }
        return t

    def _day(self, day):
        d = date_of(day)
        return {"day": day, "date": d.isoformat(), "weekday": DOW[d.weekday()],
                "market_day": is_market_day(day),
                "label": "%s %s" % (DOW[d.weekday()], d.strftime("%d %b %Y"))}

    def state_json(self):
        with self.lock:
            sim = self.sim
            out = {"today": self._day(sim.day),
                   "tomorrow_market": is_market_day(sim.day + 1),
                   "levels": {p: {k: round(v, 4) for k, v in sim.worlds[p].levels.items()}
                              for p in POLICIES},
                   "totals": {p: sim.worlds[p].totals() for p in POLICIES},
                   "daily": {p: sim.worlds[p].daily for p in POLICIES},
                   "events": self._recent_events(sim.events)}
            return out

    @staticmethod
    def _recent_events(events, n=14):
        out = []
        for e in events[-n:][::-1]:
            out.append({"day": e["day"], "label": e["label"], "market_day": e["market_day"],
                        "fixed_overflows": e["overflows"]["fixed"],
                        "smart_overflows": e["overflows"]["smart"],
                        "fixed_km": e["kpis"]["fixed"]["km"], "smart_km": e["kpis"]["smart"]["km"]})
        return out

    # ------------------------------------------------------------------ plan
    def _xy(self, node):
        if node == "DEPOT":
            return self.town.depot["x"], self.town.depot["y"]
        b = self.town.bin_by_id[node]
        return b.x, b.y

    def _shape_run(self, run, plan_trucks=None):
        trucks = []
        for i, tr in enumerate(run["trucks"]):
            info = self.town.trucks[i]
            ev = []
            for e in tr["events"]:
                x, y = self._xy(e["node"])
                item = dict(e)
                item.update({"x": x, "y": y, "clock": _clock(e["arrive"])})
                ev.append(item)
            row = {"truck": info["id"], "name": info["name"], "color": info["color"],
                   "km": tr["km"], "minutes": tr["minutes"], "stops": tr["stops"],
                   "unloads": tr["unloads"], "fuel_l": tr["fuel_l"],
                   "finish": _clock(tr["minutes"]), "events": ev}
            if plan_trucks is not None:
                row["trips"] = plan_trucks[i]["trips"]
            trucks.append(row)
        return trucks

    def plan_json(self):
        with self.lock:
            p = self.sim.preview()
            ks, kf = p["kpis"]["smart"], p["kpis"]["fixed"]

            def pct(a, b):
                return round(100.0 * (1 - a / b), 1) if b else 0.0
            savings = {
                "km": round(kf["km"] - ks["km"], 2), "km_pct": pct(ks["km"], kf["km"]),
                "fuel_l": round(kf["fuel_l"] - ks["fuel_l"], 2),
                "fuel_pct": pct(ks["fuel_l"], kf["fuel_l"]),
                "co2_kg": round(kf["co2_kg"] - ks["co2_kg"], 2),
                "inr": round(kf["cost_inr"] - ks["cost_inr"], 0),
                "truck_hours": round(kf["truck_hours"] - ks["truck_hours"], 2),
                "overflows_avoided": kf["overflow_bins"] - ks["overflow_bins"],
            }
            return {
                "day": self._day(self.sim.day),
                "tomorrow_market": is_market_day(self.sim.day + 1),
                "decisions": p["decisions"],
                "smart": {"trucks": self._shape_run(p["runs"]["smart"], p["plan"]["trucks"]),
                          "kpis": ks, "unvisited": p["runs"]["smart"]["unvisited"],
                          "overflows": p["overflows"]["smart"]},
                "fixed": {"trucks": self._shape_run(p["runs"]["fixed"]), "kpis": kf,
                          "unvisited": p["runs"]["fixed"]["unvisited"],
                          "overflows": p["overflows"]["fixed"]},
                "algorithm": p["plan"]["algorithm"],
                "savings": savings,
                "naive_all": naive_all_bins(self.town),
                "fleet_minutes": C.N_TRUCKS * C.SHIFT_MIN,
                "shift": {"start": _clock(0), "end": _clock(C.SHIFT_MIN), "minutes": C.SHIFT_MIN},
            }

    # ------------------------------------------------------------------ simulator
    def advance(self, body):
        days = (body or {}).get("days", 1)
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 60:
            raise BadRequest("'days' must be an integer between 1 and 60")
        with self.lock:
            if self.sim.day + days > 365:
                raise BadRequest("simulation is limited to 365 days; reset first")
            out = self.sim.run(days)
            return {"advanced": days,
                    "days": [{"label": d["label"], "market_day": d["market_day"],
                              "kpis": d["kpis"], "overflows": d["overflows"]} for d in out],
                    "state": self.state_json()}

    def reset(self):
        with self.lock:
            self.sim.reset()
            return {"status": "ok", "message": "Simulation reset to day 0", "state": self.state_json()}

    def demo(self):
        with self.lock:
            self.sim.reset()
            self.reports.reset()
            return {"status": "ok", "message": "Demo data loaded: day 0, %d segregation reports"
                    % len(self.reports.reports), "state": self.state_json()}

    def month_json(self, days=None):
        days = days or C.MONTH_DAYS
        if self._month is not None and self._month["days"] == days:
            return self._month
        t0 = time.perf_counter()
        sim = Simulation(self.town)
        solver_ms = []
        daily = []
        for _ in range(days):
            p = sim.preview()
            solver_ms.append(p["plan"]["algorithm"]["total_ms"])
            alg = p["plan"]["algorithm"]
            s = sim.step()
            row = {"label": s["label"], "market_day": s["market_day"]}
            for pol in POLICIES:
                row[pol] = s["kpis"][pol]
            row["routing"] = {"fixed_order_km": alg["fixed_order_km"],
                              "clarke_wright_km": alg["clarke_wright_km"],
                              "two_opt_km": alg["two_opt_km"], "bins": alg["bins"]}
            daily.append(row)
        tf, ts = sim.worlds["fixed"].totals(), sim.worlds["smart"].totals()
        routing = {k: round(sum(d["routing"][k] for d in daily), 2)
                   for k in ("fixed_order_km", "clarke_wright_km", "two_opt_km")}

        def pct(a, b):
            return round(100.0 * (1 - a / b), 1) if b else 0.0
        self._month = {
            "days": days,
            "daily": daily,
            "totals": {"fixed": tf, "smart": ts},
            "savings_pct": {k: pct(ts[k], tf[k]) for k in
                            ("km", "fuel_l", "co2_kg", "cost_inr", "truck_hours", "stops",
                             "overflow_bins", "overflow_l")},
            "routing_only": dict(routing, cw_vs_fixed_pct=pct(routing["clarke_wright_km"],
                                                              routing["fixed_order_km"]),
                                 two_opt_extra_pct=pct(routing["two_opt_km"],
                                                       routing["clarke_wright_km"])),
            "solver_ms": {"mean": round(sum(solver_ms) / len(solver_ms), 3),
                          "max": round(max(solver_ms), 3)},
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }
        return self._month

    # ------------------------------------------------------------------ forecast
    def forecast_json(self, bin_id):
        b = self.town.bin_by_id.get(bin_id)
        if b is None:
            raise NotFound("unknown bin '%s'" % bin_id)
        with self.lock:
            sim = self.sim
            obs = sim.obs[b.id]
            model = sim.forecasters[b.id]
            replay = SeasonalES(model.alpha, model.gamma)
            replay._init([(dow, v) for _, dow, v in obs[:len(obs)]])
            hist = []
            for k, (d, dow, v) in enumerate(obs):
                fit = replay.forecast(dow) if k >= 7 else None
                hist.append({"day": d, "date": date_of(d).isoformat(), "dow": DOW[dow],
                             "value": round(v, 4),
                             "fitted": round(fit, 4) if fit is not None else None,
                             "market_day": dow == C.MARKET_WEEKDAY})
                replay.update(dow, v, score=False)
            level = sim.worlds["smart"].levels[b.id]
            fc, lvl, path = [], level, []
            for k in range(7):
                d = sim.day + k
                dow = weekday_of(d)
                v = model.forecast(dow)
                fc.append({"day": d, "date": date_of(d).isoformat(), "dow": DOW[dow],
                           "value": round(v, 4), "lo": round(max(0.0, v - model.sigma), 4),
                           "hi": round(v + model.sigma, 4), "market_day": is_market_day(d)})
                lvl += v
                path.append(round(lvl, 4))
            horizon = [model.forecast(weekday_of(sim.day + k)) for k in range(14)]
            h = hours_to_full(level, horizon, 0.0, (C.DEPOSIT_START_H, C.DEPOSIT_END_H))
            full_at = None
            if h is not None:
                dd = sim.day + int(h // 24)
                hh = h - 24 * int(h // 24)
                full_at = "%s %02d:%02d" % (DOW[weekday_of(dd)], int(hh), int((hh % 1) * 60))
            decision = next(d for d in sim.preview()["decisions"] if d["bin"] == b.id)
            vals = [(dow, v) for _, dow, v in obs]
            return {
                "bin": b.to_json(), "ward_name": self.town.ward_by_id[b.ward]["name"],
                "level": round(level, 4), "today": self._day(sim.day),
                "history": hist[-42:], "forecast": fc, "if_not_collected": path,
                "model": model.to_json(),
                "season": [{"dow": DOW[k], "index": round(model.season[k], 3)} for k in range(7)],
                "backtest_mae": {k: round(v, 4) for k, v in backtest(vals).items()},
                "hours_to_full": h, "full_at": full_at, "decision": decision,
            }

    def evaluation_json(self):
        if self._evaluation is None:
            t0 = time.perf_counter()
            agg = {}
            for b in self.town.bins:
                vals = [(dow, v) for _, dow, v in self.town.history(b)]
                for k, v in backtest(vals).items():
                    agg.setdefault(k, []).append(v)
            mae = {k: round(sum(v) / len(v), 4) for k, v in agg.items()}
            mean_fill = sum(v for b in self.town.bins for _, _, v in self.town.history(b)) / (
                len(self.town.bins) * C.HISTORY_DAYS)
            self._evaluation = {
                "forecast": {"holdout_days": 14, "mae": mae,
                             "mean_daily_fill": round(mean_fill, 4),
                             "best": min(mae, key=mae.get),
                             "seasonal_es_vs_naive_pct": round(
                                 100 * (1 - mae["seasonal_es"] / mae["naive"]), 1)},
                "classifier": classifier.evaluate(),
                "eval_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            }
        out = dict(self._evaluation)
        m = self.month_json()
        out["month"] = {"days": m["days"], "savings_pct": m["savings_pct"],
                        "routing_only": m["routing_only"], "solver_ms": m["solver_ms"]}
        return out

    # ------------------------------------------------------------------ segregation
    def classify_json(self, text):
        if not isinstance(text, str) or not text.strip():
            raise BadRequest("'item' is required")
        if len(text) > 80:
            raise BadRequest("'item' must be at most 80 characters")
        return classifier.classify(text.strip())

    def report_json(self, body):
        from .segregation import ReportError
        try:
            rep, verdict = self.reports.add(body, date_of(self.sim.day).isoformat())
        except ReportError as e:
            raise BadRequest(str(e))
        return {"report": rep, "verdict": verdict, "leaderboard": self.reports.leaderboard()}

    def leaderboard_json(self):
        return self.reports.leaderboard()

    # ------------------------------------------------------------------ impact
    def impact_json(self, diesel=None, bins=None, kmpl=None):
        m = self.month_json()
        out = impact.project(m["totals"]["fixed"], m["totals"]["smart"], diesel, bins, kmpl)
        out["month_totals"] = m["totals"]
        return out
