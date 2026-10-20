"""Fertiliser advisor: soil test vs crop requirement -> Urea / DAP / MOP per acre.

Calculation (all per hectare first, then converted to per acre):
  1. deficit_X = max(0, dose_X - SOIL_CREDIT_X * soil_X)          X in {N, P2O5, K2O}
  2. DAP  = deficit_P2O5 / 0.46          (DAP supplies the phosphorus...)
     N_from_DAP = DAP * 0.18             (...and some nitrogen as a by-product)
  3. Urea = max(0, deficit_N - N_from_DAP) / 0.46
  4. MOP  = deficit_K2O / 0.60
  5. per acre = per hectare * 0.404686
"""
from . import config
from .i18n import t


def nutrient_deficit(crop, soil_n, soil_p, soil_k):
    req_n, req_p, req_k = config.CROP_NPK_REQUIREMENT[crop]
    cr = config.SOIL_CREDIT
    return {
        "requirement": {"N": req_n, "P2O5": req_p, "K2O": req_k},
        "soil_credit": {"N": round(cr["N"] * soil_n, 2), "P2O5": round(cr["P"] * soil_p, 2),
                        "K2O": round(cr["K"] * soil_k, 2)},
        "deficit": {"N": max(0.0, req_n - cr["N"] * soil_n),
                    "P2O5": max(0.0, req_p - cr["P"] * soil_p),
                    "K2O": max(0.0, req_k - cr["K"] * soil_k)},
    }


def products_per_ha(def_n, def_p, def_k):
    dap = def_p / config.DAP_P2O5
    n_from_dap = dap * config.DAP_N
    urea = max(0.0, def_n - n_from_dap) / config.UREA_N
    mop = def_k / config.MOP_K2O
    return {"urea": urea, "dap": dap, "mop": mop, "n_from_dap": n_from_dap}


def advise(crop, soil_n, soil_p, soil_k, ph=None, area_acres=1.0):
    if crop not in config.CROP_NPK_REQUIREMENT:
        raise ValueError("unknown crop: %s" % crop)
    d = nutrient_deficit(crop, soil_n, soil_p, soil_k)
    de = d["deficit"]
    ha = products_per_ha(de["N"], de["P2O5"], de["K2O"])
    a = config.HA_PER_ACRE
    per_acre = {k: round(v * a, 1) for k, v in ha.items()}
    products = []
    for key in ("urea", "dap", "mop"):
        kg = per_acre[key]
        products.append({
            "product": key, "kg_per_acre": kg,
            "kg_total": round(kg * area_acres, 1),
            "bags_total": round(kg * area_acres / config.BAG_KG[key], 1),
            "bag_kg": config.BAG_KG[key],
        })

    # Generic split schedule: all DAP + MOP basal, urea in three splits (simplified).
    urea = per_acre["urea"]
    schedule = [
        {"when": t("sched_basal"), "what": t("sched_basal_what", dap=per_acre["dap"],
                                              mop=per_acre["mop"], urea=round(urea / 3, 1))},
        {"when": t("sched_top1"), "what": t("sched_urea", urea=round(urea / 3, 1))},
        {"when": t("sched_top2"), "what": t("sched_urea", urea=round(urea / 3, 1))},
    ]
    if urea < 0.5:          # e.g. legumes: DAP already covers the small N need
        schedule = [schedule[0], {"when": t("sched_top1"), "what": t("sched_no_urea")}]
    if crop in config.PERENNIAL:
        schedule = [{"when": t("sched_palm"), "what": t("sched_palm_what", dap=per_acre["dap"],
                                                         mop=per_acre["mop"], urea=urea)}]

    # Organic alternatives: amount needed to replace ORGANIC_SUBSTITUTION of the N deficit.
    n_def_acre = de["N"] * a
    organic = []
    for src, (pn, pp, pk) in config.ORGANIC_SOURCES.items():
        kg = config.ORGANIC_SUBSTITUTION * n_def_acre / (pn / 100.0) if n_def_acre > 0 else 0.0
        organic.append({
            "source": src, "name": t("org_" + src), "pct_npk": [pn, pp, pk],
            "kg_per_acre": round(kg), "supplies": {
                "N": round(kg * pn / 100, 1), "P2O5": round(kg * pp / 100, 1),
                "K2O": round(kg * pk / 100, 1)},
        })
    tips = [t("tip_biofert_legume") if crop in config.LEGUMES else t("tip_biofert")]
    tips.append(t("tip_green_manure"))
    if ph is not None and ph < 5.5:
        tips.append(t("tip_acid", ph=ph))
    elif ph is not None and ph > 8.0:
        tips.append(t("tip_alkaline", ph=ph))

    return {
        "crop": crop, "area_acres": area_acres,
        "requirement_kg_ha": d["requirement"],
        "soil_credit_kg_ha": d["soil_credit"],
        "deficit_kg_ha": {k: round(v, 1) for k, v in de.items()},
        "deficit_kg_acre": {k: round(v * a, 1) for k, v in de.items()},
        "n_from_dap_kg_acre": per_acre["n_from_dap"],
        "products": products,
        "schedule": schedule,
        "organic": organic,
        "tips": tips,
        "summary": t("fert_summary", urea=per_acre["urea"], dap=per_acre["dap"],
                     mop=per_acre["mop"]),
        "formula": ("deficit = max(0, dose - credit x soil); DAP = P2O5/0.46; "
                    "Urea = (N - 0.18 x DAP)/0.46; MOP = K2O/0.60; x0.4047 per acre"),
        "assumptions": {"soil_credit": config.SOIL_CREDIT, "urea_n": config.UREA_N,
                        "dap": [config.DAP_N, config.DAP_P2O5], "mop_k2o": config.MOP_K2O},
    }
