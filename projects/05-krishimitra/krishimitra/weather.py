"""Deterministic synthetic 7-day forecast from approx. monthly climate normals.

Used only when the caller does not supply a forecast (offline demo). Same date + latitude
=> same forecast on every machine.
"""
import datetime as _dt
import random

from . import config


def synth_forecast(lat, start_date, days=7, rain_factor=1.0):
    rng = random.Random(start_date.toordinal() * 1000 + int(round(lat * 100)))
    out = []
    for i in range(days):
        d = start_date + _dt.timedelta(days=i)
        tmax_n, tmin_n, rain_n = config.CLIMATE_NORMALS[d.month - 1]
        rain_month = rain_n * rain_factor
        p_wet = min(0.7, rain_month / 250.0)          # chance of a rainy day (assumption)
        rain = 0.0
        if rng.random() < p_wet:
            mean_wet = rain_month / max(1.0, 30 * p_wet)
            rain = rng.expovariate(1.0 / mean_wet)
        cool = min(3.0, rain / 10.0)                   # rainy days are a little cooler
        tmax = tmax_n + rng.gauss(0, 1.0) - cool
        tmin = tmin_n + rng.gauss(0, 0.8) - cool / 3
        out.append({"date": d.isoformat(), "tmax": round(tmax, 1), "tmin": round(tmin, 1),
                    "rain": round(rain, 1)})
    return out
