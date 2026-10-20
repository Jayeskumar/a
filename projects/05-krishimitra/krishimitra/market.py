"""Market timing on a SYNTHETIC weekly mandi price series (seeded, not real prices).

Series model:  p_t = base * (1+g)^(t/52) * S(month) * exp(e_t),  e_t = 0.6 e_{t-1} + N(0, s)
               S(month) = 1 + amp * cos(2*pi*(month - high_month)/12)
Analysis:
  * trailing moving averages MA4 / MA12
  * seasonal index SI[m] = mean over month m of p_t / CMA53_t (ratio-to-moving-average),
    normalised to average 1
  * deseasonalised level (last 8 weeks) + OLS trend (last 52 weeks)
  * forecast_h = (level + slope*h) * SI[month(t+h)], band = forecast * exp(+-z*sigma*sqrt(1+h/4))
  * hold h weeks only if forecast_h * (1 - hold_cost*h) beats today's price by >= MIN_GAIN
"""
import datetime as _dt
import math
import random

from . import config
from .i18n import t

EPOCH = _dt.date.fromisoformat(config.MARKET_EPOCH)
MIN_AS_OF = EPOCH + _dt.timedelta(weeks=80)
MAX_AS_OF = _dt.date(2035, 12, 31)


def _month_float(d):
    return d.month - 1 + (d.day - 1) / 31.0


def price_series(crop, as_of):
    if crop not in config.MARKET:
        raise ValueError("unknown crop: %s" % crop)
    if not (MIN_AS_OF <= as_of <= MAX_AS_OF):
        raise ValueError("date must be between %s and %s" % (MIN_AS_OF, MAX_AS_OF))
    m = config.MARKET[crop]
    rng = random.Random(config.MARKET_SEED + 101 * config.CROPS.index(crop))
    n = (as_of - EPOCH).days // 7 + 1
    e = 0.0
    out = []
    for i in range(n):
        d = EPOCH + _dt.timedelta(weeks=i)
        e = 0.6 * e + rng.gauss(0, m["noise"])
        s = 1 + m["amp"] * math.cos(2 * math.pi * (_month_float(d) - (m["high_month"] - 1)) / 12.0)
        trend = (1 + config.MARKET_TREND_PER_YEAR) ** (i / 52.18)
        out.append((d, round(m["base"] * trend * s * math.exp(e), 1)))
    return out


def moving_average(values, w):
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= w:
            s -= values[i - w]
        out.append(round(s / min(i + 1, w), 1) if i + 1 >= w else None)
    return out


def seasonal_index(dates, prices, half=26):
    sums, counts = [0.0] * 12, [0] * 12
    for i in range(half, len(prices) - half):
        cma = sum(prices[i - half:i + half + 1]) / (2 * half + 1)
        mth = dates[i].month - 1
        sums[mth] += prices[i] / cma
        counts[mth] += 1
    si = [sums[k] / counts[k] if counts[k] else 1.0 for k in range(12)]
    mean = sum(si) / 12.0
    return [v / mean for v in si]


def ols_slope(ys):
    n = len(ys)
    xm = (n - 1) / 2.0
    ym = sum(ys) / n
    num = sum((i - xm) * (y - ym) for i, y in enumerate(ys))
    den = sum((i - xm) ** 2 for i in range(n)) or 1.0
    slope = num / den
    return slope, ym - slope * xm


def analyse(crop, as_of, horizon=12):
    series = price_series(crop, as_of)        # validates crop and date
    m = config.MARKET[crop]
    dates = [d for d, _ in series]
    prices = [p for _, p in series]
    si = seasonal_index(dates, prices)
    ds = [p / si[d.month - 1] for d, p in series]
    recent = ds[-52:]
    slope, intercept = ols_slope(recent)
    level = sum(ds[-8:]) / 8.0 + slope * 3.5        # centre of last 8 weeks -> now
    # residual spread around the fitted (trend x season) curve
    resid = []
    base_i = len(ds) - len(recent)
    for j, y in enumerate(recent):
        fit = (intercept + slope * j) * si[dates[base_i + j].month - 1]
        resid.append(math.log(prices[base_i + j] / fit))
    mu = sum(resid) / len(resid)
    sigma = math.sqrt(sum((r - mu) ** 2 for r in resid) / max(1, len(resid) - 1))
    z = config.MARKET_BAND_Z
    current = prices[-1]
    last_date = dates[-1]
    forecast = []
    for h in range(1, horizon + 1):
        d = last_date + _dt.timedelta(weeks=h)
        f = (level + slope * h) * si[d.month - 1]
        spread = z * sigma * math.sqrt(1 + h / 4.0)
        net = f * (1 - m["hold_cost"] * h)
        forecast.append({"date": d.isoformat(), "week": h, "price": round(f, 1),
                         "low": round(f * math.exp(-spread), 1),
                         "high": round(f * math.exp(spread), 1),
                         "net_after_holding": round(net, 1),
                         "gain_pct": round((net / current - 1) * 100, 2)})
    best = None
    for fc in forecast[:m["max_hold"]]:
        if best is None or fc["gain_pct"] > best["gain_pct"]:
            best = fc
    hold_weeks = 0
    if best is not None and best["gain_pct"] >= config.MARKET_MIN_GAIN * 100:
        hold_weeks = best["week"]
    if hold_weeks:
        band = [best["low"], best["high"]]
        decision = {"action": "hold", "weeks": hold_weeks, "expected": best["price"], "band": band,
                    "gain_pct": best["gain_pct"],
                    "text": t("mkt_hold", n=hold_weeks, lo=int(band[0]), hi=int(band[1]),
                              gain=best["gain_pct"], unit=m["unit"])}
    else:
        spread = z * sigma
        band = [round(current * math.exp(-spread), 1), round(current * math.exp(spread), 1)]
        if m["max_hold"] == 0:
            reason_key = "mkt_reason_mill"
        elif m["max_hold"] <= 1:
            reason_key = "mkt_reason_perishable"
        else:
            reason_key = "mkt_reason_nogain"
        decision = {"action": "sell", "weeks": 0, "expected": current, "band": band,
                    "gain_pct": best["gain_pct"] if best else 0.0,
                    "text": t("mkt_sell", lo=int(band[0]), hi=int(band[1]), unit=m["unit"]),
                    "reason": t(reason_key)}
    ma4 = moving_average(prices, 4)
    ma12 = moving_average(prices, 12)
    k = min(104, len(series))
    hist = [{"date": dates[i].isoformat(), "price": prices[i], "ma4": ma4[i], "ma12": ma12[i]}
            for i in range(len(series) - k, len(series))]
    cur_month = last_date.month - 1
    return {
        "crop": crop, "unit": m["unit"], "as_of": last_date.isoformat(),
        "synthetic": True, "current": current, "ma4": ma4[-1], "ma12": ma12[-1],
        "trend_per_week": round(slope, 2), "sigma": round(sigma, 4),
        "seasonal_index": [round(v, 4) for v in si],
        "seasonal_index_now": round(si[cur_month], 4),
        "history": hist, "forecast": forecast, "decision": decision,
        "assumptions": {"hold_cost_per_week": m["hold_cost"], "max_hold_weeks": m["max_hold"],
                        "min_gain": config.MARKET_MIN_GAIN, "band_z": z},
    }
