"""Farmer report (English + Tamil summary lines) and prescription exports (CSV, GeoJSON)."""
import csv
import io
import math

from . import config
from .field import W, H


def _area(a, cls):
    return sum(1 for c in a["cell_class"] if c == cls) * config.CELL_AREA_M2


def _fmt(v, nd=1):
    return ("%%.%df" % nd) % v


def farmer_report(a, ch, rx_p, rx_u, m_vra, m_uni):
    total = len(a["cell_class"]) * config.CELL_AREA_M2
    crop = sum(1 for c in a["cell_class"] if c in config.CROP_CLASSES) * config.CELL_AREA_M2
    das = config.DAS_AT_FIRST_FLIGHT + a["day"]
    n = a["index"] + 1
    lines = []

    def add(key, en, ta, level="info"):
        lines.append({"key": key, "en": en, "ta": ta, "level": level})

    add("field",
        "Field %.2f ha (crop %.2f ha), %s at %d days after sowing - drone flight %d (day %d)."
        % (total / 1e4, crop / 1e4, config.CROP.lower(), das, n, a["day"]),
        "வயல் %.2f ஹெக்டேர் (பயிர் %.2f ஹெ.), மக்காச்சோளம் விதைத்து %d நாட்கள் - ட்ரோன் பறப்பு %d."
        % (total / 1e4, crop / 1e4, das, n))
    healthy = _area(a, "healthy")
    add("healthy",
        "Healthy crop on %.0f%% of the crop area - no treatment needed there." % (100 * healthy / crop),
        "பயிர்ப் பரப்பில் %.0f%% ஆரோக்கியமாக உள்ளது - அங்கு சிகிச்சை தேவையில்லை." % (100 * healthy / crop),
        "ok")
    pest = _area(a, "pest")
    speed = ch["spread"].get("front_speed_m_day") if ch else None
    if pest > 0:
        spreading = speed is not None and speed >= config.ALERT_FRONT_SPEED_M_DAY
        en = "Pest damage on %.0f m² (%.1f%% of crop)" % (pest, 100 * pest / crop)
        ta = "%.0f ச.மீ (பயிரில் %.1f%%) பரப்பில் பூச்சித் தாக்குதல்" % (pest, 100 * pest / crop)
        if spreading:
            en += ", spreading about %.1f m per day." % speed
            ta += ", நாளொன்றுக்கு சுமார் %.1f மீ பரவுகிறது." % speed
        else:
            en += "."
            ta += "."
        add("pest", en, ta, "danger" if spreading else "warn")
        add("spray",
            "Spray pesticide only on %.0f m² (damage + %d m ring): %.2f L product in %.1f L tank mix, "
            "%d drone sortie%s."
            % (rx_p["target_area_m2"], config.PEST_BUFFER_M, rx_p["vra"]["amount"],
               m_vra["totals"]["payload"], m_vra["totals"]["sorties"],
               "" if m_vra["totals"]["sorties"] == 1 else "s"),
            "பூச்சிக்கொல்லியை %.0f ச.மீ பரப்பில் மட்டும் தெளிக்கவும் (பாதிப்பு + %d மீ வளையம்): "
            "%.2f லி மருந்து, %.1f லி கலவை, %d ட்ரோன் சுற்று."
            % (rx_p["target_area_m2"], config.PEST_BUFFER_M, rx_p["vra"]["amount"],
               m_vra["totals"]["payload"], m_vra["totals"]["sorties"]), "action")
    nitro = _area(a, "nitrogen")
    if nitro > 0:
        doses = [r["dose"] for r in rx_u["rows"] if r["label"] == "nitrogen"]
        dose = max(doses) if doses else config.UREA_BASE_KG_HA
        add("nitrogen",
            "Nitrogen deficiency on %.0f m²: top-dress %.1f kg urea only on the yellow strip (%.0f kg/ha)."
            % (nitro, rx_u["vra"]["amount"], dose),
            "%.0f ச.மீ பரப்பில் தழைச்சத்து பற்றாக்குறை: மஞ்சள் பட்டையில் மட்டும் %.1f கிலோ யூரியா "
            "இடவும் (%.0f கிலோ/ஹெ)." % (nitro, rx_u["vra"]["amount"], dose), "action")
    wl = _area(a, "waterlogging")
    if wl > 0:
        add("waterlogging",
            "Waterlogging on %.0f m²: open the drain; do not apply urea there until it dries." % wl,
            "%.0f ச.மீ பரப்பில் நீர்த் தேக்கம்: வடிகாலைத் திறக்கவும்; காயும் வரை அங்கு யூரியா "
            "இட வேண்டாம்." % wl, "warn")
    rs = rx_p["savings"]["rs"] + rx_u["savings"]["rs"]
    add("savings",
        "Compared with treating the whole field you save %.0f%% pesticide and %.0f%% urea - about "
        "₹%.0f this round (₹%.0f per ha)."
        % (rx_p["savings"]["pct"], rx_u["savings"]["pct"], rs, rs / (crop / 1e4) if crop else 0),
        "முழு வயலுக்கும் இடுவதை விட %.0f%% பூச்சிக்கொல்லி, %.0f%% யூரியா மிச்சம் - இந்தச் சுற்றில் "
        "சுமார் ₹%.0f சேமிப்பு." % (rx_p["savings"]["pct"], rx_u["savings"]["pct"], rs), "ok")
    add("safety",
        "No spraying within %d m of the irrigation channel. Wear a mask and gloves while mixing."
        % config.WATER_NO_SPRAY_M,
        "வாய்க்காலில் இருந்து %d மீ தூரத்திற்குள் தெளிக்க வேண்டாம். மருந்து கலக்கும்போது "
        "முகக்கவசம், கையுறை அணியவும்." % config.WATER_NO_SPRAY_M, "info")
    add("next",
        "Fly the drone again in 7 days to check that the damage has stopped spreading.",
        "பாதிப்பு பரவல் நின்றதா என அறிய 7 நாட்களில் மீண்டும் ட்ரோனைப் பறக்கவிடவும்.", "info")
    return {
        "title": "AgriSky field report - flight %d (day %d)" % (n, a["day"]),
        "title_ta": "அக்ரிஸ்கை வயல் அறிக்கை - பறப்பு %d" % n,
        "lines": lines,
        "summary": {
            "field_ha": round(total / 1e4, 3), "crop_ha": round(crop / 1e4, 3),
            "healthy_m2": healthy, "pest_m2": pest, "nitrogen_m2": nitro, "waterlogging_m2": wl,
            "pesticide_saved_pct": rx_p["savings"]["pct"], "urea_saved_pct": rx_u["savings"]["pct"],
            "rs_saved": round(rs, 0),
            "sorties_vra": m_vra["totals"]["sorties"], "sorties_uniform": m_uni["totals"]["sorties"],
            "alert": ch["spread"]["alert"] if ch else None},
    }


