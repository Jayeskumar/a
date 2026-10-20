"""Irrigation scheduler: FAO-56 extraterrestrial radiation + Hargreaves ET0 + Kc curve.

  dr  = 1 + 0.033 cos(2*pi*J/365)                       inverse relative Earth-Sun distance
  dec = 0.409 sin(2*pi*J/365 - 1.39)                    solar declination (rad)
  ws  = arccos(-tan(lat) tan(dec))                      sunset hour angle (rad)
  Ra  = (24*60/pi) Gsc dr [ws sin(lat) sin(dec) + cos(lat) cos(dec) sin(ws)]   MJ m-2 day-1
  ET0 = 0.0023 (Tmean + 17.8) sqrt(Tmax - Tmin) * 0.408 Ra                     mm/day
  ETc = Kc(stage) * ET0
"""
import datetime as _dt
import math

from . import config
from .i18n import t

STAGES = ("initial", "development", "mid", "late")


def inverse_distance(doy):
    return 1 + 0.033 * math.cos(2 * math.pi * doy / 365.0)


def declination(doy):
    return 0.409 * math.sin(2 * math.pi * doy / 365.0 - 1.39)


def sunset_hour_angle(lat_rad, dec):
    x = -math.tan(lat_rad) * math.tan(dec)
    return math.acos(max(-1.0, min(1.0, x)))   # clamp for polar day/night


