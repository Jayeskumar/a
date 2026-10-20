"""Campus engine: runs every analysis once and serves JSON-ready results."""

import time

from . import anomaly, carbon, dataset, forecast, leaderboard, solar, whatif
from .stats import mean


class UnknownBuilding(KeyError):
    pass


class Campus(object):
    def __init__(self, data_dir, seed=dataset.DEFAULT_SEED, regenerate=False):
        self.data_dir = data_dir
        self.seed = seed
        self.reload(regenerate)

    # ------------------------------------------------------------ lifecycle
    def reload(self, regenerate=False):
        t0 = time.time()
        if regenerate:
            self.ds = dataset.generate(self.seed)
            try:
                dataset.save(self.ds, self.data_dir)
            except OSError:
                pass
        else:
            self.ds = dataset.load_or_generate(self.data_dir, self.seed)
        ds = self.ds
        self.hourly, self.events = {}, {}
        for bid in dataset.BUILDING_IDS:
            self.hourly[bid], self.events[bid] = anomaly.detect(ds.timestamps, ds.loads[bid], bid)
        self.backtests = {b: forecast.backtest(ds, b) for b in dataset.BUILDING_IDS}
        self.forecasts = {b: forecast.forecast_next_week(ds, b) for b in dataset.BUILDING_IDS}
        self.board = leaderboard.compute(ds, self.events)
        self.anomaly_eval = anomaly.evaluate(self.events, ds.events, ds.n_hours)
        self.compute_ms = round((time.time() - t0) * 1000)

    def _check(self, bid):
        if bid not in dataset.BUILDING_BY_ID:
            raise UnknownBuilding(bid)
        return dataset.BUILDING_BY_ID[bid]

    # ------------------------------------------------------------ views
    def buildings(self):
        ds = self.ds
        out = []
        last30 = 30 * 24
        for b in dataset.BUILDINGS:
            y = ds.loads[b["id"]]
            out.append({
                "id": b["id"], "name": b["name"], "type": b["type"],
                "roof_m2": b["roof_m2"], "shares": b["shares"],
                "auto_off_eligible": b["auto_off"],
                "avg_kw": round(mean(y), 1), "peak_kw": round(max(y), 1),
                "last30_kwh": round(sum(y[-last30:])),
                "monthly_kwh": round(sum(y[-28 * 24:]) * 30 / 28.0),
                "waste_events": len(self.events[b["id"]]),
                "mape": self.backtests[b["id"]]["mape"]["regression"],
            })
        return out

    def overview(self):
        ds = self.ds
        last30 = 30 * 24
        kwh30 = sum(sum(y[-last30:]) for y in ds.loads.values())
        all_events = [e for evs in self.events.values() for e in evs]
        waste_kwh = sum(e["wasted_kwh"] for e in all_events)
        days = ds.n_hours / 24.0
        next_week = sum(f["total_kwh"] for f in self.forecasts.values())
        roof = sum(b["roof_m2"] for b in dataset.BUILDINGS)
        sol = solar.plan(roof, monthly_kwh=kwh30)
        champ = self.board["rows"][0]
        recent = sorted(all_events, key=lambda e: e["start"], reverse=True)[:5]
        return {
            "campus": "Demo campus (synthetic data)",
            "period": {"start": ds.timestamps[0].isoformat(), "end": ds.timestamps[-1].isoformat(),
                       "days": days, "hours": ds.n_hours},
            "last30": carbon.footprint(kwh30, 30),
            "waste": {
                "events": len(all_events), "kwh": round(waste_kwh),
                "cost_inr": round(carbon.cost_inr(waste_kwh)),
                "co2_kg": round(carbon.co2_kg(waste_kwh)),
                "annual_cost_inr": round(carbon.cost_inr(waste_kwh) * 365 / days),
                "pct_of_use": round(100.0 * waste_kwh / sum(sum(y) for y in ds.loads.values()), 2),
            },
            "forecast_next_week": {"kwh": round(next_week),
                                   "cost_inr": round(carbon.cost_inr(next_week)),
                                   "co2_kg": round(carbon.co2_kg(next_week))},
            "forecast_mape_avg": round(mean(b["mape"]["regression"] for b in self.backtests.values()), 2),
            "solar_all_roofs": {"kwp": sol["kwp"], "annual_generation_kwh": sol["annual_generation_kwh"],
                                "coverage_pct": sol["coverage_pct"],
                                "payback_years": sol["simple_payback_years"],
                                "co2_avoided_t_per_year": sol["co2_avoided_t_per_year"]},
            "champion": {"name": champ["name"], "saving_pct": champ["saving_pct"]},
            "recent_alerts": recent,
            "assumptions": carbon.assumptions(),
            "compute_ms": self.compute_ms,
        }

    def series(self, bid, days=14):
        b = self._check(bid)
        ds = self.ds
        days = max(1, min(int(days), dataset.N_DAYS))
        n = days * 24
        ts = ds.timestamps[-n:]
        bt = self.backtests[bid]
        fc = self.forecasts[bid]
        return {
            "building": bid, "name": b["name"],
            "actual": {"timestamps": [t.isoformat() for t in ts], "kwh": ds.loads[bid][-n:],
                       "temp_c": ds.temps[-n:]},
            "backtest": {"timestamps": bt["timestamps"], "kwh": bt["predicted"],
                         "mape": bt["mape"], "wape": bt["wape"],
                         "mape_excluding_waste_hours": bt["mape_excluding_waste_hours"]},
            "forecast": {"timestamps": fc["timestamps"], "kwh": fc["predicted"],
                         "temp_c": fc["temps"], "total_kwh": fc["total_kwh"],
                         "peak": fc["peak"], "model": fc["model"],
                         "weather_sensitivity_kwh_per_degc": fc["weather_sensitivity_kwh_per_degc"],
                         "cost_inr": round(carbon.cost_inr(fc["total_kwh"])),
                         "co2_kg": round(carbon.co2_kg(fc["total_kwh"]))},
            "events": [e for e in self.events[bid] if e["end_index"] >= ds.n_hours - n],
        }

    def heatmap(self, bid):
        b = self._check(bid)
        ds = self.ds
        y = ds.loads[bid]
        days = []
        for d in range(dataset.N_DAYS):
            day = ds.timestamps[d * 24].date()
            days.append({"date": day.isoformat(), "weekday": day.strftime("%a"),
                         "holiday": dataset.HOLIDAYS.get(day),
                         "kwh": y[d * 24:(d + 1) * 24],
                         "flags": [1 if self.hourly[bid][d * 24 + h]["flag"] else 0
                                   for h in range(24)]})
        return {"building": bid, "name": b["name"], "days": days,
                "max": max(y), "min": min(y)}

    def anomalies(self, bid=None):
        if bid:
            self._check(bid)
            evs = list(self.events[bid])
        else:
            evs = [e for v in self.events.values() for e in v]
        evs.sort(key=lambda e: e["start"], reverse=True)
        total = sum(e["wasted_kwh"] for e in evs)
        return {"events": evs, "count": len(evs), "wasted_kwh": round(total, 1),
                "cost_inr": round(carbon.cost_inr(total)),
                "co2_kg": round(carbon.co2_kg(total), 1),
                "method": anomaly.__doc__.strip().split("\n\n")[1].strip()}

    def evaluation(self):
        fc = {b: {"mape": v["mape"], "wape": v["wape"],
                  "mape_excluding_waste_hours": v["mape_excluding_waste_hours"],
                  "trimmed_training_hours": v["trimmed_training_hours"]}
              for b, v in self.backtests.items()}
        avg = {k: round(mean(v["mape"][k] for v in self.backtests.values()), 2)
               for k in ("regression", "holt_winters", "seasonal_naive")}
        sens = []
        presets = (("high", 2.5, 1.0, 0.10), ("medium-high", 3.0, 1.5, 0.20),
                   ("default", 3.5, 2.0, 0.30), ("low", 5.0, 3.0, 0.50),
                   ("very low", 8.0, 5.0, 0.80))
        for name, z, kw, frac in presets:
            det = {b: anomaly.detect(self.ds.timestamps, self.ds.loads[b], b, z_threshold=z,
                                     min_kw=kw, min_frac=frac)[1]
                   for b in dataset.BUILDING_IDS}
            ev = anomaly.evaluate(det, self.ds.events, self.ds.n_hours)
            sens.append({"preset": name, "z": z, "min_kw": kw, "min_frac": frac,
                         "precision": ev["event_precision"], "recall": ev["event_recall"],
                         "events": ev["events_detected"]})
        return {"forecast": {"holdout": "week 8 (%s to %s), trained on weeks 1-7"
                             % (self.backtests["admin"]["timestamps"][0][:10],
                                self.backtests["admin"]["timestamps"][-1][:10]),
                             "by_building": fc, "average_mape": avg},
                "anomaly": self.anomaly_eval, "anomaly_threshold_sensitivity": sens,
                "compute_ms": self.compute_ms,
                "ground_truth_events": self.ds.events}

    def leaderboard(self):
        return self.board

    def solar(self, params):
        """Plan from explicit inputs, or pre-fill from a building ('campus' = all)."""
        bid = params.get("building")
        if bid:
            if bid == "campus":
                roof = sum(b["roof_m2"] for b in dataset.BUILDINGS)
                series = [sum(v) for v in zip(*self.ds.loads.values())]
            else:
                roof = self._check(bid)["roof_m2"]
                series = self.ds.loads[bid]
            if not params.get("roof_area_m2"):
                params = dict(params, roof_area_m2=roof)
            if not params.get("monthly_kwh") and not params.get("monthly_bill_inr"):
                params = dict(params, monthly_kwh=round(sum(series[-28 * 24:]) * 30 / 28.0, 1))
        return solar.plan(params.get("roof_area_m2"), params.get("monthly_kwh"),
                          params.get("monthly_bill_inr"), params.get("tariff"),
                          params.get("cost_per_kwp"), params.get("yield_kwh_per_kwp"))

    def whatif(self, params):
        return whatif.simulate(self.ds, params.get("ac_setpoint_delta", 0),
                               params.get("auto_off", False), params.get("auto_off_hour", 22),
                               params.get("led_pct", 0), params.get("bldc_pct", 0))
