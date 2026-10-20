"""Annual impact projection from the simulated month, with every assumption visible."""

from . import config as C


def project(fixed_totals, smart_totals, diesel_inr=None, scale_bins=None, km_per_l=None):
    """Scale the simulated month's average daily savings to a year (and optionally a bigger town).

    fixed_totals / smart_totals: World.totals() of the two policies over the same days.
    diesel_inr : override DIESEL_INR_PER_L
    scale_bins : project for a town with this many smart bins (linear scaling - rough)
    km_per_l   : override TRUCK_KM_PER_L (fuel is recomputed from km and service hours)
    """
    days = max(1, fixed_totals["days"])
    price = C.DIESEL_INR_PER_L if diesel_inr is None else float(diesel_inr)
    kmpl = C.TRUCK_KM_PER_L if km_per_l is None else float(km_per_l)
    scale = 1.0 if not scale_bins else float(scale_bins) / C.N_BINS
    factor = C.COLLECTION_DAYS_PER_YEAR / days * scale

    def fuel(t):
        service_h = t["stops"] * C.SERVICE_MIN_PER_BIN / 60.0
        return t["km"] / kmpl + service_h * C.IDLE_L_PER_H

    f_fuel, s_fuel = fuel(fixed_totals), fuel(smart_totals)
    km_saved = (fixed_totals["km"] - smart_totals["km"]) * factor
    fuel_saved = (f_fuel - s_fuel) * factor
    out = {
        "basis_days": days,
        "scale_bins": int(scale_bins) if scale_bins else C.N_BINS,
        "scale_factor": round(scale, 3),
        "diesel_inr_per_l": price,
        "km_per_l": kmpl,
        "annual": {
            "km_saved": round(km_saved, 0),
            "fuel_saved_l": round(fuel_saved, 0),
            "money_saved_inr": round(fuel_saved * price, 0),
            "co2_saved_t": round(fuel_saved * C.CO2_KG_PER_L_DIESEL / 1000.0, 2),
            "truck_hours_freed": round((fixed_totals["truck_hours"] - smart_totals["truck_hours"])
                                       * factor, 0),
            "overflow_events_avoided": round((fixed_totals["overflow_bins"]
                                              - smart_totals["overflow_bins"]) * factor, 0),
            "spilled_litres_avoided": round((fixed_totals["overflow_l"] - smart_totals["overflow_l"])
                                            * factor, 0),
            "pickups_avoided": round((fixed_totals["stops"] - smart_totals["stops"]) * factor, 0),
        },
        "per_day": {
            "fixed_km": round(fixed_totals["km"] / days, 2),
            "smart_km": round(smart_totals["km"] / days, 2),
            "fixed_fuel_l": round(f_fuel / days, 2),
            "smart_fuel_l": round(s_fuel / days, 2),
        },
        "pct": {
            "km": round(100.0 * (1 - smart_totals["km"] / fixed_totals["km"]), 1)
            if fixed_totals["km"] else 0.0,
            "fuel": round(100.0 * (1 - s_fuel / f_fuel), 1) if f_fuel else 0.0,
        },
        "formulas": [
            "fuel_L = km / TRUCK_KM_PER_L + stops x SERVICE_MIN_PER_BIN/60 x IDLE_L_PER_H",
            "CO2_kg = fuel_L x CO2_KG_PER_L_DIESEL (%.2f)" % C.CO2_KG_PER_L_DIESEL,
            "money_INR = fuel_L x DIESEL_INR_PER_L",
            "annual = (fixed - smart over %d simulated days) x %d / %d x (bins / %d)" % (
                days, C.COLLECTION_DAYS_PER_YEAR, days, C.N_BINS),
        ],
        "assumptions": C.assumptions(),
        "caveats": [
            "Linear scaling to more bins is rough: denser towns save less per bin, sparser more.",
            "Fuel model ignores load-dependent consumption and traffic variation.",
            "All money figures use the diesel price above; crew wages are not included.",
        ],
    }
    return out
