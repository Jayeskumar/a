"""Orchestrates the whole analysis and shapes results for the HTTP API (no HTTP code here)."""
import math
import os
import threading
import time
from datetime import timedelta

from . import abcxyz, apriori, backtest, catalog, config, dataset, festivals, inventory, simulate, synth
from .forecast import SkuContext, explain_regression, forecast
from .stats import inv_norm

BAND_Z = 1.2816   # 80% prediction band


def _r(v, nd=2):
    return None if v is None else round(v, nd)


class Analysis:
    """All derived results for one dataset. Immutable once built (safe to share across threads)."""

    def __init__(self, ds):
        t0 = time.time()
        self.ds = ds
        self.today = ds.today
        n = ds.n
        H = config.FORECAST_HORIZON
        self.fc_dates = [self.today + timedelta(days=i) for i in range(H)]
        self.ctx, self.bt, self.fc, self.uplift, self.coef = {}, {}, {}, {}, {}
        for s in ds.skus:
            ctx = SkuContext(ds.clean[s], ds.stockout[s], ds.promo[s], ds.dates)
            self.ctx[s] = ctx
            bt = backtest.backtest_sku(ctx, n)
            self.bt[s] = bt
            u = ctx.festival_uplift(n)
            self.uplift[s] = u
            out = {}
            for m in config.MODEL_ORDER:
                pred, used, _ = forecast(ctx, m, n, H, uplift=u)
                out[m] = pred
                if m == "linreg":
                    self.coef[s] = used["coef"]
            self.fc[s] = out
        self.chosen = {s: self.bt[s]["chosen"] for s in ds.skus}
        self.sigma = {s: self.bt[s]["sigma"] for s in ds.skus}

        # Revenue (last 365 days) for ABC; weekly cleaned demand for XYZ.
        last = max(0, n - 365)
        self.revenue = {s: sum(ds.qty[s][last:]) * ds.items[s]["price"] for s in ds.skus}
        weekly = {s: dataset.weekly_totals(ds.clean[s], 104) for s in ds.skus}   # whole history
        names = {s: ds.items[s]["name"] for s in ds.skus}
        self.abc = abcxyz.matrix(self.revenue, weekly, names)

        # Market basket (bill log only covers demo SKUs).
        self.baskets = [b & set(ds.skus) for b in ds.baskets]
        self.baskets = [b for b in self.baskets if b]
        self._basket_cache = {}
        self.basket(config.MIN_SUPPORT, config.MIN_CONFIDENCE)

        self._prepare_simulation()
        self._sim_cache = {}
        self.build_seconds = round(time.time() - t0, 2)

    # ------------------------------------------------------------ simulation setup
    def _prepare_simulation(self):
        ds, n = self.ds, self.ds.n
        min_cut = config.MIN_TRAIN_DAYS + config.BACKTEST_FOLDS * config.BACKTEST_STEP
        sim_days = min(config.SIM_DAYS, n - min_cut - config.SIM_WARMUP)
        self.sim_ready = sim_days >= 28
        self.sim_days = sim_days if self.sim_ready else 0
        if not self.sim_ready:
            return
        start = n - sim_days - config.SIM_WARMUP
        self.sim_start = start
        self.sim_dates = ds.dates[start + config.SIM_WARMUP:]
        self.sim_inputs = {}
        total = n - start
        for s in ds.skus:
            ctx = self.ctx[s]
            bt = backtest.backtest_sku(ctx, start)       # model chosen with data before the window
            model = bt["chosen"]
            u = ctx.festival_uplift(start)
            params = None
            if model == "hw":
                params = {"abg": forecast(ctx, "hw", start, 1, uplift=u)[1]["abg"]}
            fcs = {}
            for r in range(0, total, config.SIM_REFIT_EVERY):
                fcs[r] = forecast(ctx, model, start + r, config.FORECAST_HORIZON + 7, params=params, uplift=u)[0]
            demand = [int(round(v)) for v in ds.clean[s][start:]]
            pre = ds.clean[s][max(0, start - 56):start]
            gq, gd = simulate.gut_quantity(ds.items[s], pre)
            avg = sum(pre) / len(pre) if pre else 0.0
            init = int(math.ceil(avg * (ds.items[s]["lead_time"] + 3)))
            if ds.items[s]["shelf_life"] <= config.PERISHABLE_DAYS:
                init = min(init, int(math.ceil(avg * max(1, ds.items[s]["shelf_life"] - 1))))
            self.sim_inputs[s] = {"model": model, "sigma": bt["sigma"], "forecasts": fcs, "demand": demand,
                                  "gut_qty": gq, "gut_daily": gd, "init": init}
        self.sim_weekdays = [d.weekday() for d in ds.dates[start:]]

    def simulation(self, service):
        key = round(service, 4)
        if key in self._sim_cache:
            return self._sim_cache[key]
        if not self.sim_ready:
            return {"ready": False, "message": "Need at least ~6 months of history to simulate 90 days."}
        rows, gut_all, ss_all, traj = [], [], [], {}
        for s in self.ds.skus:
            si, item = self.sim_inputs[s], self.ds.items[s]
            g, gt = simulate.run(item, si["demand"], self.sim_weekdays, "gut", config.SIM_WARMUP,
                                 gut_qty=si["gut_qty"], gut_daily=si["gut_daily"], init_stock=si["init"])
            k, kt = simulate.run(item, si["demand"], self.sim_weekdays, "stocksense", config.SIM_WARMUP,
                                 forecasts=si["forecasts"], sigma=si["sigma"], service=service, init_stock=si["init"])
            gut_all.append(g)
            ss_all.append(k)
            traj[s] = {"gut": gt, "stocksense": kt}
            rows.append({"sku": s, "name": item["name"], "model": si["model"],
                         "gut_order": si["gut_qty"], "gut_cycle": "daily" if si["gut_daily"] else "weekly",
                         "gut": _round_metrics(g), "stocksense": _round_metrics(k)})
        G, S = simulate.aggregate(gut_all), simulate.aggregate(ss_all)

        def pct(a, b):
            return round(100.0 * (b - a) / a, 1) if a else None
        res = {
            "ready": True, "service": service, "days": self.sim_days,
            "start": self.sim_dates[0].isoformat(), "end": self.sim_dates[-1].isoformat(),
            "dates": [d.isoformat() for d in self.sim_dates],
            "gut": G, "stocksense": S,
            "change_pct": {k: pct(G[k], S[k]) for k in ("stockout_days", "lost_sales", "expired_units",
                                                         "waste_cost", "holding_cost", "total_cost",
                                                         "avg_inventory_value", "orders")},
            "rows": rows, "trajectories": traj,
            "assumptions": [
                "Demand = actual sales with stock-out days imputed; unmet demand is lost (customers walk out).",
                "Gut-feel: fixed order = 8-week average x %.2f, weekly on Monday (daily if shelf life <= 7 d), "
                "skipped when the shelf already holds that much." % config.GUT_BUFFER,
                "StockSense: models chosen and tuned on data before the window; forecasts refreshed every %d days."
                % config.SIM_REFIT_EVERY,
                "Holding cost %d%%/yr of unit cost; ₹%d per order line; supplier lead times vary per order."
                % (round(config.HOLDING_RATE * 100), config.ORDER_COST),
            ],
        }
        self._sim_cache[key] = res
        return res

    # ------------------------------------------------------------ basket
    def basket(self, min_support, min_conf):
        key = (round(min_support, 4), round(min_conf, 4))
        if key in self._basket_cache:
            return self._basket_cache[key]
        freq, nb = apriori.frequent_itemsets(self.baskets, min_support)
        rules = apriori.association_rules(freq, nb, min_conf, config.MIN_LIFT) if nb else []
        items = self.ds.items
        res = {
            "bills": nb, "min_support": min_support, "min_confidence": min_conf, "min_lift": config.MIN_LIFT,
            "itemsets": sorted(({"items": sorted(k), "support": round(v / nb, 4), "count": v}
                                for k, v in freq.items() if len(k) >= 2), key=lambda r: -r["count"])[:40],
            "rules": [dict(r, support=round(r["support"], 4), confidence=round(r["confidence"], 4),
                           lift=round(r["lift"], 3)) for r in rules[:150]],
            "rule_count": len(rules),
            "suggestions": apriori.placement_suggestions(rules, items),
            "names": {s: items[s]["name"] for s in self.ds.skus},
            "note": "Bills are a synthetic POS log for the demo catalogue." if nb else
                    "No bill log available for these SKUs.",
        }
        self._basket_cache[key] = res
        return res

    # ------------------------------------------------------------ inventory views
    def plan(self, service, overrides=None):
        rows = []
        for s in self.ds.skus:
            oh = (overrides or {}).get(s) or self.ds.on_hand[s]
            row = inventory.plan_item(self.ds.items[s], self.fc[s][self.chosen[s]], self.sigma[s],
                                      int(oh["on_hand"]), int(oh.get("on_order", 0)), service,
                                      config.MODEL_NAMES[self.chosen[s]])
            row["class"] = self.abc["per_sku"][s]["class"]
            row["model"] = self.chosen[s]
            row["assumed_stock"] = bool(oh.get("assumed"))
            rows.append(row)
        rank = {"urgent": 0, "order": 1, "overstock": 2, "ok": 3}
        rows.sort(key=lambda r: (rank[r["status"]], -r["sales_at_risk"], r["sku"]))
        need = [r for r in rows if r["order_qty"] > 0]
        return {
            "date": self.today.isoformat(), "service": service, "z": round(inv_norm(service), 4),
            "rows": rows,
            "totals": {
                "items_to_order": len(need),
                "urgent": sum(1 for r in rows if r["status"] == "urgent"),
                "overstock": sum(1 for r in rows if r["status"] == "overstock"),
                "order_value": round(sum(r["order_value"] for r in need), 2),
                "sales_at_risk": round(sum(r["sales_at_risk"] for r in need), 2),
                "sales_saved": round(sum(r["sales_saved"] for r in need), 2),
                "excess_value": round(sum(r["excess_value"] for r in rows), 2),
            },
        }

    def whatif(self, service):
        items_fc = [(self.ds.items[s], self.fc[s][self.chosen[s]], self.sigma[s]) for s in self.ds.skus]
        levels = sorted(set(config.SERVICE_GRID) | {round(service, 4)})
        curve = inventory.tradeoff(items_fc, levels)
        at = next(p for p in curve["points"] if abs(p["service"] - round(service, 4)) < 1e-9)
        return {"service": service, "at": at, "curve": curve["points"], "optimum": curve["optimum"],
                "explain": "Higher service level -> more safety stock (holding cost rises steeply) but fewer "
                           "expected stock-outs (lost margin falls). Expected lost units per year = "
                           "(annual demand / order qty) x sigma_LT x G(z)."}

    # ------------------------------------------------------------ store-level
    def trend(self, days=150):
        ds = self.ds
        n = ds.n
        start = max(0, n - days)
        hist = []
        for t in range(start, n):
            rev = sum(ds.qty[s][t] * ds.items[s]["price"] for s in ds.skus)
            so = sum(1 for s in ds.skus if ds.stockout[s][t])
            hist.append({"date": ds.dates[t].isoformat(), "revenue": round(rev, 0), "stockouts": so,
                         "festival": festivals.label_for(ds.dates[t])})
        fc = []
        for i, d in enumerate(self.fc_dates):
            mu = sum(self.fc[s][self.chosen[s]][i] * ds.items[s]["price"] for s in ds.skus)
            sd = math.sqrt(sum((self.sigma[s] * ds.items[s]["price"]) ** 2 for s in ds.skus))
            fc.append({"date": d.isoformat(), "revenue": round(mu, 0), "lo": round(max(0, mu - BAND_Z * sd), 0),
                       "hi": round(mu + BAND_Z * sd, 0), "festival": festivals.label_for(d)})
        fests = festivals.in_range(ds.dates[start], self.fc_dates[-1])
        return {"history": hist, "forecast": fc, "festivals": fests,
                "band": "80% band (+/-1.28 sigma, errors assumed independent)"}

    def leaderboard(self):
        skus = self.ds.skus
        models = {}
        for m in config.MODEL_ORDER:
            sm = [self.bt[s]["models"][m]["smape"] for s in skus]
            mp = [self.bt[s]["models"][m]["mape"] for s in skus if self.bt[s]["models"][m]["mape"] is not None]
            models[m] = {"name": config.MODEL_NAMES[m], "wins": sum(1 for s in skus if self.chosen[s] == m),
                         "mean_smape": _r(sum(sm) / len(sm)), "mean_mape": _r(sum(mp) / len(mp)) if mp else None}
        per_sku = []
        for s in skus:
            b = self.bt[s]
            per_sku.append({"sku": s, "name": self.ds.items[s]["name"], "chosen": b["chosen"],
                            "smape": {m: b["models"][m]["smape"] for m in config.MODEL_ORDER},
                            "mape": {m: b["models"][m]["mape"] for m in config.MODEL_ORDER},
                            "gain_vs_naive": _r(b["models"]["snaive"]["smape"] - b["models"][b["chosen"]]["smape"])})
        return {"models": models, "per_sku": per_sku, "holdout": self.holdout(),
                "method": "%d rolling-origin folds x %d-day horizon (last %d days out of sample); best model per SKU "
                          "by %s." % (config.BACKTEST_FOLDS, config.BACKTEST_HORIZON,
                                      config.BACKTEST_FOLDS * config.BACKTEST_STEP, config.SELECT_METRIC.upper())}

    def holdout(self):
        """Model picked on folds 1-3, scored on the unseen last fold, vs seasonal naive."""
        sel, nai, sm_sel, sm_nai, mp_sel, mp_nai = [], [], [], [], [], []
        for s in self.ds.skus:
            b = self.bt[s]
            sel += b["holdout_pairs"]
            nai += b["holdout_naive_pairs"]
            ms = backtest.metrics([a for a, _ in b["holdout_pairs"]], [p for _, p in b["holdout_pairs"]])
            mn = backtest.metrics([a for a, _ in b["holdout_naive_pairs"]], [p for _, p in b["holdout_naive_pairs"]])
            sm_sel.append(ms["smape"])
            sm_nai.append(mn["smape"])
            if ms["mape"] is not None and mn["mape"] is not None:
                mp_sel.append(ms["mape"])
                mp_nai.append(mn["mape"])
        rev_sel = sum(abs(a - p) for a, p in sel)
        rev_nai = sum(abs(a - p) for a, p in nai)
        return {
            "wape": _r(backtest.wape(sel)), "wape_naive": _r(backtest.wape(nai)),
            "smape": _r(sum(sm_sel) / len(sm_sel)), "smape_naive": _r(sum(sm_nai) / len(sm_nai)),
            "mape": _r(sum(mp_sel) / len(mp_sel)) if mp_sel else None,
            "mape_naive": _r(sum(mp_nai) / len(mp_nai)) if mp_nai else None,
            "error_reduction_pct": _r(100 * (1 - rev_sel / rev_nai)) if rev_nai else None,
            "days": config.BACKTEST_HORIZON, "points": len(sel),
        }

    def festival_plan(self, days=45):
        ups = festivals.upcoming(self.today, days)
        out = []
        for f in ups:
            fd = festivals.parse_iso(f["date"])
            g = config.FESTIVAL_GROUPS.index(f["group"])
            win = [fd + timedelta(days=o) for o in sorted(config.FEST_SHAPE)]
            rows = []
            for s in self.ds.skus:
                u = self.uplift[s][f["group"]]
                if u <= 0.15:
                    continue
                extra = 0.0
                ctx = self.ctx[s]
                base_fc = self.fc[s][self.chosen[s]]
                for d in win:
                    i = (d - self.today).days
                    if 0 <= i < len(base_fc):
                        t = self.ds.n + i
                        shape = ctx.fest[t][g]
                        factor = ctx.fest_factor(t, self.uplift[s])
                        extra += base_fc[i] / factor * u * shape
                item = self.ds.items[s]
                order_by = win[0] - timedelta(days=item["lead_time"])
                rows.append({"sku": s, "name": item["name"], "uplift_pct": round(100 * u),
                             "extra_units": round(extra, 1), "extra_revenue": round(extra * item["price"], 0),
                             "order_by": order_by.isoformat()})
            rows.sort(key=lambda r: -r["extra_revenue"])
            out.append(dict(f, skus=rows[:12], extra_revenue=round(sum(r["extra_revenue"] for r in rows), 0),
                            in_horizon=f["days_away"] < config.FORECAST_HORIZON))
        return out

    def summary(self, service):
        ds, n = self.ds, self.ds.n
        last30 = sum(ds.qty[s][t] * ds.items[s]["price"] for s in ds.skus for t in range(n - 30, n))
        prev30 = sum(ds.qty[s][t] * ds.items[s]["price"] for s in ds.skus for t in range(n - 60, n - 30))
        fc28 = sum(self.fc[s][self.chosen[s]][i] * ds.items[s]["price"] for s in ds.skus
                   for i in range(config.FORECAST_HORIZON))
        so90 = sum(1 for s in ds.skus for t in range(max(0, n - 90), n) if ds.stockout[s][t])
        inv_value = sum(ds.on_hand[s]["on_hand"] * ds.items[s]["cost"] for s in ds.skus)
        plan = self.plan(service)
        sim = self.simulation(service) if self.sim_ready else None
        fest = self.festival_plan()
        return {
            "product": config.PRODUCT, "tagline": config.TAGLINE, "source": ds.source,
            "today": self.today.isoformat(), "history_start": ds.dates[0].isoformat(),
            "history_end": ds.dates[-1].isoformat(), "days": n, "skus": len(ds.skus),
            "revenue_30d": round(last30, 0), "revenue_prev_30d": round(prev30, 0),
            "revenue_change_pct": _r(100 * (last30 - prev30) / prev30, 1) if prev30 else None,
            "forecast_28d": round(fc28, 0), "stockout_days_90d": so90,
            "inventory_value": round(inv_value, 0), "reorder": plan["totals"],
            "holdout": self.holdout(), "wins": {m: sum(1 for s in ds.skus if self.chosen[s] == m)
                                                for m in config.MODEL_ORDER},
            "simulation": {"gut": sim["gut"], "stocksense": sim["stocksense"], "change_pct": sim["change_pct"],
                           "days": sim["days"]} if sim else None,
            "festivals": [{k: f[k] for k in ("name", "date", "days_away", "extra_revenue", "in_horizon")}
                          for f in fest],
            "warnings": ds.warnings, "build_seconds": self.build_seconds,
            "stockouts_detected": sum(ds.detected.values()) if not ds.stockout_given else None,
            "service": service, "model_names": config.MODEL_NAMES, "assumptions": assumptions(),
        }

    def skus(self, service):
        plan = {r["sku"]: r for r in self.plan(service)["rows"]}
        out = []
        for s in self.ds.skus:
            it = self.ds.items[s]
            b = self.bt[s]
            out.append({"sku": s, "name": it["name"], "category": it.get("category", ""),
                        "class": self.abc["per_sku"][s]["class"], "model": b["chosen"],
                        "smape": b["models"][b["chosen"]]["smape"], "status": plan[s]["status"],
                        "revenue": round(self.revenue[s], 0)})
        return out

    def sku_detail(self, sku, service, days=120):
        ds = self.ds
        if sku not in ds.items:
            return None
        n = ds.n
        start = max(0, n - days)
        item = ds.items[sku]
        b = self.bt[sku]
        chosen = b["chosen"]
        sigma = self.sigma[sku]
        fc = self.fc[sku][chosen]
        row = next(r for r in self.plan(service)["rows"] if r["sku"] == sku)
        pol = inventory.policy(item, fc, sigma, service)
        rules = [r for r in self.basket(config.MIN_SUPPORT, config.MIN_CONFIDENCE)["rules"]
                 if r["antecedent"] == [sku]][:6]
        names = {s: ds.items[s]["name"] for s in ds.skus}
        lb = []
        for m in config.MODEL_ORDER:
            mm = b["models"][m]
            lb.append(dict(mm, model=m, name=config.MODEL_NAMES[m], chosen=(m == chosen)))
        lb.sort(key=lambda r: r[config.SELECT_METRIC] if r[config.SELECT_METRIC] is not None else 1e9)
        naive = b["models"]["snaive"]["smape"]
        best = b["models"][chosen]["smape"]
        why = "%s won the backtest: sMAPE %.1f%% vs %.1f%% for seasonal naive over %d rolling folds." % (
            config.MODEL_NAMES[chosen], best, naive, len(b["splits"]))
        sim = None
        if self.sim_ready:
            res = self.simulation(service)
            r = next(x for x in res["rows"] if x["sku"] == sku)
            sim = dict(r, trajectory=res["trajectories"][sku], dates=res["dates"])
        return {
            "item": item, "class": self.abc["per_sku"][sku], "plan": row,
            "policy": {k: (_r(v, 3) if isinstance(v, float) else v) for k, v in pol.items()},
            "optimal_service": _r(inventory.optimal_service(item, pol["q_star"], pol["annual_demand"]), 4),
            "history": {
                "dates": [d.isoformat() for d in ds.dates[start:]],
                "qty": ds.qty[sku][start:], "clean": [round(v, 2) for v in ds.clean[sku][start:]],
                "stockout": [1 if f else 0 for f in ds.stockout[sku][start:]],
                "promo": ds.promo[sku][start:],
            },
            "forecast": {
                "dates": [d.isoformat() for d in self.fc_dates],
                "models": {m: [round(v, 2) for v in self.fc[sku][m]] for m in config.MODEL_ORDER},
                "chosen": chosen, "sigma": round(sigma, 3),
                "lo": [round(max(0.0, v - BAND_Z * sigma), 2) for v in fc],
                "hi": [round(v + BAND_Z * sigma, 2) for v in fc],
            },
            "leaderboard": lb, "why_model": why,
            "folds": [{"train_end": ds.dates[tr - 1].isoformat(), "test_start": ds.dates[tr].isoformat(),
                       "test_end": ds.dates[te - 1].isoformat()} for tr, te in b["splits"]],
            "uplift": {k: round(v, 3) for k, v in self.uplift[sku].items()},
            "uplift_detail": {g: {"raw": round(v["raw"], 3), "se": None if v["se"] is None else round(v["se"], 3)}
                              for g, v in self.ctx[sku].festival_uplift_detail(n).items()},
            "regression": explain_regression(self.coef[sku]),
            "basket": [dict(r, consequent_names=[names.get(c, c) for c in r["consequent"]]) for r in rules],
            "simulation": sim, "model_names": config.MODEL_NAMES,
        }


