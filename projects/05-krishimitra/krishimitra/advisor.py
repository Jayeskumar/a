"""One-call farm advisory: validates input and combines all modules."""
import datetime as _dt
import time

from . import config, cropcal, fertiliser, irrigation, market, weather
from .i18n import join, t
from .recommender import get_model


class InputError(ValueError):
    pass


def num(payload, key, lo, hi, default=None):
    v = payload.get(key, default)
    if v is None or v == "":
        raise InputError("missing field: %s" % key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise InputError("field %s must be a number" % key)
    if v != v or not (lo <= v <= hi):       # v != v catches NaN
        raise InputError("field %s must be between %s and %s" % (key, lo, hi))
    return v


def date_field(payload, key, default):
    v = payload.get(key)
    if v in (None, ""):
        return default
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise InputError("field %s must be an ISO date YYYY-MM-DD" % key)


def choice(payload, key, options, default=None):
    v = payload.get(key, default)
    if v not in options:
        raise InputError("field %s must be one of: %s" % (key, ", ".join(sorted(options))))
    return v


def soil_inputs(payload):
    return {f: num(payload, f, *config.FEATURE_LIMITS[f]) for f in config.FEATURES}


def forecast_field(payload, lat, start, rain_factor):
    fc = payload.get("forecast")
    if fc in (None, "", []):
        return weather.synth_forecast(lat, start, 7, rain_factor), "synthetic"
    if not isinstance(fc, list) or len(fc) > 14:
        raise InputError("forecast must be a list of up to 14 days")
    out = []
    for i, d in enumerate(fc):
        if not isinstance(d, dict):
            raise InputError("forecast[%d] must be an object" % i)
        out.append({"tmax": num(d, "tmax", -10, 55), "tmin": num(d, "tmin", -20, 45),
                    "rain": num(d, "rain", 0, 1000, 0)})
    return out, "user"


def advise(payload, today=None):
    if not isinstance(payload, dict):
        raise InputError("JSON body must be an object")
    t0 = time.perf_counter()
    today = today or _dt.date.today()
    inputs = soil_inputs(payload)
    lat = num(payload, "lat", -60, 60, 11.0)
    area = num(payload, "area_acres", 0.05, 10000, 1.0)
    soil = choice(payload, "soil", config.SOIL_TYPES, "red")
    method = choice(payload, "method", config.IRRIGATION_METHODS, "flood")
    rain_factor = num(payload, "rain_factor", 0, 5, 1.0)
    start = date_field(payload, "start_date", today)
    sowing = date_field(payload, "sowing_date", start - _dt.timedelta(days=20))
    if abs((start - sowing).days) > 800:
        raise InputError("sowing_date must be within ~2 years of start_date")

    rec = get_model().recommend(inputs)
    crop = payload.get("crop") or rec["top3"][0]["crop"]
    if crop not in config.CROPS:
        raise InputError("unknown crop: %s" % crop)

    fc, fc_source = forecast_field(payload, lat, start, rain_factor)
    fert = fertiliser.advise(crop, inputs["N"], inputs["P"], inputs["K"], inputs["ph"], area)
    irr = irrigation.plan(crop, lat, sowing, start, fc, soil, method, area)
    try:
        mkt = market.analyse(crop, start)
    except ValueError as e:
        raise InputError(str(e))
    cal = cropcal.calendar(crop, sowing, start)

    top = rec["top3"]
    speech = join(
        t("advice_intro", crop=crop),
        t("rec_summary", crop=top[0]["crop"], pct=int(round(top[0]["prob"] * 100)),
          crop2=top[1]["crop"], crop3=top[2]["crop"]),
        fert["summary"], irr["summary"], mkt["decision"]["text"],
    )
    return {
        "crop": crop, "crop_name": config.CROP_NAMES[crop],
        "recommendation": rec, "fertiliser": fert, "irrigation": irr,
        "market": mkt, "calendar": cal, "forecast_source": fc_source,
        "speech": speech,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def meta():
    m = get_model()
    return {
        "features": config.FEATURES, "units": config.FEATURE_UNITS,
        "limits": config.FEATURE_LIMITS,
        "crops": [{"crop": c, "name": config.CROP_NAMES[c], "ranges": config.CROP_RANGES[c]}
                  for c in config.CROPS],
        "soils": {k: {"en": v["en"], "ta": v["ta"], "refill_mm": v["refill_mm"]}
                  for k, v in config.SOIL_TYPES.items()},
        "methods": {k: {"en": v["en"], "ta": v["ta"], "eff": v["eff"]}
                    for k, v in config.IRRIGATION_METHODS.items()},
        "presets": config.PRESETS,
        "metrics": m.metrics,
        "disclaimer": {
            "en": "All agronomic ranges, doses and prices are approximate / illustrative; prices are synthetic.",
            "ta": "அனைத்து வேளாண் அளவுகள், உர அளவுகள், விலைகள் தோராயமானவை / விளக்கத்திற்கு மட்டும்; விலைகள் செயற்கையாக உருவாக்கப்பட்டவை.",
        },
    }
