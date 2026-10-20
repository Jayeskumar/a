"""Carbon and cost accounting (all factors come from config.py)."""

from . import config


def co2_kg(kwh, factor=config.GRID_EMISSION_FACTOR_KG_PER_KWH):
    return kwh * factor


def cost_inr(kwh, tariff=config.TARIFF_INR_PER_KWH):
    return kwh * tariff


def trees_equivalent(co2_kg_per_year):
    """Trees needed to absorb this much CO2 in one year."""
    return co2_kg_per_year / config.TREE_KG_CO2_PER_YEAR


def footprint(kwh, days):
    """Cost and carbon for ``kwh`` consumed over ``days`` days, plus annualised."""
    annual_kwh = kwh * 365.0 / days if days else 0.0
    return {
        "kwh": round(kwh, 1),
        "cost_inr": round(cost_inr(kwh)),
        "co2_kg": round(co2_kg(kwh), 1),
        "annual_kwh": round(annual_kwh),
        "annual_cost_inr": round(cost_inr(annual_kwh)),
        "annual_co2_t": round(co2_kg(annual_kwh) / 1000.0, 1),
        "trees_to_offset_per_year": round(trees_equivalent(co2_kg(annual_kwh))),
    }


def assumptions():
    return {
        "grid_emission_factor_kg_per_kwh": config.GRID_EMISSION_FACTOR_KG_PER_KWH,
        "grid_emission_factor_source": "approx. - CEA CO2 Baseline Database, India grid ~0.7",
        "tariff_inr_per_kwh": config.TARIFF_INR_PER_KWH,
        "tariff_source": "approx. planning assumption for an institutional tariff",
        "tree_kg_co2_per_year": config.TREE_KG_CO2_PER_YEAR,
        "tree_source": "approx. commonly quoted ~21 kg CO2 per mature tree per year",
    }
