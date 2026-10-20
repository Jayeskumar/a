"""Crop calendar: sowing -> harvest stages from the FAO-56 style stage lengths."""
import datetime as _dt

from . import config
from .i18n import t

LAND_PREP_DAYS = 15     # approx. ploughing / puddling before sowing (assumption)
NURSERY_DAYS = 25       # approx. nursery age at transplanting for transplanted crops
HARVEST_WINDOW = 10     # last N days of the season shown as the harvest window


def calendar(crop, sowing_date, today=None):
    if crop not in config.STAGE_DAYS:
        raise ValueError("unknown crop: %s" % crop)
    l1, l2, l3, l4 = config.STAGE_DAYS[crop]
    total = l1 + l2 + l3 + l4
    d0 = sowing_date

    def day(n):
        return (d0 + _dt.timedelta(days=n)).isoformat()

    stages = []
    if crop not in config.PERENNIAL:
        stages.append({"key": "land_prep", "label": t("st_land_prep"),
                       "start": day(-LAND_PREP_DAYS), "end": day(0)})
    if crop in config.TRANSPLANTED:
        stages.append({"key": "nursery", "label": t("st_nursery"), "start": day(-NURSERY_DAYS),
                       "end": day(0)})
    bounds = [0, l1, l1 + l2, l1 + l2 + l3, total]
    keys = ["initial", "development", "mid", "late"]
    for i, k in enumerate(keys):
        stages.append({"key": k, "label": t("st_" + k), "start": day(bounds[i]),
                       "end": day(bounds[i + 1]), "kc": _kc_label(crop, k)})
    stages.append({"key": "harvest", "label": t("st_harvest"), "start": day(total - HARVEST_WINDOW),
                   "end": day(total)})
    sow_key = "op_transplant" if crop in config.TRANSPLANTED else "op_sow"
    ops = [
        {"date": day(0), "text": t(sow_key)},
        {"date": day(min(l1, 30)), "text": t("op_topdress1")},
        {"date": day(l1 + l2), "text": t("op_flowering")},
        {"date": day(total - HARVEST_WINDOW), "text": t("op_harvest")},
    ]
    if crop in config.PERENNIAL:      # established palm: yearly care cycle instead
        ops = [
            {"date": day(0), "text": t("op_palm_cycle")},
            {"date": day(l1 + l2 // 2), "text": t("op_palm_split2")},
            {"date": day(l1 + l2 + l3 // 2), "text": t("op_palm_summer")},
            {"date": day(total - HARVEST_WINDOW), "text": t("op_palm_harvest")},
        ]
    today = today or _dt.date.today()
    return {
        "crop": crop, "sowing_date": d0.isoformat(), "harvest_date": day(total),
        "duration_days": total, "today": today.isoformat(),
        "days_after_sowing": (today - d0).days, "stages": stages, "operations": ops,
        "perennial": crop in config.PERENNIAL,
    }


def _kc_label(crop, stage):
    kc_ini, kc_mid, kc_end = config.KC[crop]
    return {"initial": "%.2f" % kc_ini, "development": "%.2f-%.2f" % (kc_ini, kc_mid),
            "mid": "%.2f" % kc_mid, "late": "%.2f-%.2f" % (kc_mid, kc_end)}[stage]
