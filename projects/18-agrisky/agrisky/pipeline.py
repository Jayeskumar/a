"""Orchestration + in-memory cache: field -> analyses -> change -> prescription -> mission."""
import threading
import time
from collections import OrderedDict

from . import analysis as an
from . import change, config, field, planner, prescription, report
from .field import W, H


class InputError(ValueError):
    """Bad user input -> HTTP 400."""


def _lru_get(cache, key, maker, limit):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    val = maker()
    cache[key] = val
    while len(cache) > limit:
        cache.popitem(last=False)
    return val


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.fields = OrderedDict()
        self.analyses = OrderedDict()
        self.missions = OrderedDict()

    # ---------------------------------------------------------------- data
    def field(self, seed):
        with self.lock:
            return _lru_get(self.fields, seed, lambda: field.generate(seed), 4)

    def all_analyses(self, seed, k=config.KMEANS_K):
        def make():
            data = self.field(seed)
            out, prev = [], None
            for f in data["flights"]:
                a = an.analyse_flight(f, prev, k=k, seed=seed)
                out.append(a)
                prev = dict(f)
                prev["features"] = a["features"]
            return out
        with self.lock:
            return _lru_get(self.analyses, (seed, k), make, 6)

    def analysis(self, seed, flight, k=config.KMEANS_K):
        return self.all_analyses(seed, k)[flight]

    # ---------------------------------------------------------------- products
    def change(self, seed, flight, k=config.KMEANS_K, base=None):
        """Change detection as of `flight` (uses only flights up to and including it)."""
        als = self.all_analyses(seed, k)
        cur = als[flight]
        out = {"flight": flight, "day": cur["day"]}
        if base is None:
            base = flight - 1
        if 0 <= base < flight:
            b = als[base]
            crop = [c in config.CROP_CLASSES for c in cur["cell_class"]]
            out["diff"] = change.ndvi_difference(b["features"]["ndvi"], cur["features"]["ndvi"], crop)
            out["base"] = base
            out["base_day"] = b["day"]
        else:
            out["diff"] = None
            out["base"] = None
        sub = als[:flight + 1]
        masks = [[c == "pest" for c in a["cell_class"]] for a in sub]
        crop_cells = sum(1 for c in cur["cell_class"] if c in config.CROP_CLASSES)
        rates = [z["ndvi_rate_week"] for z in cur["zones"]
                 if z["label"] == "pest" and z.get("spreading") and z["ndvi_rate_week"] is not None]
        out["spread"] = change.spread([a["day"] for a in sub], masks, crop_cells,
                                      min(rates) if rates else None)
        data = self.field(seed)
        truth_idx = config.CLASSES.index("pest")
        out["truth"] = {
            "front_speed_m_day": round(data["layout"]["pest_speed"], 3),
            "series": [{"day": f["day"], "area_m2": sum(1 for t in f["truth"] if t == truth_idx)
                        * config.CELL_AREA_M2} for f in data["flights"][:flight + 1]]}
        return out

    def prescription(self, seed, flight, product="pesticide", k=config.KMEANS_K,
                     buffer_m=config.PEST_BUFFER_M):
        return prescription.build(self.analysis(seed, flight, k), product, buffer_m)

    def mission(self, seed, flight, product="pesticide", kind="vra", k=config.KMEANS_K,
                buffer_m=config.PEST_BUFFER_M, **params):
        key = (seed, flight, product, kind, k, buffer_m, tuple(sorted(params.items())))

        def make():
            rx = self.prescription(seed, flight, product, k, buffer_m)
            if kind == "vra":
                target = [r > 0 for r in rx["cell_rate"]]
                payload = rx["payload_per_m2"]
            else:
                a = self.analysis(seed, flight, k)
                blocked = prescription.no_spray_mask(a["cell_class"])
                target = [c in config.CROP_CLASSES and not blocked[i]
                          for i, c in enumerate(a["cell_class"])]
                if product == "pesticide":
                    rate = config.SPRAY_VOLUME_L_HA / config.M2_PER_HA
                else:
                    rate = config.UREA_BASE_KG_HA / config.M2_PER_HA
                payload = [rate if t else 0.0 for t in target]
            t0 = time.perf_counter()
            res = planner.plan(target, payload, W, H, **params)
            res["plan_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            res["kind"] = kind
            res["product"] = product
            res["payload_unit"] = rx["payload_unit"]
            res["payload_name"] = rx["payload_name"]
            return res
        with self.lock:
            return _lru_get(self.missions, key, make, 24)

    # ---------------------------------------------------------------- views
    def flights_summary(self, seed, k=config.KMEANS_K):
        out = []
        for a in self.all_analyses(seed, k):
            pest = sum(1 for c in a["cell_class"] if c == "pest")
            out.append({"index": a["index"], "day": a["day"],
                        "das": config.DAS_AT_FIRST_FLIGHT + a["day"],
                        "label": "Flight %d · Day %d" % (a["index"] + 1, a["day"]),
                        "pest_m2": pest * config.CELL_AREA_M2,
                        "zones": len(a["zones"]), "accuracy": a["accuracy"]["accuracy"]})
        return out

    def scene(self, seed, flight, k=config.KMEANS_K, mission_params=None):
        t0 = time.perf_counter()
        mission_params = mission_params or {}
        a = self.analysis(seed, flight, k)
        f = self.field(seed)["flights"][flight]
        ch = self.change(seed, flight, k)
        rx_p = self.prescription(seed, flight, "pesticide", k)
        rx_u = self.prescription(seed, flight, "urea", k)
        m_vra = self.mission(seed, flight, "pesticide", "vra", k, **mission_params)
        m_uni = self.mission(seed, flight, "pesticide", "uniform", k, **mission_params)
        feat = a["features"]
        cls_idx = {c: i for i, c in enumerate(config.CLASSES)}

        def q(arr, s=1000):
            return [int(round(v * s)) for v in arr]
        layers = {name: q(feat[name]) for name in ("ndvi", "gndvi", "ndre", "savi", "ndwi")}
        for b in config.BANDS:
            layers[b] = q(f["bands"][b])
        layers["truth"] = f["truth"]
        layers["cluster"] = a["smoothed"]
        layers["zone"] = a["zones_grid"]
        layers["cls"] = [cls_idx[c] for c in a["cell_class"]]
        layers["dndvi"] = q(ch["diff"]["relative"]) if ch["diff"] else None
        layers["rx_pesticide"] = q(rx_p["cell_rate"])
        layers["rx_urea"] = [int(round(v)) for v in rx_u["cell_rate"]]
        rep = report.farmer_report(a, ch, rx_p, rx_u, m_vra, m_uni)
        out = {
            "seed": seed, "flight": flight, "k": k, "width": W, "height": H,
            "cell_m": config.CELL_M, "day": a["day"], "das": config.DAS_AT_FIRST_FLIGHT + a["day"],
            "flights": self.flights_summary(seed, k),
            "layers": layers,
            "kmeans": {kk: v for kk, v in a["kmeans"].items() if kk != "labels"},
            "zones": a["zones"], "reference": a["reference"], "accuracy": a["accuracy"],
            "raw_zone_count": a["raw_zone_count"], "timing_ms": a["timing_ms"],
            "change": _strip_change(ch),
            "prescriptions": {"pesticide": _strip_rx(rx_p), "urea": _strip_rx(rx_u)},
            "mission": {"vra": _strip_mission(m_vra), "uniform": _strip_mission(m_uni)},
            "report": rep,
            "layout_truth": {"pest_corner": self.field(seed)["layout"]["pest_corner"],
                             "pest_speed_m_day": round(self.field(seed)["layout"]["pest_speed"], 3)},
        }
        out["scene_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out


def _strip_rx(rx):
    return {k: v for k, v in rx.items() if k not in ("cell_rate", "payload_per_m2")}


def _strip_mission(m):
    return {k: v for k, v in m.items() if k != "coverage"}


def _strip_change(ch):
    out = dict(ch)
    if ch.get("diff"):
        out["diff"] = {k: v for k, v in ch["diff"].items() if k not in ("diff", "relative")}
    return out


STORE = Store()