def assumptions():
    """Tunable assumptions shown in the UI (single source: config.py)."""
    return [
        {"name": "Ordering cost", "value": "₹%d per order line" % config.ORDER_COST,
         "note": "owner time + share of delivery (assumption)"},
        {"name": "Holding cost", "value": "%d%% of unit cost per year" % round(100 * config.HOLDING_RATE),
         "note": "capital + space + shrinkage (assumption)"},
        {"name": "Default service level", "value": "%.0f%%" % (100 * config.SERVICE_LEVEL),
         "note": "probability of not running out in a replenishment cycle"},
        {"name": "Review", "value": "daily, protection = lead time + %d day" % config.REVIEW_DAYS,
         "note": "stock checked every morning"},
        {"name": "Perishables", "value": "sell within %d%% of shelf life" % round(100 * config.SELLABLE_FRACTION),
         "note": "shelf life <= %d days" % config.PERISHABLE_DAYS},
        {"name": "Order cap", "value": "%d days of demand" % config.MAX_COVER_DAYS, "note": "limited cash and shelf space"},
        {"name": "Backtest", "value": "%d folds x %d days" % (config.BACKTEST_FOLDS, config.BACKTEST_HORIZON),
         "note": "rolling origin; model picked by %s" % config.SELECT_METRIC.upper()},
        {"name": "ABC / XYZ cut-offs", "value": "A<%d%%, B<%d%% revenue; X<%.2f, Y<%.2f weekly CV"
         % (100 * config.ABC_A, 100 * config.ABC_B, config.XYZ_X, config.XYZ_Y), "note": "Pareto x variability"},
        {"name": "Basket rules", "value": "support >= %.0f%%, confidence >= %.0f%%, lift >= %.1f"
         % (100 * config.MIN_SUPPORT, 100 * config.MIN_CONFIDENCE, config.MIN_LIFT), "note": "Apriori"},
        {"name": "Festival dates", "value": "approximate", "note": "Diwali, Pongal, Christmas, Tamil New Year, Ganesh Chaturthi"},
    ]


