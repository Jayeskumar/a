"""Vegetation / water indices on single cells and on whole rasters (flat lists).

NDVI  = (NIR - Red) / (NIR + Red)                 canopy vigour / biomass
GNDVI = (NIR - Green) / (NIR + Green)             chlorophyll, less saturating than NDVI
NDRE  = (NIR - RedEdge) / (NIR + RedEdge)         chlorophyll / nitrogen status (red-edge)
SAVI  = (1 + L) (NIR - Red) / (NIR + Red + L)     NDVI with a soil-brightness correction
NDWI  = (Green - NIR) / (Green + NIR)             McFeeters water index, > 0 over open water
"""
from . import config

INDEX_NAMES = ("ndvi", "gndvi", "ndre", "savi", "ndwi")
INDEX_INFO = {
    "ndvi": {"name": "NDVI", "formula": "(NIR − Red) / (NIR + Red)", "range": (-0.2, 0.9),
             "meaning": "canopy vigour and biomass"},
    "gndvi": {"name": "GNDVI", "formula": "(NIR − Green) / (NIR + Green)", "range": (-0.2, 0.8),
              "meaning": "chlorophyll; saturates later than NDVI"},
    "ndre": {"name": "NDRE", "formula": "(NIR − RedEdge) / (NIR + RedEdge)", "range": (-0.1, 0.4),
             "meaning": "chlorophyll / nitrogen status"},
    "savi": {"name": "SAVI", "formula": "1.5 (NIR − Red) / (NIR + Red + 0.5)", "range": (-0.1, 0.7),
             "meaning": "vigour with soil-brightness correction"},
    "ndwi": {"name": "NDWI", "formula": "(Green − NIR) / (Green + NIR)", "range": (-0.8, 0.6),
             "meaning": "surface water / wetness (> 0 = open water)"},
}


def normalized_difference(a, b):
    """(a - b) / (a + b), defined as 0 when both are 0 (no signal)."""
    s = a + b
    if s == 0:
        return 0.0
    return (a - b) / s


def ndvi(nir, red):
    return normalized_difference(nir, red)


def gndvi(nir, green):
    return normalized_difference(nir, green)


def ndre(nir, rededge):
    return normalized_difference(nir, rededge)


def ndwi(green, nir):
    return normalized_difference(green, nir)


def savi(nir, red, L=config.SAVI_L):
    den = nir + red + L
    if den == 0:
        return 0.0
    return (1.0 + L) * (nir - red) / den


def cell_indices(green, red, rededge, nir):
    """All indices for one cell as a dict."""
    return {
        "ndvi": ndvi(nir, red),
        "gndvi": gndvi(nir, green),
        "ndre": ndre(nir, rededge),
        "savi": savi(nir, red),
        "ndwi": ndwi(green, nir),
    }


def compute_all(bands):
    """bands: {"green": [...], "red": [...], "rededge": [...], "nir": [...]} -> {index: [...]}"""
    g, r, e, n = bands["green"], bands["red"], bands["rededge"], bands["nir"]
    count = len(n)
    out = {k: [0.0] * count for k in INDEX_NAMES}
    o_ndvi, o_gndvi, o_ndre, o_savi, o_ndwi = (out[k] for k in INDEX_NAMES)
    L = config.SAVI_L
    for i in range(count):
        gi, ri, ei, ni = g[i], r[i], e[i], n[i]
        s = ni + ri
        o_ndvi[i] = (ni - ri) / s if s else 0.0
        s = ni + gi
        o_gndvi[i] = (ni - gi) / s if s else 0.0
        o_ndwi[i] = (gi - ni) / s if s else 0.0
        s = ni + ei
        o_ndre[i] = (ni - ei) / s if s else 0.0
        d = ni + ri + L
        o_savi[i] = (1.0 + L) * (ni - ri) / d if d else 0.0
    return out
