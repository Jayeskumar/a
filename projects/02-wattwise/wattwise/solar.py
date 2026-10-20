"""Rooftop solar planner: size, generation, payback and CO2 avoided.

    kWp_roof    = roof_m2 * usable_fraction / m2_per_kWp
    kWp_demand  = annual_kWh * max_fraction / yield
    kWp         = min(kWp_roof, kWp_demand)          (the binding limit is reported)
    gen(y)      = kWp * yield * (1 - degradation)^(y-1)
    saving(y)   = gen(y) * tariff - O&M
    payback     = capex / saving(1)                  (simple, undiscounted)
"""

from . import config


class SolarInputError(ValueError):
    pass


def _num(v, name, lo, hi, allow_none=False):
    if v is None or v == "":
        if allow_none:
            return None
        raise SolarInputError("%s is required" % name)
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise SolarInputError("%s must be a number" % name)
    if x != x or x < lo or x > hi:
        raise SolarInputError("%s must be between %g and %g" % (name, lo, hi))
    return x


def plan(roof_area_m2, monthly_kwh=None, monthly_bill_inr=None,
         tariff=None, cost_per_kwp=None, yield_kwh_per_kwp=None):
    roof = _num(roof_area_m2, "roof_area_m2", 1, 1e6)
    tariff = _num(tariff, "tariff", 1, 50, True) or config.TARIFF_INR_PER_KWH
    cost = _num(cost_per_kwp, "cost_per_kwp", 10000, 200000, True) or config.SOLAR_COST_INR_PER_KWP
    yld = _num(yield_kwh_per_kwp, "yield_kwh_per_kwp", 500, 2500, True) \
        or config.SOLAR_YIELD_KWH_PER_KWP_YEAR
    mk = _num(monthly_kwh, "monthly_kwh", 0, 1e8, True)
    mb = _num(monthly_bill_inr, "monthly_bill_inr", 0, 1e9, True)
    if mk:
        consumption_source = "monthly kWh entered"
    elif mb:
        mk = mb / tariff
        consumption_source = "derived from bill: Rs %.0f / Rs %.2f per kWh" % (mb, tariff)
    else:
        raise SolarInputError("give monthly_kwh or monthly_bill_inr (> 0)")

    annual_kwh = mk * 12.0
    kwp_roof = roof * config.SOLAR_USABLE_ROOF_FRACTION / config.SOLAR_AREA_M2_PER_KWP
    kwp_demand = annual_kwh * config.SOLAR_MAX_FRACTION_OF_CONSUMPTION / yld
    kwp = round(min(kwp_roof, kwp_demand), 1)
    limit = "roof area" if kwp_roof <= kwp_demand else "annual consumption (net-metering cap)"
    capex = kwp * cost
    om = capex * config.SOLAR_OM_FRACTION_PER_YEAR
    years = config.SOLAR_LIFETIME_YEARS

    cashflow, cumulative, gen_total, payback_year = [], -capex, 0.0, None
    for y in range(1, years + 1):
        gen = kwp * yld * (1 - config.SOLAR_DEGRADATION_PER_YEAR) ** (y - 1)
        saving = gen * tariff - om
        prev = cumulative
        cumulative += saving
        gen_total += gen
        if payback_year is None and cumulative >= 0 and saving > 0:
            payback_year = round(y - 1 + (-prev) / saving, 1)
        cashflow.append({"year": y, "generation_kwh": round(gen),
                         "saving_inr": round(saving), "cumulative_inr": round(cumulative)})

    gen1 = kwp * yld
    saving1 = gen1 * tariff - om
    co2_year = gen1 * config.GRID_EMISSION_FACTOR_KG_PER_KWH
    return {
        "inputs": {"roof_area_m2": roof, "monthly_kwh": round(mk, 1),
                   "consumption_source": consumption_source, "tariff_inr_per_kwh": tariff,
                   "cost_inr_per_kwp": cost, "yield_kwh_per_kwp_year": yld},
        "kwp": kwp, "kwp_roof_limit": round(kwp_roof, 1),
        "kwp_demand_limit": round(kwp_demand, 1), "limited_by": limit,
        "panel_area_m2": round(kwp * config.SOLAR_AREA_M2_PER_KWP),
        "annual_generation_kwh": round(gen1),
        "coverage_pct": round(100.0 * gen1 / annual_kwh, 1) if annual_kwh else 0.0,
        "capex_inr": round(capex), "annual_om_inr": round(om),
        "annual_saving_inr": round(saving1),
        "simple_payback_years": round(capex / saving1, 1) if saving1 > 0 else None,
        "payback_year_with_degradation": payback_year,
        "lifetime_years": years,
        "lifetime_generation_kwh": round(gen_total),
        "lifetime_net_saving_inr": round(cumulative),
        "co2_avoided_t_per_year": round(co2_year / 1000.0, 2),
        "co2_avoided_t_lifetime": round(gen_total * config.GRID_EMISSION_FACTOR_KG_PER_KWH / 1000.0, 1),
        "trees_equivalent": round(co2_year / config.TREE_KG_CO2_PER_YEAR),
        "cashflow": cashflow,
        "explain": [
            "Usable roof %.0f m2 x %.0f%% / %.0f m2 per kWp = %.1f kWp roof limit"
            % (roof, config.SOLAR_USABLE_ROOF_FRACTION * 100, config.SOLAR_AREA_M2_PER_KWP, kwp_roof),
            "%.0f kWh/yr / %.0f kWh per kWp = %.1f kWp demand limit"
            % (annual_kwh, yld, kwp_demand),
            "Chosen %.1f kWp (limited by %s)" % (kwp, limit),
            "%.1f kWp x %.0f kWh/kWp = %.0f kWh in year 1 (%.1f%% of use)"
            % (kwp, yld, gen1, 100.0 * gen1 / annual_kwh if annual_kwh else 0),
            "Capex Rs %.0f; year-1 saving Rs %.0f after O&M -> payback %.1f yr"
            % (capex, saving1, capex / saving1 if saving1 > 0 else float("nan")),
        ],
        "assumptions": {
            "yield": "approx. 1,400-1,500 kWh/kWp/yr for Tamil Nadu (using %.0f)" % yld,
            "area": "approx. %.0f m2 shadow-free roof per kWp; %.0f%% of roof usable"
                    % (config.SOLAR_AREA_M2_PER_KWP, config.SOLAR_USABLE_ROOF_FRACTION * 100),
            "cost": "approx. Rs %.0f per kWp before subsidy (planning figure)" % cost,
            "degradation": "%.1f%% per year" % (config.SOLAR_DEGRADATION_PER_YEAR * 100),
            "om": "%.0f%% of capex per year" % (config.SOLAR_OM_FRACTION_PER_YEAR * 100),
            "emission_factor": "%.2f kg CO2/kWh (approx., CEA)"
                               % config.GRID_EMISSION_FACTOR_KG_PER_KWH,
        },
    }