def _round_metrics(m):
    return {k: (round(v, 4) if k == "fill_rate" else round(v, 2)) for k, v in m.items()}


class Engine:
    """Holds the current Analysis; swaps it atomically when data is (re)loaded."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.overrides = {}
        self.analysis = None
        self._demo_items = {i["sku"]: catalog.public_item(i) for i in catalog.build_catalog()}
        self.load_demo()

    def _ensure_demo_files(self):
        need = ("sales_history.csv", "baskets.csv", "inventory.json", "catalog.json")
        if not all(os.path.exists(os.path.join(self.data_dir, f)) for f in need):
            synth.write_all(self.data_dir)

    def _read(self, name):
        with open(os.path.join(self.data_dir, name), encoding="utf-8") as f:
            return f.read()

    def _demo_parts(self):
        import json
        self._ensure_demo_files()
        inv = json.loads(self._read("inventory.json"))
        baskets = dataset.parse_baskets(self._read("baskets.csv"))
        return inv, baskets

    def load_demo(self):
        inv, baskets = self._demo_parts()
        ds = dataset.parse_csv(self._read("sales_history.csv"), base_items=self._demo_items,
                               base_on_hand=inv, source="demo", baskets=baskets)
        ds.warnings = []
        a = Analysis(ds)
        with self.lock:
            self.analysis = a
            self.overrides = {}
        return a

    def load_csv(self, text):
        inv, baskets = self._demo_parts()
        ds = dataset.parse_csv(text, base_items=self._demo_items, base_on_hand=None, source="upload",
                               baskets=baskets)
        a = Analysis(ds)
        with self.lock:
            self.analysis = a
            self.overrides = {}
        return a

    def set_stock(self, sku, on_hand, on_order=0):
        a = self.analysis
        if sku not in a.ds.items:
            raise KeyError(sku)
        with self.lock:
            a.ds.on_hand[sku] = {"on_hand": int(on_hand), "on_order": int(on_order), "assumed": False}
        return a.plan(config.SERVICE_LEVEL)

    def sample_csv(self, days=200):
        a = self.analysis if self.analysis.ds.source == "demo" else None
        text = self._read("sales_history.csv")
        lines = text.splitlines()
        if a is None:
            return text
        cutoff = a.ds.dates[-days].isoformat()
        return "\n".join([lines[0]] + [ln for ln in lines[1:] if ln[:10] >= cutoff]) + "\n"