# ------------------------------------------------------------------------ exports
def _latlon(x_m, y_m):
    lat0 = config.FIELD_ORIGIN_LAT
    lat = lat0 - y_m / config.M_PER_DEG_LAT
    lon = config.FIELD_ORIGIN_LON + x_m / (config.M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    return round(lat, 7), round(lon, 7)


def zone_table(a, rx_p, rx_u):
    """Per-zone prescription rows (amounts summed from the per-cell rate maps)."""
    rows = []
    cell_area_ha = config.CELL_AREA_M2 / config.M2_PER_HA
    sums = {}
    for i, z in enumerate(a["zones_grid"]):
        s = sums.setdefault(z, [0.0, 0.0, 0, 0])
        if rx_p["cell_rate"][i] > 0:
            s[0] += rx_p["cell_rate"][i] * cell_area_ha
            s[2] += 1
        if rx_u["cell_rate"][i] > 0:
            s[1] += rx_u["cell_rate"][i] * cell_area_ha
            s[3] += 1
    for z in a["zones"]:
        p_l, u_kg, p_cells, u_cells = sums.get(z["id"], [0.0, 0.0, 0, 0])
        lat, lon = _latlon(z["centroid"][0] * config.CELL_M, z["centroid"][1] * config.CELL_M)
        rows.append({
            "zone_id": z["id"], "class": z["label"], "class_en": config.CLASS_INFO[z["label"]]["en"],
            "area_m2": z["area_m2"], "pct_field": z["pct_field"],
            "mean_ndvi": round(z["ndvi"], 3), "mean_ndre": round(z["ndre"], 3),
            "pesticide_area_m2": p_cells * config.CELL_AREA_M2,
            "pesticide_l_ha": config.PESTICIDE_PRODUCT_L_HA if p_cells else 0.0,
            "pesticide_l": round(p_l, 3),
            "urea_area_m2": u_cells * config.CELL_AREA_M2,
            "urea_kg_ha": round(u_kg / (u_cells * cell_area_ha), 1) if u_cells else 0.0,
            "urea_kg": round(u_kg, 2),
            "centroid_lat": lat, "centroid_lon": lon, "reason": z["why"]})
    return rows


def prescription_csv(a, rx_p, rx_u):
    rows = zone_table(a, rx_p, rx_u)
    buf = io.StringIO()
    cols = ["zone_id", "class", "area_m2", "pct_field", "mean_ndvi", "mean_ndre",
            "pesticide_area_m2", "pesticide_l_ha", "pesticide_l", "urea_area_m2", "urea_kg_ha",
            "urea_kg", "centroid_lat", "centroid_lon", "reason"]
    wr = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    wr.writeheader()
    for r in rows:
        wr.writerow(r)
    wr.writerow({"zone_id": "TOTAL", "class": "", "area_m2": sum(r["area_m2"] for r in rows),
                 "pesticide_area_m2": sum(r["pesticide_area_m2"] for r in rows),
                 "pesticide_l": round(sum(r["pesticide_l"] for r in rows), 3),
                 "urea_area_m2": sum(r["urea_area_m2"] for r in rows),
                 "urea_kg": round(sum(r["urea_kg"] for r in rows), 2),
                 "reason": "uniform would use %.3f L pesticide and %.2f kg urea"
                           % (rx_p["uniform"]["amount"], rx_u["uniform"]["amount"])})
    return buf.getvalue()


def rectangles(cells, w):
    """Cover a set of cells with axis-aligned rectangles (row runs merged downwards)."""
    by_row = {}
    for i in cells:
        by_row.setdefault(i // w, []).append(i % w)
    active = {}
    done = []
    for y in sorted(by_row):
        xs = sorted(by_row[y])
        runs = []
        start = prev = xs[0]
        for x in xs[1:]:
            if x == prev + 1:
                prev = x
                continue
            runs.append((start, prev + 1))
            start = prev = x
        runs.append((start, prev + 1))
        nxt = {}
        for r in runs:
            if r in active and active[r][3] == y:
                x0, x1, y0, _ = active.pop(r)
                nxt[r] = (x0, x1, y0, y + 1)
            else:
                nxt[r] = (r[0], r[1], y, y + 1)
        done.extend(active.values())
        active = nxt
    done.extend(active.values())
    return sorted(done, key=lambda t: (t[2], t[0]))


def prescription_geojson(a, rx_p, rx_u):
    rows = {r["zone_id"]: r for r in zone_table(a, rx_p, rx_u)}
    cells_of = {}
    for i, z in enumerate(a["zones_grid"]):
        cells_of.setdefault(z, []).append(i)
    feats = []
    for z in a["zones"]:
        polys = []
        for x0, x1, y0, y1 in rectangles(cells_of[z["id"]], W):
            ring = [_latlon(x0, y0), _latlon(x1, y0), _latlon(x1, y1), _latlon(x0, y1), _latlon(x0, y0)]
            polys.append([[[lon, lat] for lat, lon in ring]])
        props = dict(rows[z["id"]])
        props["color"] = config.CLASS_INFO[z["label"]]["color"]
        feats.append({"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": polys},
                      "properties": props})
    return {"type": "FeatureCollection",
            "name": "agrisky_prescription_flight_%d" % (a["index"] + 1),
            "crs_note": "WGS84 lon/lat; illustrative origin near Tiruchengode, 1 m cells",
            "origin": {"lat": config.FIELD_ORIGIN_LAT, "lon": config.FIELD_ORIGIN_LON},
            "grid": {"width": W, "height": H, "cell_m": config.CELL_M},
            "features": feats}
