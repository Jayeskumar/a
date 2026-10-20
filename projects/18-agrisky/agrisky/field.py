"""Deterministic synthetic multispectral drone flights over one maize field.

The field is a FIELD_W x FIELD_H raster of 1 m cells. Each cell's reflectance in four bands
(green, red, red-edge, NIR) comes from a linear mixing model:

    reflectance = cover * leaf + (1 - cover) * background
    leaf        = lerp(LEAF_HEALTHY, LEAF_CHLOROTIC, chlorosis), NIR scaled by (1 - tissue damage)
    background  = lerp(lerp(SOIL_DRY, SOIL_WET, wetness), WATER, standing-water fraction)

Plant-health scenarios change cover / chlorosis / wetness / damage:
  * nitrogen-deficient strip (a missed fertiliser pass): chlorosis up, cover slightly down
  * waterlogged patch (low spot near the channel): standing water, stunting, some yellowing
  * pest outbreak from a corner, front advancing every day: defoliation + NIR tissue loss
  * bunds (bare soil, sparse weeds) and an irrigation channel (open water)
Every flight also carries the generator's ground-truth class per cell for evaluation.
"""
import math
import random

from . import config

W, H = config.FIELD_W, config.FIELD_H
N_CELLS = W * H
CLASS_INDEX = {c: i for i, c in enumerate(config.CLASSES)}


def _lerp(a, b, t):
    return a + (b - a) * t


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def layout_for_seed(seed):
    """Scenario geometry that varies with the seed (so hold-out seeds are new fields)."""
    rng = random.Random("agrisky-layout-%d" % seed)
    pest_right = rng.random() < 0.5 if seed != config.DEFAULT_SEED else True
    # pest corner: bottom-right or bottom-left (inner corner of the outer bund)
    origin = (W - 1.0, H - 1.0) if pest_right else (1.0, H - 1.0)
    # the nitrogen strip lies in the other plot
    sw = rng.randint(*config.NITROGEN_STRIP_W)
    if pest_right:
        nx0 = rng.randint(8, config.INNER_BUND_X - sw - 6)
    else:
        nx0 = rng.randint(config.INNER_BUND_X + 6, W - sw - 8)
    strip = (nx0, nx0 + sw)          # [x0, x1)
    rx = rng.uniform(*config.WATERLOG_RX)
    ry = rng.uniform(*config.WATERLOG_RY)
    for _ in range(200):
        cx = rng.uniform(rx + 4, W - rx - 4)
        cy = rng.uniform(4 + ry, 28)
        mid = (strip[0] + strip[1]) / 2.0
        if abs(cx - mid) > rx + sw / 2.0 + 4:
            break
    return {
        "seed": seed,
        "pest_origin": origin,
        "pest_corner": "bottom-right" if pest_right else "bottom-left",
        "pest_r0": rng.uniform(*config.PEST_R0_M),
        "pest_speed": rng.uniform(*config.PEST_SPEED_M_DAY),
        "pest_harmonics": [(3, rng.uniform(0.06, 0.12), rng.uniform(0, 2 * math.pi)),
                           (5, rng.uniform(0.03, 0.07), rng.uniform(0, 2 * math.pi))],
        "nitrogen_strip": strip,
        "waterlog": (cx, cy, rx, ry),
        "vigour": [(rng.uniform(0.02, 0.08), rng.uniform(0.02, 0.08),
                    rng.uniform(0, 2 * math.pi)) for _ in range(3)],
    }


def static_class(x, y):
    """Furniture that never changes: outer/inner bunds and the irrigation channel."""
    if x == 0 or y == 0 or x == W - 1 or y == H - 1:
        return "soil"
    if y in config.CHANNEL_ROWS:
        return "water"
    if x == config.INNER_BUND_X:
        return "soil"
    return None


def pest_severity(layout, x, y, day):
    ox, oy = layout["pest_origin"]
    dx, dy = (x + 0.5) - ox, (y + 0.5) - oy
    d = math.hypot(dx, dy)
    theta = math.atan2(abs(dy), abs(dx))     # 0..pi/2 inside the corner quadrant
    mod = 1.0
    for k, amp, ph in layout["pest_harmonics"]:
        mod += amp * math.sin(k * theta + ph)
    radius = (layout["pest_r0"] + layout["pest_speed"] * day) * mod
    return _clamp((radius - d) / config.PEST_RAMP_M)


def pest_front_radius(layout, day):
    """Mean front radius (m) at a given day - the generator's truth for the spread rate."""
    return layout["pest_r0"] + layout["pest_speed"] * day


