"""Variable-rate prescription maps and the comparison with uniform (blanket) application.

Pesticide: spot-spray pest zones plus a PEST_BUFFER_M ring at the full label rate (we never
under-dose: variable rate here means "only where needed"), and nothing within
WATER_NO_SPRAY_M of open water.
Urea: corrective top-dressing only on nitrogen-deficient zones, dose scaled by the red-edge
deficit (UREA_BASE_KG_HA x clamp(deficit / UREA_DEFICIT_REF, 0.6, 1.5)); waterlogged zones
get none until drained (urea on waterlogged soil is largely lost).
The baseline is the usual practice of applying the same dose over the whole cropped area.
"""
from . import config, segment
from .field import W, H

PRODUCTS = {
    "pesticide": {"en": "Pesticide (spot spray)", "ta": "பூச்சிக்கொல்லி", "unit": "L",
                  "rate_unit": "L/ha", "payload_unit": "L", "payload_name": "tank mix"},
    "urea": {"en": "Urea top-dressing", "ta": "யூரியா", "unit": "kg", "rate_unit": "kg/ha",
             "payload_unit": "kg", "payload_name": "urea granules"},
}


def urea_dose(zone):
    deficit = max(0.0, 1.0 - zone["ratios"]["ndre"])
    factor = deficit / config.UREA_DEFICIT_REF
    factor = max(config.UREA_MIN_FACTOR, min(config.UREA_MAX_FACTOR, factor))
    return round(config.UREA_BASE_KG_HA * factor, 1)


def no_spray_mask(cell_class, radius=config.WATER_NO_SPRAY_M):
    water = [c == "water" for c in cell_class]
    return segment.dilate(water, W, H, radius)


def build(analysis, product="pesticide", buffer_m=config.PEST_BUFFER_M,
          water_buffer_m=config.WATER_NO_SPRAY_M):
    if product not in PRODUCTS:
        raise ValueError("product must be one of: %s" % ", ".join(PRODUCTS))
    cell_class = analysis["cell_class"]
    zgrid = analysis["zones_grid"]
    zones = analysis["zones"]
    crop = [c in config.CROP_CLASSES for c in cell_class]
    crop_cells = sum(crop)
    crop_ha = crop_cells * config.CELL_AREA_M2 / config.M2_PER_HA
    blocked = no_spray_mask(cell_class, water_buffer_m)
    rate = [0.0] * len(cell_class)        # product dose per cell (L/ha or kg/ha)
    rows = []
    if product == "pesticide":
        pest = [c == "pest" for c in cell_class]
        ring = segment.dilate(pest, W, H, int(buffer_m))
        dose = config.PESTICIDE_PRODUCT_L_HA
        zone_cells = {}
        buffer_cells = 0
        excluded = 0
        for i in range(len(cell_class)):
            if not ring[i] or not crop[i]:
                continue
            if blocked[i]:
                excluded += 1
                continue
            rate[i] = dose
            if pest[i]:
                zone_cells[zgrid[i]] = zone_cells.get(zgrid[i], 0) + 1
            else:
                buffer_cells += 1
        for z in zones:
            n = zone_cells.get(z["id"], 0)
            if z["label"] == "pest":
                rows.append(_row(z["id"], "pest", n, dose, "L/ha",
                                 "Full label rate on damaged canopy" +
                                 (" (actively spreading)" if z.get("spreading") else "")))
        if buffer_cells:
            rows.append(_row("ring", "buffer", buffer_cells, dose, "L/ha",
                             "%d m ring to stop the advancing front" % buffer_m))
        payload_rate = config.SPRAY_VOLUME_L_HA
        uniform_dose = dose
        price = config.PESTICIDE_PRICE_RS_PER_L
        notes = {"excluded_near_water_cells": excluded}
    else:
        excluded = 0
        for z in zones:
            if z["label"] == "nitrogen":
                d = urea_dose(z)
                n = 0
                for i, zi in enumerate(zgrid):
                    if zi == z["id"]:
                        if blocked[i]:
                            excluded += 1
                            continue
                        rate[i] = d
                        n += 1
                rows.append(_row(z["id"], "nitrogen", n, d, "kg/ha",
                                 "NDRE %.0f%% below reference → %.2f × base dose"
                                 % ((1 - z["ratios"]["ndre"]) * 100, d / config.UREA_BASE_KG_HA)))
            elif z["label"] == "waterlogging":
                rows.append(_row(z["id"], "waterlogging", 0, 0.0, "kg/ha",
                                 "Hold urea: drain first (N would be lost)"))
        payload_rate = None
        uniform_dose = config.UREA_BASE_KG_HA
        price = config.UREA_PRICE_RS_PER_KG
        notes = {"excluded_near_water_cells": excluded}
    target_cells = sum(1 for r in rate if r > 0)
    vra_amount = sum(rate) * config.CELL_AREA_M2 / config.M2_PER_HA
    uni_amount = uniform_dose * crop_ha
    saved = uni_amount - vra_amount
    pct = 100.0 * saved / uni_amount if uni_amount else 0.0
    # payload (what the drone carries) per cell in units per m^2
    payload = [0.0] * len(rate)
    for i, r in enumerate(rate):
        if r > 0:
            payload[i] = (payload_rate if payload_rate is not None else r) / config.M2_PER_HA
    uni_payload_rate = payload_rate if payload_rate is not None else uniform_dose
    meta = PRODUCTS[product]
    return {
        "product": product, "label_en": meta["en"], "label_ta": meta["ta"],
        "unit": meta["unit"], "rate_unit": meta["rate_unit"],
        "payload_unit": meta["payload_unit"], "payload_name": meta["payload_name"],
        "rows": rows, "cell_rate": [round(r, 3) for r in rate], "payload_per_m2": payload,
        "target_cells": target_cells, "target_area_m2": round(target_cells * config.CELL_AREA_M2, 1),
        "crop_area_m2": round(crop_cells * config.CELL_AREA_M2, 1),
        "vra": {"amount": round(vra_amount, 3), "cost_rs": round(vra_amount * price, 1),
                "payload": round(sum(payload) * config.CELL_AREA_M2, 2)},
        "uniform": {"amount": round(uni_amount, 3), "cost_rs": round(uni_amount * price, 1),
                    "dose": uniform_dose,
                    "payload": round(uni_payload_rate * crop_ha, 2)},
        "savings": {"amount": round(saved, 3), "pct": round(pct, 1),
                    "rs": round(saved * price, 1),
                    "rs_per_ha": round(saved * price / crop_ha, 0) if crop_ha else 0.0,
                    "area_pct_treated": round(100.0 * target_cells / crop_cells, 1)
                    if crop_cells else 0.0},
        "price_rs_per_unit": round(price, 2), "notes": notes,
        "assumptions": {
            "pesticide_l_ha": config.PESTICIDE_PRODUCT_L_HA,
            "pesticide_rs_l": config.PESTICIDE_PRICE_RS_PER_L,
            "spray_volume_l_ha": config.SPRAY_VOLUME_L_HA,
            "urea_base_kg_ha": config.UREA_BASE_KG_HA,
            "urea_rs_kg": round(config.UREA_PRICE_RS_PER_KG, 2),
            "pest_buffer_m": buffer_m, "water_no_spray_m": water_buffer_m},
    }


def _row(zone_id, label, cells, dose, unit, why):
    area = cells * config.CELL_AREA_M2
    return {"zone": zone_id, "label": label, "cells": cells, "area_m2": round(area, 1),
            "dose": dose, "unit": unit,
            "amount": round(dose * area / config.M2_PER_HA, 3), "why": why}