def extraterrestrial_radiation(lat_deg, doy):
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21)."""
    phi = math.radians(lat_deg)
    dr = inverse_distance(doy)
    dec = declination(doy)
    ws = sunset_hour_angle(phi, dec)
    ra = (24 * 60 / math.pi) * config.GSC * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    return max(0.0, ra)


def hargreaves_et0(tmin, tmax, ra_mj):
    """Reference evapotranspiration, mm/day (FAO-56 eq. 52)."""
    if tmax < tmin:
        tmin, tmax = tmax, tmin
    tmean = (tmax + tmin) / 2.0
    return max(0.0, config.HARGREAVES_COEFF * (tmean + 17.8) * math.sqrt(tmax - tmin)
               * config.MJ_TO_MM * ra_mj)


def effective_rain(rain_mm):
    if rain_mm < config.EFF_RAIN_THRESHOLD_MM:
        return 0.0
    return config.EFF_RAIN_FRACTION * rain_mm


def season_length(crop):
    return sum(config.STAGE_DAYS[crop])


def crop_stage(crop, das):
    """Return (stage name or None, Kc) for days-after-sowing `das` (FAO-56 Kc curve)."""
    if das < 0:
        return None, 0.0
    l_ini, l_dev, l_mid, l_late = config.STAGE_DAYS[crop]
    kc_ini, kc_mid, kc_end = config.KC[crop]
    total = l_ini + l_dev + l_mid + l_late
    if crop in config.PERENNIAL:
        das = das % total
    if das >= total:
        return "harvested", 0.0
    if das < l_ini:
        return "initial", kc_ini
    if das < l_ini + l_dev:
        frac = (das - l_ini) / float(l_dev)
        return "development", kc_ini + frac * (kc_mid - kc_ini)
    if das < l_ini + l_dev + l_mid:
        return "mid", kc_mid
    frac = (das - l_ini - l_dev - l_mid) / float(l_late)
    return "late", kc_mid + frac * (kc_end - kc_mid)


def plan(crop, lat, sowing_date, start_date, forecast, soil="red", method="flood",
         area_acres=1.0, initial_deficit_mm=None):
    """Simple root-zone bucket over the forecast days.

    deficit += ETc - Peff each day; irrigate when deficit >= refill threshold of the soil
    (drip: every day there is any deficit). gross = net / application efficiency.
    """
    if crop not in config.KC:
        raise ValueError("unknown crop: %s" % crop)
    if soil not in config.SOIL_TYPES:
        raise ValueError("unknown soil type: %s" % soil)
    if method not in config.IRRIGATION_METHODS:
        raise ValueError("unknown irrigation method: %s" % method)
    eff = config.IRRIGATION_METHODS[method]["eff"]
    refill = config.PADDY_REFILL_MM if crop == "rice" else config.SOIL_TYPES[soil]["refill_mm"]
    if initial_deficit_mm is None:      # unknown history: drip keeps soil near capacity,
        initial_deficit_mm = 0.0 if method == "drip" else refill / 2.0   # others half-way
    deficit = float(initial_deficit_mm)
    lpa = config.LITRES_PER_MM_PER_ACRE
    days = []
    tot = {"etc": 0.0, "peff": 0.0, "net": 0.0, "gross": 0.0, "et0": 0.0}
    for i, w in enumerate(forecast):
        day = start_date + _dt.timedelta(days=i)
        doy = day.timetuple().tm_yday
        ra = extraterrestrial_radiation(lat, doy)
        et0 = hargreaves_et0(w["tmin"], w["tmax"], ra)
        das = (day - sowing_date).days
        stage, kc = crop_stage(crop, das)
        etc = kc * et0
        if crop == "rice" and stage not in (None, "harvested", "late"):
            etc += config.PADDY_PERCOLATION_MM    # puddled field loses water downward too
        peff = effective_rain(w["rain"])
        deficit = max(0.0, deficit + etc - peff)
        net = 0.0
        if stage not in (None, "harvested"):
            if (method == "drip" and deficit > 0.5) or deficit >= refill:
                net = deficit
                deficit = 0.0
        gross = net / eff
        tot["etc"] += etc
        tot["peff"] += peff
        tot["net"] += net
        tot["gross"] += gross
        tot["et0"] += et0
        days.append({
            "date": day.isoformat(), "doy": doy, "das": das, "stage": stage,
            "tmax": w["tmax"], "tmin": w["tmin"], "rain": w["rain"],
            "ra_mj": round(ra, 2), "et0": round(et0, 2), "kc": round(kc, 3),
            "etc": round(etc, 2), "peff": round(peff, 2),
            "deficit_mm": round(deficit, 1), "irrigate": net > 0,
            "net_mm": round(net, 1), "gross_mm": round(gross, 1),
            "litres_per_acre": int(round(gross * lpa)),
            "litres_total": int(round(gross * lpa * area_acres)),
        })
    n = max(1, len(days))
    irrigation_days = [d for d in days if d["irrigate"]]
    stage_now = days[0]["stage"] if days else None
    if not irrigation_days:
        summary = t("irr_none", crop=crop)
    else:
        first = irrigation_days[0]
        summary = t("irr_summary", n=len(irrigation_days), date=first["date"],
                    mm=first["gross_mm"], litres=first["litres_per_acre"],
                    week_litres=int(round(tot["gross"] * lpa)))
    return {
        "crop": crop, "lat": lat, "soil": soil, "method": method, "efficiency": eff,
        "refill_mm": refill, "area_acres": area_acres,
        "sowing_date": sowing_date.isoformat(), "start_date": start_date.isoformat(),
        "stage_now": stage_now, "days": days,
        "daily_need_mm": round(tot["etc"] / n, 2),
        "daily_need_litres_per_acre": int(round(tot["etc"] / n * lpa)),
        "week": {
            "et0_mm": round(tot["et0"], 1), "etc_mm": round(tot["etc"], 1),
            "effective_rain_mm": round(tot["peff"], 1),
            "net_irrigation_mm": round(tot["net"], 1),
            "gross_irrigation_mm": round(tot["gross"], 1),
            "litres_per_acre": int(round(tot["gross"] * lpa)),
            "litres_total": int(round(tot["gross"] * lpa * area_acres)),
        },
        "summary": summary,
        "formula": "ET0 = 0.0023 (Tmean+17.8) sqrt(Tmax-Tmin) x 0.408 Ra;  ETc = Kc x ET0",
    }
