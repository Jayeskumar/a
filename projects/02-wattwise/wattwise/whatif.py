"""What-if simulator: projected monthly savings from four operational levers.

Levers are applied in sequence so savings never double-count:
 1. Auto-off after a cut-off hour (non-residential buildings only):
    saving = sum over cut-off..06:00 hours of max(0, load - essential base) x 85%
    where essential base = 20th percentile of the building's 00-05 h load.
 2. AC setpoint +d degC: remaining kWh x AC share x 6% x d
 3. LED retrofit p%:     remaining kWh x lighting share x p x 50%
 4. BLDC fans p%:        remaining kWh x fan share x p x 50%
The month is the last 28 days of data scaled to 30 days.
"""

from . import config
from .carbon import co2_kg, cost_inr, trees_equivalent
from .dataset import BUILDING_BY_ID
from .stats import percentile

WINDOW_HOURS = 28 * 24
MONTH_SCALE = 30.0 / 28.0


class WhatIfError(ValueError):
    pass


def _clamp(v, name, lo, hi, cast=float):
    try:
        x = cast(v)
    except (TypeError, ValueError):
        raise WhatIfError("%s must be a number" % name)
    if x != x or x < lo or x > hi:
        raise WhatIfError("%s must be between %s and %s" % (name, lo, hi))
    return x


def essential_base(timestamps, y):
    night = [v for t, v in zip(timestamps, y) if t.hour in config.NIGHT_HOURS]
    return percentile(night, config.ESSENTIAL_BASE_PERCENTILE)


def _in_window(hour, cutoff):
    return hour >= cutoff or hour < config.AUTO_OFF_END_HOUR


def simulate(ds, ac_setpoint_delta=0, auto_off=False, auto_off_hour=22,
             led_pct=0, bldc_pct=0):
    d = _clamp(ac_setpoint_delta, "ac_setpoint_delta", 0, config.AC_MAX_SETPOINT_DELTA)
    cutoff = _clamp(auto_off_hour, "auto_off_hour", 18, 23, int)
    led = _clamp(led_pct, "led_pct", 0, 100) / 100.0
    bldc = _clamp(bldc_pct, "bldc_pct", 0, 100) / 100.0
    auto_off = bool(auto_off) and str(auto_off).lower() not in ("0", "false", "no")

    ts = ds.timestamps[-WINDOW_HOURS:]
    rows, tot = [], {"baseline_kwh": 0.0, "auto_off": 0.0, "ac": 0.0, "led": 0.0, "bldc": 0.0}
    for bid, series in ds.loads.items():
        b = BUILDING_BY_ID[bid]
        y = series[-WINDOW_HOURS:]
        month = sum(y) * MONTH_SCALE
        s_off = 0.0
        base = essential_base(ds.timestamps, series)
        if auto_off and b["auto_off"]:
            s_off = sum(max(0.0, v - base) for t, v in zip(ts, y) if _in_window(t.hour, cutoff))
            s_off *= config.AUTO_OFF_EFFECTIVENESS * MONTH_SCALE
        rem = month - s_off
        s_ac = rem * b["shares"]["ac"] * config.AC_SAVING_PER_DEGC * d
        rem -= s_ac
        s_led = rem * b["shares"]["lighting"] * led * config.LED_SAVING_FRACTION
        rem -= s_led
        s_bldc = rem * b["shares"]["fans"] * bldc * config.BLDC_SAVING_FRACTION
        total = s_off + s_ac + s_led + s_bldc
        rows.append({
            "building": bid, "name": b["name"], "baseline_kwh": round(month),
            "essential_base_kw": round(base, 1),
            "saving_kwh": {"auto_off": round(s_off), "ac": round(s_ac),
                           "led": round(s_led), "bldc": round(s_bldc), "total": round(total)},
            "saving_pct": round(100.0 * total / month, 1) if month else 0.0,
            "auto_off_applies": b["auto_off"],
        })
        tot["baseline_kwh"] += month
        tot["auto_off"] += s_off
        tot["ac"] += s_ac
        tot["led"] += s_led
        tot["bldc"] += s_bldc
    total = tot["auto_off"] + tot["ac"] + tot["led"] + tot["bldc"]
    return {
        "inputs": {"ac_setpoint_delta": d, "auto_off": auto_off, "auto_off_hour": cutoff,
                   "led_pct": led * 100, "bldc_pct": bldc * 100},
        "monthly_baseline_kwh": round(tot["baseline_kwh"]),
        "monthly_saving_kwh": round(total),
        "monthly_saving_inr": round(cost_inr(total)),
        "monthly_co2_saved_kg": round(co2_kg(total)),
        "annual_saving_inr": round(cost_inr(total) * 12),
        "trees_equivalent": round(trees_equivalent(co2_kg(total) * 12)),
        "saving_pct": round(100.0 * total / tot["baseline_kwh"], 1) if tot["baseline_kwh"] else 0,
        "by_lever_kwh": {k: round(tot[k]) for k in ("auto_off", "ac", "led", "bldc")},
        "buildings": rows,
        "explain": [
            "Month = last 28 days of metered data x 30/28.",
            "Auto-off: after-hours load above each building's essential base "
            "(20th pct of 00-05 h) x %d%% effectiveness; hostels and canteen excluded."
            % int(config.AUTO_OFF_EFFECTIVENESS * 100),
            "AC: approx. %d%% of AC energy per +1 degC (BEE guidance) x AC share."
            % int(config.AC_SAVING_PER_DEGC * 100),
            "LED / BLDC: approx. %d%% saving on the retrofitted share of lighting / fans."
            % int(config.LED_SAVING_FRACTION * 100),
            "Levers applied in sequence on the remaining energy - no double counting.",
        ],
    }