def _memberships(layout, x, y):
    x0, x1 = layout["nitrogen_strip"]
    cxm = x + 0.5
    # soft 1 m edges on the strip
    m_n = _clamp(min(cxm - x0, x1 - cxm) + 0.5)
    cx, cy, rx, ry = layout["waterlog"]
    e = ((cxm - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2
    m_w = _clamp(1.0 - e)
    return m_n, m_w


def _vigour(layout, x, y):
    v = 0.0
    for fx, fy, ph in layout["vigour"]:
        v += math.sin(fx * x + fy * y + ph)
    return 1.0 + config.VIGOUR_AMPLITUDE * v / 1.5


def _mix(cover, chlorosis, nir_damage, wetness, water_frac):
    out = []
    for b in range(4):
        leaf = _lerp(config.LEAF_HEALTHY[b], config.LEAF_CHLOROTIC[b], chlorosis)
        if b == 3:
            leaf *= (1.0 - nir_damage)
        soil = _lerp(config.SOIL_DRY[b], config.SOIL_WET[b], wetness)
        bg = _lerp(soil, config.WATER[b], water_frac)
        out.append(cover * leaf + (1.0 - cover) * bg)
    return out


def cell_state(layout, x, y, flight_index):
    """Physical state + ground-truth class of one cell (no noise)."""
    day = config.FLIGHT_DAYS[flight_index]
    fixed = static_class(x, y)
    if fixed == "water":
        return {"cover": 0.02, "chlorosis": 0.3, "nir_damage": 0.0, "wetness": 1.0,
                "water_frac": 1.0, "truth": "water", "severity": 0.0}
    if fixed == "soil":
        return {"cover": config.BUND_COVER, "chlorosis": 0.3, "nir_damage": 0.0, "wetness": 0.0,
                "water_frac": 0.0, "truth": "soil", "severity": 0.0}
    cover = config.CANOPY_COVER[flight_index] * _vigour(layout, x, y)
    chl = config.HEALTHY_CHLOROSIS
    wet = config.SOIL_WETNESS
    water = 0.0
    damage = 0.0
    m_n, m_w = _memberships(layout, x, y)
    s = pest_severity(layout, x, y, day)
    if m_n > 0:
        chl = _lerp(chl, config.NITROGEN_CHLOROSIS[flight_index], m_n)
        cover *= 1.0 - config.NITROGEN_COVER_LOSS * m_n
    if m_w > 0:
        water = config.WATERLOG_WATER_FRAC * min(1.0, 1.6 * m_w)
        wet = _lerp(wet, 1.0, min(1.0, 2.0 * m_w))
        cover *= 1.0 - config.WATERLOG_COVER_LOSS * m_w
        chl += config.WATERLOG_CHLOROSIS * m_w
    if s > 0:
        cover *= 1.0 - config.PEST_DEFOLIATION * s
        damage = config.PEST_NIR_LOSS * s
        chl += 0.1 * s
    if m_w >= config.TRUTH_WATERLOG_MEMBERSHIP:
        truth, sev = "waterlogging", m_w
    elif s >= config.TRUTH_PEST_SEVERITY:
        truth, sev = "pest", s
    elif m_n >= config.TRUTH_NITROGEN_MEMBERSHIP:
        truth, sev = "nitrogen", m_n
    else:
        truth, sev = "healthy", 0.0
    return {"cover": _clamp(cover), "chlorosis": _clamp(chl), "nir_damage": damage,
            "wetness": wet, "water_frac": water, "truth": truth, "severity": sev}


def generate_flight(layout, flight_index, noise=config.SENSOR_NOISE):
    rng = random.Random("agrisky-noise-%d-%d" % (layout["seed"], flight_index))
    gauss = rng.gauss
    bands = {b: [0.0] * N_CELLS for b in config.BANDS}
    bl = [bands[b] for b in config.BANDS]
    truth = [0] * N_CELLS
    for y in range(H):
        for x in range(W):
            i = y * W + x
            st = cell_state(layout, x, y, flight_index)
            refl = _mix(st["cover"], st["chlorosis"], st["nir_damage"], st["wetness"],
                        st["water_frac"])
            for b in range(4):
                v = refl[b] + gauss(0.0, noise) if noise > 0 else refl[b]
                bl[b][i] = round(max(0.003, v), 4)
            truth[i] = CLASS_INDEX[st["truth"]]
    day = config.FLIGHT_DAYS[flight_index]
    return {"index": flight_index, "day": day, "das": config.DAS_AT_FIRST_FLIGHT + day,
            "bands": bands, "truth": truth}


def generate(seed=config.DEFAULT_SEED, noise=config.SENSOR_NOISE, pest=True):
    """All flights for one seeded field. pest=False builds a control field with no outbreak."""
    layout = layout_for_seed(seed)
    if not pest:
        layout["pest_r0"] = -1e9
    flights = [generate_flight(layout, k, noise) for k in range(len(config.FLIGHT_DAYS))]
    return {"seed": seed, "width": W, "height": H, "cell_m": config.CELL_M,
            "layout": layout, "flights": flights}


def truth_names(truth):
    return [config.CLASSES[t] for t in truth]


def write_sample(path, seed=config.DEFAULT_SEED):
    """Persist the default demo flights as compact JSON (bands x1000 as ints)."""
    import json
    data = generate(seed)
    out = {"seed": seed, "width": W, "height": H, "cell_m": config.CELL_M,
           "bands": list(config.BANDS), "classes": list(config.CLASSES),
           "scale": 1000, "flights": []}
    for f in data["flights"]:
        out["flights"].append({
            "day": f["day"], "das": f["das"],
            "bands": {b: [int(round(v * 1000)) for v in f["bands"][b]] for b in config.BANDS},
            "truth": f["truth"]})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    return path
