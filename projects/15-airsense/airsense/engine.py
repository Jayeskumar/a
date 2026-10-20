"""AirSense pipeline: load data -> calibrate -> QA -> AQI -> interpolate -> forecast -> sources.

Pure logic (no HTTP). The web layer calls the methods at the bottom of Network.
"""

import math
import random
import threading
import time

from . import aqi as A
from . import calibration, faults, forecast, health, interpolate, simulate, sources
from . import config as C
from .mathx import dist, errors, mean, median

FIELD_KEYS = ("pm25", "pm10")


class NotFound(KeyError):
    pass


class BadRequest(ValueError):
    pass


def _r(v, nd=1):
    return None if v is None else round(v, nd)


class Network:
    def __init__(self, data_dir, regenerate=False):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.reload(regenerate)

    # ================================================================ loading
    def reload(self, regenerate=False):
        with self.lock:
            t0 = time.time()
            if regenerate or not simulate.files_present(self.data_dir):
                simulate.write(self.data_dir)
            self._parse(simulate.read(self.data_dir))
            self.timings = {}
            self._run()
            self.compute_ms = int((time.time() - t0) * 1000)

    def _parse(self, raw):
        meta = raw["meta"]
        self.meta = meta
        self.n = int(meta["field_hours"])
        self.nc = int(meta["coloc_hours"])
        self.sensors = [{"id": s["id"], "name": s["name"], "x": s["x"], "y": s["y"],
                         "coloc": s["coloc"]} for s in meta["sensors"]]
        self.sensor_by_id = {s["id"]: s for s in self.sensors}
        self.refs = meta["references"]
        self.ref_by_id = {r["id"]: r for r in self.refs}
        self.injected = meta["faults"]
        self.events = meta["events"]
        n = self.n
        num = simulate._num
        self.raw = {k: {s["id"]: [None] * n for s in self.sensors} for k in ("pm25", "pm10", "temp", "rh")}
        for h, sid, r25, r10, t, rh in raw["field"]:
            h = int(h)
            self.raw["pm25"][sid][h] = num(r25)
            self.raw["pm10"][sid][h] = num(r10)
            self.raw["temp"][sid][h] = num(t)
            self.raw["rh"][sid][h] = num(rh)
        self.coloc = {s["id"]: [] for s in self.sensors}
        for h, sid, st, r25, r10, t, rh in raw["coloc"]:
            self.coloc[sid].append((int(h), st, num(r25), num(r10), num(t), num(rh)))
        self.ref = {r["id"]: {p: [None] * (self.nc + n) for p in C.POLLUTANT_ORDER} for r in self.refs}
        for row in raw["reference"]:
            h = int(row[0])
            for p, v in zip(simulate.POLL, row[2:]):
                self.ref[row[1]][p][h + self.nc] = num(v)
        wx = {"temp": [], "rh": [], "wdir": [], "ws": [], "rain": [], "kind": []}
        for h, t, rh, wd, ws, rain, kind in raw["weather"]:
            if int(h) < 0:
                continue
            wx["temp"].append(float(t))
            wx["rh"].append(float(rh))
            wx["wdir"].append(float(wd))
            wx["ws"].append(float(ws))
            wx["rain"].append(float(rain))
            wx["kind"].append(kind)
        self.nw = len(wx["ws"])            # field hours + 24 forecast hours
        self.dts = [simulate.hour_label(h) for h in range(self.nw)]
        wx["sunday"] = [d.weekday() == 6 for d in self.dts]
        self.hods = [d.hour for d in self.dts]
        self.wx = wx
        self.labels = [d.strftime("%a %d %b %H:00") for d in self.dts]
        self.truth = {s["id"]: ([None] * n, [None] * n) for s in self.sensors}
        for h, sid, t25, t10 in raw["truth"]:
            self.truth[sid][0][int(h)] = float(t25)
            self.truth[sid][1][int(h)] = float(t10)

    def ref_series(self, station, p, field_only=True):
        s = self.ref[station][p]
        return s[self.nc:] if field_only else s

    # ================================================================ pipeline
    def _tick(self, name, t0):
        self.timings[name] = int((time.time() - t0) * 1000)
        return time.time()

    def _run(self):
        t = time.time()
        self._calibrate()
        t = self._tick("calibration", t)
        self._qa()
        t = self._tick("fault_detection", t)
        self._aqi()
        t = self._tick("aqi", t)
        self._interp()
        t = self._tick("interpolation", t)
        self._forecast()
        t = self._tick("forecast", t)
        self._sources()
        t = self._tick("sources", t)

    # ---------------------------------------------------------------- calibration
    def _calibrate(self):
        split = -self.nc + C.COLOC_TRAIN_DAYS * 24
        self.cal_models = {}
        self.cal_report = []
        self.cal = {k: {} for k in FIELD_KEYS}
        for s in self.sensors:
            sid = s["id"]
            entry = {"sensor": sid, "name": s["name"], "station": s["coloc"]}
            for idx, p in ((2, "pm25"), (3, "pm10")):
                samples = []
                for row in self.coloc[sid]:
                    h, st = row[0], row[1]
                    ref = self.ref[st][p][h + self.nc]
                    samples.append((h, (row[idx], row[5], row[4], ref)))
                train = [x for h, x in samples if h < split]
                test = [x for h, x in samples if h >= split]
                res = calibration.calibrate_sensor(train, test)
                self.cal_models[(sid, p)] = res["model"]
                entry[p] = {"model": res["model"], "mlr": res["mlr"], "test": res["test"]}
                self.cal[p][sid] = [calibration.apply(res["model"], r, rh, tt) for r, rh, tt in
                                    zip(self.raw[p][sid], self.raw["rh"][sid], self.raw["temp"][sid])]
            self.cal_report.append(entry)

    # ---------------------------------------------------------------- QA
    def _qa(self):
        res = faults.run(self.sensors, self.raw["pm25"], self.cal["pm25"], self.n)
        self.qa = res
        self.flagged = res["flagged"]
        self.fault_events = res["events"]
        self.clean = {}
        for p in FIELD_KEYS:
            self.clean[p] = {sid: [None if (sid, t) in self.flagged else v for t, v in enumerate(vals)]
                             for sid, vals in self.cal[p].items()}
        self.flag_type = {}
        for e in self.fault_events:
            for t in range(e["start_hour"], e["end_hour"] + 1):
                self.flag_type.setdefault((e["sensor"], t), e["type"])
        self.fault_eval = faults.evaluate(self.fault_events, self.injected, self.n)
        self.spike_sweep = self._spike_sweep()
        for e in self.fault_events:
            e["matches_injected"] = any(
                i["sensor"] == e["sensor"] and i["start_hour"] <= e["end_hour"] and
                i["end_hour"] >= e["start_hour"] for i in self.injected)

    def _spike_sweep(self):
        """Precision/recall of the spike rule across thresholds (honest trade-off)."""
        inj = [e for e in self.injected if e["type"] == "spike"]
        stuck = set(k for k, v in self.flag_type.items() if v == "stuck")
        out = []
        for z in (6, 8, 10, 12, 15, 20, 30, 45):
            det = []
            for s in self.sensors:
                sid = s["id"]
                series = [None if (sid, t) in stuck else self.cal["pm25"][sid][t] for t in range(self.n)]
                for sp in faults.detect_spikes(series, self.qa["neighbour_median"][sid], z=z):
                    det.append({"sensor": sid, "type": "spike", "start_hour": sp["hour"], "end_hour": sp["hour"]})
            ev = faults.evaluate(det, inj, self.n)["spike"]
            out.append({"z": z, "detected": len(det), "precision": ev["event_precision"],
                        "recall": ev["event_recall"]})
        return out

    # ---------------------------------------------------------------- AQI
    def nearest_ref(self, x, y):
        return min(self.refs, key=lambda r: dist(r["x"], r["y"], x, y))

    def _aqi(self):
        n = self.n
        self.aqi1 = {}
        self.aqi24 = {}
        self.avg = {p: {} for p in FIELD_KEYS}
        # reference stations: official-style AQI series (needs prior day -> include coloc week)
        self.ref_avg = {}
        self.ref_aqi = {}
        for r in self.refs:
            avg = {p: A.averaged(p, self.ref[r["id"]][p])[self.nc:] for p in C.POLLUTANT_ORDER}
            self.ref_avg[r["id"]] = avg
            series = []
            for t in range(n):
                subs = {p: (A.sub_index(p, avg[p][t]) if avg[p][t] is not None else None)
                        for p in C.POLLUTANT_ORDER}
                o = A.overall(subs)
                series.append(o)
            self.ref_aqi[r["id"]] = series
        for s in self.sensors:
            sid = s["id"]
            p25, p10 = self.clean["pm25"][sid], self.clean["pm10"][sid]
            self.aqi1[sid] = [A.hourly_indicative(a, b) if (a is not None or b is not None) else None
                              for a, b in zip(p25, p10)]
            a25, a10 = A.average_24h(p25), A.average_24h(p10)
            self.avg["pm25"][sid], self.avg["pm10"][sid] = a25, a10
            ref = self.nearest_ref(s["x"], s["y"])["id"]
            gas = self.ref_avg[ref]
            out = []
            for t in range(n):
                subs = {"pm25": A.sub_index("pm25", a25[t]) if a25[t] is not None else None,
                        "pm10": A.sub_index("pm10", a10[t]) if a10[t] is not None else None}
                for g in ("no2", "so2", "co", "o3", "nh3"):
                    subs[g] = A.sub_index(g, gas[g][t]) if gas[g][t] is not None else None
                o = A.overall(subs)
                out.append(o["aqi"] if o["valid"] else None)
            self.aqi24[sid] = out
        # hidden exposure: local hourly AQI above 100 while the nearest official station
        # (one station for the whole town) still shows Good/Satisfactory
        ref1 = {r["id"]: [A.hourly_indicative(a, b) if a is not None else None for a, b in
                          zip(self.ref_series(r["id"], "pm25"), self.ref_series(r["id"], "pm10"))]
                for r in self.refs}
        unhealthy = hidden = 0
        per = []
        for s in self.sensors:
            rid = "REF-A"   # the town's single official station
            u = h_ = 0
            for t in range(n):
                a, b = self.aqi1[s["id"]][t], ref1[rid][t]
                if a is None or b is None:
                    continue
                if a > 100:
                    u += 1
                    if b <= 100:
                        h_ += 1
            unhealthy += u
            hidden += h_
            per.append({"sensor": s["id"], "name": s["name"], "unhealthy_hours": u, "missed_by_station": h_})
        per.sort(key=lambda r: -r["missed_by_station"])
        self.hidden = {"unhealthy_sensor_hours": unhealthy, "missed_by_station": hidden,
                       "missed_pct": _r(hidden / unhealthy * 100, 1) if unhealthy else None,
                       "station": "REF-A", "top": per[:6],
                       "definition": "Sensor-hours with local hourly AQI > 100 while the town's "
                                     "official station (REF-A) showed 100 or less"}

    def snapshot(self, t, p="pm25", avg=False):
        src = self.avg[p] if avg else self.clean[p]
        return [(s["x"], s["y"], src[s["id"]][t]) for s in self.sensors if src[s["id"]][t] is not None]

    # ---------------------------------------------------------------- interpolation
    def _interp(self):
        snaps = [self.snapshot(t) for t in range(0, self.n, 3)]
        self.vario_bins = interpolate.empirical_variogram(snaps)
        self.vario = interpolate.fit_variogram(self.vario_bins)
        res = {k: [] for k in ("idw1", "idw2", "idw3", "kriging", "nearest_ref")}
        truth = []
        cat_hits = {k: 0 for k in res}
        cat_n = 0
        for t in range(0, self.n, 4):
            pts = self.snapshot(t)
            if len(pts) < 10:
                continue
            k = interpolate.Kriging(pts, self.vario, interpolate.snapshot_scale(pts))
            kres = k.loo_residuals()
            preds = {"kriging": [max(0.0, p[2] - e) for p, e in zip(pts, kres)]}
            for pw in (1, 2, 3):
                preds["idw%d" % pw] = interpolate.idw_loo(pts, pw)
            preds["nearest_ref"] = []
            for x, y, v in pts:
                r = self.nearest_ref(x, y)
                preds["nearest_ref"].append(self.ref_series(r["id"], "pm25")[t])
            for i, (x, y, v) in enumerate(pts):
                truth.append(v)
                ci = A.category_index(A.sub_index("pm25", v))
                cat_n += 1
                for name, pv in preds.items():
                    pv_i = pv[i]
                    res[name].append(pv_i)
                    if pv_i is not None and A.category_index(A.sub_index("pm25", pv_i)) == ci:
                        cat_hits[name] += 1
        self.interp_eval = {name: dict(errors(v, truth), category_accuracy=cat_hits[name] / cat_n)
                            for name, v in res.items()}
        self.interp_eval["hours_evaluated"] = len(range(0, self.n, 4))

    # ---------------------------------------------------------------- forecast
    def _noisy_weather(self, origin, cache):
        if origin in cache:
            return cache[origin]
        rng = random.Random(C.SEED * 1000 + origin)
        w = {k: list(v) for k, v in self.wx.items() if k in ("ws", "rain", "rh", "wdir", "sunday")}
        for k in range(1, 25):
            t = origin + k
            if t >= self.nw:
                break
            sd = 0.08 + 0.01 * k
            w["ws"][t] = max(0.3, w["ws"][t] * math.exp(rng.gauss(0, sd)))
            w["wdir"][t] = (w["wdir"][t] + rng.gauss(0, 10 + k)) % 360
            w["rh"][t] = min(99.0, max(30.0, w["rh"][t] + rng.gauss(0, 2 + 0.2 * k)))
            w["rain"][t] = max(0.0, w["rain"][t] * math.exp(rng.gauss(0, 0.3)))
        cache[origin] = w
        return w

    def _forecast(self):
        n = self.n
        train_end = n - C.FORECAST_HOLDOUT_DAYS * 24
        cache = {}
        wx_hist = {k: v for k, v in self.wx.items()}
        pairs = [[] for _ in range(24)]            # (pred, actual, persistence, seasonal)
        log_errs = {p: [[] for _ in range(24)] for p in FIELD_KEYS}
        for p in FIELD_KEYS:
            for s in self.sensors:
                vals = self.clean[p][s["id"]] + [None] * (self.nw - n)
                fc = forecast.SensorForecaster(vals, self.hods, wx_hist, train_end)
                origin = train_end - 1
                while origin + 24 < n:
                    cur = vals[origin]
                    if cur is not None:
                        pred = fc.forecast(origin, 24, self._noisy_weather(origin, cache))
                        for k in range(1, 25):
                            act = vals[origin + k]
                            if act is None:
                                continue
                            log_errs[p][k - 1].append(forecast.to_log(act) - forecast.to_log(pred[k - 1]))
                            if p == "pm25":
                                pairs[k - 1].append((pred[k - 1], act, cur, vals[origin + k - 24]))
                    origin += C.FORECAST_ORIGIN_STEP_H
        self.fc_quant = {p: forecast.interval_quantiles(log_errs[p]) for p in FIELD_KEYS}
        by_h = []
        allp = {"model": [], "persistence": [], "seasonal": []}
        alla = {"model": [], "persistence": [], "seasonal": []}
        for k in range(24):
            row = {"h": k + 1}
            for name, idx in (("model", 0), ("persistence", 2), ("seasonal", 3)):
                e = [abs(pr[idx] - pr[1]) for pr in pairs[k] if pr[idx] is not None]
                row[name] = _r(mean(e), 2)
                allp[name].extend(e)
                alla[name].extend(abs(A.sub_index("pm25", pr[idx]) - A.sub_index("pm25", pr[1]))
                                  for pr in pairs[k] if pr[idx] is not None)
            by_h.append(row)
        q = self.fc_quant["pm25"]
        cover = []
        for k in range(24):
            for pr in pairs[k]:
                lo = forecast.from_log(forecast.to_log(pr[0]) + q[k][0])
                hi = forecast.from_log(forecast.to_log(pr[0]) + q[k][1])
                cover.append(lo <= pr[1] <= hi)
        self.fc_eval = {
            "by_horizon": by_h,
            "mae": {k: _r(mean(v), 2) for k, v in allp.items()},
            "mae_aqi": {k: _r(mean(v), 1) for k, v in alla.items()},
            "n_forecasts": len(pairs[0]),
            "interval_coverage_80": _r(sum(cover) / len(cover) * 100, 1) if cover else None,
            "holdout_days": C.FORECAST_HOLDOUT_DAYS, "train_days": train_end // 24,
            "origin_step_h": C.FORECAST_ORIGIN_STEP_H,
        }
        m, pe = self.fc_eval["mae"]["model"], self.fc_eval["mae"]["persistence"]
        self.fc_eval["improvement_vs_persistence_pct"] = _r((1 - m / pe) * 100, 1) if pe else None
        # live forecasts from the last hour, trained on all data
        self.live = {}
        self.fc_models = {}
        for s in self.sensors:
            sid = s["id"]
            out = {}
            for p in FIELD_KEYS:
                vals = self.clean[p][sid] + [None] * (self.nw - n)
                fc = forecast.SensorForecaster(vals, self.hods, self.wx, n)
                pred = fc.forecast(n - 1, 24)
                qq = self.fc_quant[p]
                lo = [forecast.from_log(forecast.to_log(v) + qq[k][0]) for k, v in enumerate(pred)]
                hi = [forecast.from_log(forecast.to_log(v) + qq[k][1]) for k, v in enumerate(pred)]
                out[p] = {"mean": pred, "lo": lo, "hi": hi}
                self.fc_models[(sid, p)] = fc
            last = next((v for v in reversed(self.clean["pm25"][sid]) if v is not None), None)
            out["persistence"] = last
            out["stale"] = self.clean["pm25"][sid][n - 1] is None
            self.live[sid] = out

    # ---------------------------------------------------------------- sources
    def _sources(self):
        n = self.n
        ids = [s["id"] for s in self.sensors]
        vals = self.clean["pm25"]
        bg = sources.network_background(vals, ids, n, set())
        self.bg = bg
        wd, ws = self.wx["wdir"][:n], self.wx["ws"][:n]
        self.roses = {}
        for s in self.sensors:
            r = sources.rose(vals[s["id"]], bg, wd, ws, set(), s["id"])
            r["upwind"] = (sources.landmark_upwind(s["x"], s["y"], r["peak_dir"])
                           if r["peak_dir"] is not None else [])
            self.roses[s["id"]] = r
        self.cwt = sources.cwt_grid(vals, self.sensors, bg, wd, ws, set(), n)
        self.hotspots = sources.hotspots(self.cwt)
        loc = []
        for lm in C.LANDMARKS:
            if lm["kind"] in ("green",) or lm["id"] == "highway" or "x" not in lm:
                continue
            ds = [dist(h["x"], h["y"], lm["x"], lm["y"]) for h in self.hotspots]
            loc.append({"landmark": lm["name"], "id": lm["id"],
                        "nearest_hotspot_km": _r(min(ds), 2) if ds else None})
        self.source_eval = loc

    # ================================================================ API views
    def check_hour(self, hour):
        if hour is None:
            return self.n - 1
        if not 0 <= hour < self.n:
            raise BadRequest("hour must be between 0 and %d" % (self.n - 1))
        return hour

    def sensor(self, sid):
        s = self.sensor_by_id.get(sid)
        if s is None:
            raise NotFound(sid)
        return s

    def summary_now(self, t=None):
        t = self.check_hour(t)
        vals = [self.aqi1[s["id"]][t] for s in self.sensors if self.aqi1[s["id"]][t] is not None]
        v24 = [self.aqi24[s["id"]][t] for s in self.sensors if self.aqi24[s["id"]][t] is not None]
        worst = max(self.sensors, key=lambda s: self.aqi1[s["id"]][t] or -1)
        best = min(self.sensors, key=lambda s: self.aqi1[s["id"]][t] if self.aqi1[s["id"]][t] is not None else 999)
        ref = self.ref_aqi["REF-A"][t]
        return {"hour": t, "label": self.labels[t], "median_aqi_1h": median(vals),
                "median_aqi_24h": median(v24), "spread": [min(vals), max(vals)] if vals else None,
                "worst": {"id": worst["id"], "name": worst["name"], "aqi": self.aqi1[worst["id"]][t]},
                "best": {"id": best["id"], "name": best["name"], "aqi": self.aqi1[best["id"]][t]},
                "official_station_aqi": ref["aqi"], "official_station_valid": ref["valid"],
                "official_station_prominent": ref["prominent"]}

    def health_info(self):
        return {"status": "ok", "hours": self.n, "sensors": len(self.sensors),
                "reference_stations": len(self.refs), "compute_ms": self.compute_ms,
                "timings_ms": self.timings, "seed": self.meta["seed"]}

    def meta_view(self):
        cats = [{k: c[k] for k in ("key", "name", "lo", "hi", "color", "ink", "health")} for c in C.CATEGORIES]
        knots = {p: A._KNOTS[p] for p in ("pm25", "pm10")}
        return {
            "map": {"w_km": C.MAP_W_KM, "h_km": C.MAP_H_KM, "highway": C.HIGHWAY,
                    "landmarks": C.LANDMARKS, "town": "Demo town (Tiruchengode-like layout, synthetic)"},
            "sensors": [dict(s, neighbours=self.qa["neighbours"][s["id"]],
                             faulty_now=(s["id"], self.n - 1) in self.flagged,
                             fault_now=self.flag_type.get((s["id"], self.n - 1)))
                        for s in self.sensors],
            "references": self.refs, "events": self.events, "categories": cats,
            "knots": knots, "profiles": {k: v["name"] for k, v in C.PROFILES.items()},
            "profileAdvice": {k: v["advice"] for k, v in C.PROFILES.items()},
            "profileThreshold": {k: v["alert_from"] for k, v in C.PROFILES.items()},
            "breakpoints": C.BREAKPOINTS,
            "pollutants": {k: list(v) for k, v in C.POLLUTANTS.items()},
            "hours": self.n, "labels": self.labels, "now": self.n - 1,
            "forecast_labels": self.labels[self.n:self.n + 24],
            "aqi_source": C.AQI_SOURCE, "summary": self.summary_now(),
            "metrics": self.headline(),
        }

    def headline(self):
        c = self.calibration_summary()
        fe = self.fault_eval["overall"]
        return {"calibration_rmse_reduction_pct": c["pm25"]["rmse_reduction_pct"],
                "fault_precision": fe["event_precision"], "fault_recall": fe["event_recall"],
                "forecast_mae": self.fc_eval["mae"]["model"],
                "persistence_mae": self.fc_eval["mae"]["persistence"],
                "forecast_gain_pct": self.fc_eval["improvement_vs_persistence_pct"],
                "kriging_mae": _r(self.interp_eval["kriging"]["mae"], 2),
                "nearest_station_mae": _r(self.interp_eval["nearest_ref"]["mae"], 2),
                "faults_detected": len(self.fault_events),
                "hidden_exposure_pct": self.hidden["missed_pct"]}

    def frames(self):
        n = self.n
        ids = [s["id"] for s in self.sensors]
        codes = {"stuck": 1, "spike": 2, "drift": 3}
        out = {"sensors": ids, "hours": n, "pm25": [], "pm10": [], "aqi": [], "aqi24": [],
               "pm25_24": [], "pm10_24": [], "flag": [], "missing": [],
               "wind": [[round(self.wx["wdir"][t]), round(self.wx["ws"][t], 1)] for t in range(n)],
               "rain": [round(self.wx["rain"][t], 1) for t in range(n)],
               "ref_aqi": {r["id"]: [o["aqi"] for o in self.ref_aqi[r["id"]]] for r in self.refs},
               "ref_pm25": {r["id"]: [_r(v) for v in self.ref_series(r["id"], "pm25")] for r in self.refs}}
        for t in range(n):
            out["pm25"].append([_r(self.clean["pm25"][s][t]) for s in ids])
            out["pm10"].append([_r(self.clean["pm10"][s][t]) for s in ids])
            out["pm25_24"].append([_r(self.avg["pm25"][s][t]) for s in ids])
            out["pm10_24"].append([_r(self.avg["pm10"][s][t]) for s in ids])
            out["aqi"].append([self.aqi1[s][t] for s in ids])
            out["aqi24"].append([self.aqi24[s][t] for s in ids])
            out["flag"].append([codes.get(self.flag_type.get((s, t)), 0) for s in ids])
            out["missing"].append([1 if self.raw["pm25"][s][t] is None else 0 for s in ids])
        return out

    def _forecast_block(self, pm25, pm10, lo25, hi25, lo10, hi10):
        aqi = [A.hourly_indicative(a, b) for a, b in zip(pm25, pm10)]
        lo = [A.hourly_indicative(a, b) for a, b in zip(lo25, lo10)]
        hi = [A.hourly_indicative(a, b) for a, b in zip(hi25, hi10)]
        return aqi, lo, hi

    def sensor_view(self, sid):
        s = self.sensor(sid)
        n = self.n
        cal = next(c for c in self.cal_report if c["sensor"] == sid)
        ref = self.nearest_ref(s["x"], s["y"])
        colocated = dist(ref["x"], ref["y"], s["x"], s["y"]) < 0.05
        t_last = max((t for t in range(n) if self.raw["pm25"][sid][t] is not None), default=n - 1)
        expl = calibration.explain(self.cal_models[(sid, "pm25")], self.raw["pm25"][sid][t_last],
                                   self.raw["rh"][sid][t_last], self.raw["temp"][sid][t_last])
        ev = [e for e in self.fault_events if e["sensor"] == sid]
        view = {
            "sensor": s, "nearest_reference": ref["id"], "colocated": colocated,
            "raw_pm25": [_r(v) for v in self.raw["pm25"][sid]],
            "cal_pm25": [_r(v) for v in self.cal["pm25"][sid]],
            "cal_pm10": [_r(v) for v in self.cal["pm10"][sid]],
            "ref_pm25": [_r(v) for v in self.ref_series(ref["id"], "pm25")],
            "rh": self.raw["rh"][sid], "aqi": self.aqi1[sid], "aqi24": self.aqi24[sid],
            "flags": [self.flag_type.get((sid, t)) for t in range(n)],
            "events": ev,
            "calibration": {"pm25": self._cal_view(cal["pm25"]), "pm10": self._cal_view(cal["pm10"]),
                            "station": cal["station"], "example": dict(expl, hour=t_last,
                                                                       label=self.labels[t_last])},
            "rose": self.roses[sid],
            "forecast": self.forecast_view(sid=sid),
        }
        if colocated:
            pairs = [(r, c, f) for r, c, f in zip(self.raw["pm25"][sid], self.cal["pm25"][sid],
                                                  self.ref_series(ref["id"], "pm25"))]
            view["field_validation"] = {
                "raw": self._err([p[0] for p in pairs], [p[2] for p in pairs]),
                "calibrated": self._err([p[1] for p in pairs], [p[2] for p in pairs])}
        return view

    @staticmethod
    def _err(pred, truth):
        e = errors(pred, truth)
        return {k: (_r(v, 2) if isinstance(v, float) else v) for k, v in e.items()}

    def _cal_view(self, c):
        m = c["model"]
        return {"kappa": m["kappa"], "intercept": _r(m["intercept"], 3),
                "coef": dict(zip(m["features"], [_r(v, 4) for v in m["coef"]])),
                "n_train": m["n_train"],
                "test": {k: {kk: _r(vv, 2) if isinstance(vv, float) else vv for kk, vv in e.items()}
                         for k, e in c["test"].items()}}

    def forecast_view(self, sid=None, x=None, y=None, profile="general"):
        health.profile(profile)
        n = self.n
        if sid is not None:
            self.sensor(sid)
            L = self.live[sid]
            p25, p10 = L["pm25"], L["pm10"]
            m25, m10 = p25["mean"], p10["mean"]
            lo25, hi25, lo10, hi10 = p25["lo"], p25["hi"], p10["lo"], p10["hi"]
            where = self.sensor_by_id[sid]["name"]
            persistence = L["persistence"]
            contrib = self.fc_models[(sid, "pm25")].contributions(n - 1)
            stale = L["stale"]
        else:
            if x is None or y is None:
                raise BadRequest("give sensor id or x and y")
            pts = [(s["x"], s["y"], s["id"]) for s in self.sensors if not self.live[s["id"]]["stale"]]
            ws = interpolate.idw_weights([(a, b, 0) for a, b, _ in pts], x, y)

            def blend(p, key):
                return [sum(w * self.live[i][p][key][k] for w, (_, _, i) in zip(ws, pts)) for k in range(24)]
            m25, m10 = blend("pm25", "mean"), blend("pm10", "mean")
            lo25, hi25 = blend("pm25", "lo"), blend("pm25", "hi")
            lo10, hi10 = blend("pm10", "lo"), blend("pm10", "hi")
            where = "%.1f km E, %.1f km N" % (x, y)
            persistence = sum(w * (self.live[i]["persistence"] or 0) for w, (_, _, i) in zip(ws, pts))
            contrib = []
            stale = False
        aqi, lo, hi = self._forecast_block(m25, m10, lo25, hi25, lo10, hi10)
        labels = self.labels[n:n + 24]
        hods = self.hods[n:n + 24]
        short = [lab[-5:] for lab in labels]
        best = health.best_run(hods, aqi, hi, short, profile_key=profile)
        al = health.alerts(list(range(n, n + 24)), aqi, profile, short, upper=hi)
        now_aqi = aqi[0]
        return {"where": where, "labels": labels, "hods": hods,
                "pm25": [_r(v) for v in m25], "pm25_lo": [_r(v) for v in lo25],
                "pm25_hi": [_r(v) for v in hi25], "pm10": [_r(v) for v in m10],
                "aqi": aqi, "aqi_lo": lo, "aqi_hi": hi,
                "persistence_pm25": _r(persistence), "best_run": best, "alerts": al,
                "advice_next_hour": health.advice(now_aqi, profile),
                "peak": {"aqi": max(aqi), "label": labels[aqi.index(max(aqi))]},
                "contributions": contrib, "stale": stale, "profile": profile,
                "weather": [{"ws": round(self.wx["ws"][t], 1), "wdir": round(self.wx["wdir"][t]),
                             "rain": round(self.wx["rain"][t], 1)} for t in range(n, n + 24)],
                "note": "Hourly AQI here applies CPCB breakpoints to 1-hour forecasts: indicative "
                        "only (official AQI uses 24-h / 8-h averages)."}

    def estimate(self, x, y, hour=None):
        if not (0 <= x <= C.MAP_W_KM and 0 <= y <= C.MAP_H_KM):
            raise BadRequest("x must be 0-%g and y 0-%g km" % (C.MAP_W_KM, C.MAP_H_KM))
        t = self.check_hour(hour)
        out = {"x": x, "y": y, "hour": t, "label": self.labels[t]}
        for p in FIELD_KEYS:
            pts = self.snapshot(t, p)
            if len(pts) < 3:
                raise BadRequest("not enough valid sensors at that hour")
            k = interpolate.Kriging(pts, self.vario, interpolate.snapshot_scale(pts))
            ek, sk, wk = k.predict(x, y)
            out[p] = {"idw": _r(interpolate.idw(pts, x, y)), "kriging": _r(max(0.0, ek)),
                      "sd": _r(sk), "lo": _r(max(0.0, ek - 1.645 * sk)), "hi": _r(ek + 1.645 * sk)}
        e25, e10 = out["pm25"], out["pm10"]
        aqi = A.hourly_indicative(e25["kriging"], e10["kriging"])
        out["aqi"] = aqi
        out["aqi_lo"] = A.hourly_indicative(e25["lo"], e10["lo"])
        out["aqi_hi"] = A.hourly_indicative(e25["hi"], e10["hi"])
        s25 = A.sub_index("pm25", e25["kriging"])
        s10 = A.sub_index("pm10", e10["kriging"])
        out["prominent"] = "PM2.5" if s25 >= s10 else "PM10"
        out["sub_indices"] = {"pm25": round(s25), "pm10": round(s10)}
        cat = A.category(aqi)
        out["category"] = cat["name"]
        out["color"] = cat["color"]
        out["health"] = cat["health"]
        pts = [(s["x"], s["y"], s["id"]) for s in self.sensors if self.clean["pm25"][s["id"]][t] is not None]
        w = interpolate.idw_weights([(a, b, 0) for a, b, _ in pts], x, y)
        top = sorted(zip(w, pts), reverse=True)[:4]
        out["nearest"] = [{"id": i, "name": self.sensor_by_id[i]["name"], "km": _r(dist(a, b, x, y), 2),
                           "weight": _r(wt, 3), "pm25": _r(self.clean["pm25"][i][t])}
                          for wt, (a, b, i) in top]
        out["nearest_km"] = out["nearest"][0]["km"] if out["nearest"] else None
        out["method_note"] = ("Ordinary kriging (exponential variogram, range %.1f km) with 90%% "
                              "interval from the kriging variance; IDW (p=2) shown for comparison."
                              % self.vario["range"])
        return out

    def grid_view(self, hour=None, method="kriging", field="pm25", nx=40, ny=30):
        if method not in ("kriging", "idw"):
            raise BadRequest("method must be kriging or idw")
        if field not in FIELD_KEYS:
            raise BadRequest("field must be pm25 or pm10")
        t = self.check_hour(hour)
        pts = self.snapshot(t, field)
        g = interpolate.grid(pts, method, nx, ny, vario=self.vario)
        g.update({"hour": t, "label": self.labels[t], "method": method, "field": field})
        return g

    def faults_view(self):
        return {"events": self.fault_events, "evaluation": self.fault_eval,
                "spike_threshold_sweep": self.spike_sweep,
                "injected": self.injected, "drift_sigma": _r(self.qa["drift"]["sigma"], 4),
                "rules": {"stuck_min_run_h": C.STUCK_MIN_RUN, "spike_z": C.SPIKE_Z,
                          "spike_spatial_ratio": C.SPIKE_SPATIAL_RATIO,
                          "spike_min_excess": C.SPIKE_MIN_EXCESS, "drift_z": C.DRIFT_Z,
                          "drift_min_days": C.DRIFT_MIN_DAYS, "neighbours": C.NEIGHBOURS_K}}

    def sources_view(self):
        roses = []
        for s in self.sensors:
            r = self.roses[s["id"]]
            roses.append({"id": s["id"], "name": s["name"], "x": s["x"], "y": s["y"],
                          "peak_dir": r["peak_dir"], "peak_label": r["peak_label"],
                          "peak_excess": r["peak_excess"], "peak_ratio": r["peak_ratio"],
                          "overall_excess": r["overall_excess"], "upwind": r["upwind"],
                          "sectors": r["sectors"]})
        return {"cwt": self.cwt, "hotspots": self.hotspots, "roses": roses,
                "localisation": self.source_eval,
                "method": "Upwind concentration-weighted rays (CWT/PSCF-style) from every "
                          "sensor-hour; wind-sector pollution roses."}

    def calibration_summary(self):
        out = {}
        for p in FIELD_KEYS:
            rows = []
            agg = {"raw": [], "mlr": [], "hybrid": []}
            for c in self.cal_report:
                t = c[p]["test"]
                rows.append({"sensor": c["sensor"], "name": c["name"], "kappa": c[p]["model"]["kappa"],
                             "raw_rmse": _r(t["raw"]["rmse"], 2), "mlr_rmse": _r(t["mlr"]["rmse"], 2),
                             "hybrid_rmse": _r(t["hybrid"]["rmse"], 2), "raw_mae": _r(t["raw"]["mae"], 2),
                             "hybrid_mae": _r(t["hybrid"]["mae"], 2), "raw_bias": _r(t["raw"]["bias"], 2),
                             "hybrid_bias": _r(t["hybrid"]["bias"], 2), "hybrid_r2": _r(t["hybrid"]["r2"], 3),
                             "raw_r2": _r(t["raw"]["r2"], 3)})
                for k in agg:
                    agg[k].append(t[k])
            summ = {}
            for k, lst in agg.items():
                summ[k] = {"rmse": _r(mean([e["rmse"] for e in lst]), 2),
                           "mae": _r(mean([e["mae"] for e in lst]), 2),
                           "r2": _r(mean([e["r2"] for e in lst if e["r2"] is not None]), 3)}
            red = (1 - summ["hybrid"]["rmse"] / summ["raw"]["rmse"]) * 100
            red_mae = (1 - summ["hybrid"]["mae"] / summ["raw"]["mae"]) * 100
            out[p] = {"sensors": rows, "mean": summ, "rmse_reduction_pct": _r(red, 1),
                      "mae_reduction_pct": _r(red_mae, 1)}
        # network-wide check against ground truth (possible only because data is synthetic)
        raw_e, cal_e = [], []
        for s in self.sensors:
            sid = s["id"]
            tr = self.truth[sid][0]
            for t in range(self.n):
                if (sid, t) in self.flagged or tr[t] is None:
                    continue
                r, c = self.raw["pm25"][sid][t], self.cal["pm25"][sid][t]
                if r is None or c is None:
                    continue
                raw_e.append(abs(r - tr[t]))
                cal_e.append(abs(c - tr[t]))
        out["field_vs_truth_pm25"] = {"raw_mae": _r(mean(raw_e), 2), "cal_mae": _r(mean(cal_e), 2),
                                      "n": len(raw_e)}
        fv = []
        for sid in ("S01", "S14"):
            if sid in self.sensor_by_id:
                ref = self.nearest_ref(self.sensor_by_id[sid]["x"], self.sensor_by_id[sid]["y"])["id"]
                r = self.ref_series(ref, "pm25")
                fv.append({"sensor": sid, "reference": ref,
                           "raw": self._err(self.raw["pm25"][sid], r),
                           "calibrated": self._err([None if (sid, t) in self.flagged else v
                                                    for t, v in enumerate(self.cal["pm25"][sid])], r)})
        out["field_validation"] = fv
        return out

    def evaluation(self):
        return {"calibration": self.calibration_summary(), "faults": self.fault_eval,
                "forecast": self.fc_eval,
                "interpolation": {k: ({kk: _r(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()}
                                      if isinstance(v, dict) else v) for k, v in self.interp_eval.items()},
                "variogram": {"model": self.vario, "bins": self.vario_bins},
                "sources": self.source_eval, "hotspots": self.hotspots,
                "hidden_exposure": self.hidden, "spike_threshold_sweep": self.spike_sweep,
                "timings_ms": self.timings, "compute_ms": self.compute_ms}

    def aqi_calc(self, body):
        concs = {}
        hourly_used = {}
        for p, v in body.items():
            if p in ("profile",):
                continue
            if p not in C.BREAKPOINTS:
                raise BadRequest("unknown pollutant '%s'" % p)
            if isinstance(v, list):
                if not v or len(v) > 48:
                    raise BadRequest("%s: give 1-48 hourly values" % p)
                try:
                    vals = [None if x is None else float(x) for x in v]
                except (TypeError, ValueError):
                    raise BadRequest("%s: hourly values must be numbers" % p)
                avg = A.averaged(p, vals)[-1]
                need = C.MIN_HOURS_24H if C.POLLUTANTS[p][2] == 24 else C.MIN_HOURS_8H
                hourly_used[p] = {"hours_given": sum(1 for x in vals if x is not None),
                                  "averaging_h": C.POLLUTANTS[p][2], "min_hours": need,
                                  "average": _r(avg, 2)}
                concs[p] = avg
            elif v is None or v == "":
                continue
            elif isinstance(v, bool) or not isinstance(v, (int, float, str)):
                raise BadRequest("%s must be a number" % p)
            else:
                try:
                    concs[p] = float(v)
                except ValueError:
                    raise BadRequest("%s must be a number" % p)
        try:
            res = A.compute({p: v for p, v in concs.items() if v is not None})
        except A.AQIError as e:
            raise BadRequest(str(e))
        res["averaging"] = hourly_used
        res["insufficient"] = [p for p, v in concs.items() if v is None]
        prof = body.get("profile", "general")
        if res["aqi"] is not None:
            try:
                res["advice"] = health.advice(res["aqi"], prof)
            except health.ProfileError as e:
                raise BadRequest(str(e))
        return res
