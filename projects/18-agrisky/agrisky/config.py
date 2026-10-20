"""Every tunable assumption of AgriSky in one place.

Numbers marked "approx." are rough, widely quoted orders of magnitude; numbers marked
"illustrative" are placeholders chosen so the demo behaves realistically. Nothing here is a
precise agronomic or commercial recommendation - always follow the product label and local
(TNAU / KVK) advice.
"""

# --------------------------------------------------------------------------- field raster
FIELD_W = 120              # cells along x (east), one cell = CELL_M metres
FIELD_H = 80               # cells along y (south)
CELL_M = 1.0               # drone imagery aggregated to a 1 m grid -> 1 m^2 per cell
CELL_AREA_M2 = CELL_M * CELL_M
M2_PER_HA = 10000.0
DEFAULT_SEED = 42
FLIGHT_DAYS = (0, 7, 14, 21, 28)      # five weekly flights spanning four weeks
CROP = "Maize"
DAS_AT_FIRST_FLIGHT = 30   # days after sowing at flight 1 (illustrative)
SENSOR_NOISE = 0.008       # reflectance std-dev per band (illustrative, calibrated camera)
BANDS = ("green", "red", "rededge", "nir")
# Illustrative geo-reference for the GeoJSON export (a field near Tiruchengode, Namakkal).
FIELD_ORIGIN_LAT = 11.38
FIELD_ORIGIN_LON = 77.89
M_PER_DEG_LAT = 111320.0   # metres per degree of latitude (approx.)

# Field furniture (cell indices). Outer bunds on the border, an internal bund splitting the
# field into two plots, and an irrigation channel running along the top inside the bund.
CHANNEL_ROWS = (1, 2)
INNER_BUND_X = 60

# --------------------------------------------------------------------------- classes
CLASSES = ("healthy", "nitrogen", "waterlogging", "pest", "soil", "water")
CLASS_INFO = {
    "healthy": {"en": "Healthy crop", "ta": "ஆரோக்கியமான பயிர்", "color": "#16a34a"},
    "nitrogen": {"en": "Nitrogen deficiency", "ta": "தழைச்சத்து பற்றாக்குறை", "color": "#eab308"},
    "waterlogging": {"en": "Water stress (waterlogging)", "ta": "நீர்த் தேக்கம்", "color": "#06b6d4"},
    "pest": {"en": "Pest damage", "ta": "பூச்சித் தாக்குதல்", "color": "#dc2626"},
    "soil": {"en": "Bare soil / bund", "ta": "வெற்று மண் / வரப்பு", "color": "#a16207"},
    "water": {"en": "Open water / channel", "ta": "நீர் / வாய்க்கால்", "color": "#1d4ed8"},
}
CROP_CLASSES = ("healthy", "nitrogen", "waterlogging", "pest")

# --------------------------------------------------------------------------- spectral model
# Reflectance endmembers (green, red, red-edge, NIR), typical textbook shapes (approx.):
# green leaves absorb red and reflect NIR strongly; chlorophyll loss raises green/red/red-edge;
# soil is flat and brighter in red; water absorbs NIR almost completely.
LEAF_HEALTHY = (0.10, 0.040, 0.26, 0.52)
LEAF_CHLOROTIC = (0.16, 0.110, 0.36, 0.49)
SOIL_DRY = (0.11, 0.150, 0.19, 0.24)
SOIL_WET = (0.06, 0.080, 0.10, 0.13)
WATER = (0.07, 0.050, 0.035, 0.025)

CANOPY_COVER = (0.72, 0.78, 0.84, 0.88, 0.91)   # healthy maize cover per flight (illustrative)
HEALTHY_CHLOROSIS = 0.05
VIGOUR_AMPLITUDE = 0.04            # +-4 % low-frequency within-field vigour variation
SOIL_WETNESS = 0.35                # irrigated, moist inter-row soil
BUND_COVER = 0.06                  # sparse weeds on bunds
NITROGEN_CHLOROSIS = (0.50, 0.55, 0.60, 0.63, 0.66)   # N-deficient strip slowly worsens
NITROGEN_COVER_LOSS = 0.06
NITROGEN_STRIP_W = (10, 14)        # width range of the missed fertiliser strip (m)
WATERLOG_WATER_FRAC = 0.90         # standing water fraction of the background at the centre
WATERLOG_COVER_LOSS = 0.45
WATERLOG_CHLOROSIS = 0.15
WATERLOG_RX = (12, 17)
WATERLOG_RY = (7, 10)
PEST_R0_M = (4.0, 7.0)             # radius of the outbreak at flight 1
PEST_SPEED_M_DAY = (0.8, 1.2)      # front speed (illustrative; fall armyworm larvae move plant to plant)
PEST_RAMP_M = 6.0                  # damage builds up over 6 m behind the front
PEST_DEFOLIATION = 0.50
PEST_NIR_LOSS = 0.30
# Ground-truth label thresholds used by the generator
TRUTH_PEST_SEVERITY = 0.20
TRUTH_WATERLOG_MEMBERSHIP = 0.35     # >= ~50 % of the ground under standing water
TRUTH_NITROGEN_MEMBERSHIP = 0.50

# --------------------------------------------------------------------------- indices / zoning
SAVI_L = 0.5                       # soil-adjustment factor (Huete 1988 default)
KMEANS_K = 5                       # clusters over crop cells (soil / water are masked first)
KMEANS_FEATURES = ("ndvi", "ndre", "ndwi", "savi")
KMEANS_MAX_ITER = 60
KMEANS_TOL = 1e-4                  # stop when no centroid moves more than this (z-units)
KMEANS_N_INIT = 3
KMEANS_SAMPLE_STEP = 2             # fit centroids on every 2nd row & column, then label all cells
SMOOTH_PASSES = 3                  # plurality (mode) filter passes over crop clusters
SMOOTH_MIN_VOTES = 5               # a label needs >= 5 of 9 votes in the 3x3 window to take over
MIN_ZONE_CELLS = 12                # smaller connected pieces (< 12 m^2) are merged into a neighbour

# --------------------------------------------------------------------------- stress rules
REFERENCE_PERCENTILE = 75          # reference canopy = top-quartile NDVI crop cells
RULE_WATER_NDWI = 0.0              # NDWI > 0 -> more green than NIR -> open water
RULE_SOIL_NDVI = 0.35              # below this -> bare soil / bund
RULE_WATERLOG_NDWI_DELTA = 0.08    # wetter than the reference canopy by this much ...
RULE_WATERLOG_RED_RATIO = 1.35     # ... while red stays dark (wet background, leaves still green)
RULE_PEST_NIR_RATIO = 0.87         # NIR < 87 % of reference -> canopy / leaf tissue lost ...
RULE_PEST_RED_RATIO = 1.25         # ... and red up 25 %: damaged tissue + exposed soil, not water
RULE_N_NDRE_RATIO = 0.90           # NDRE < 90 % of reference with canopy intact -> chlorophyll / N
RULE_ACTIVE_DECLINE_WEEK = -0.03   # NDVI falling faster than the field by 0.03 / week -> spreading

# --------------------------------------------------------------------------- change detection
CHANGE_DECLINE_THRESHOLD = -0.08   # relative NDVI drop between flights flagged as decline
CHANGE_MIN_HOTSPOT_CELLS = 6
ALERT_FRONT_SPEED_M_DAY = 0.4      # front moving faster than this -> red alert
ALERT_FIELD_SHARE = 0.10           # projection target: days until the pest covers 10 % of crop

# --------------------------------------------------------------------------- prescription
UREA_PRICE_RS_PER_KG = 266.50 / 45.0   # subsidised MRP of Rs 266.50 per 45-kg bag (approx.)
UREA_BASE_KG_HA = 60.0             # corrective top-dressing dose (illustrative; follow TNAU advice)
UREA_DEFICIT_REF = 0.25            # an NDRE deficit of 25 % maps to the base dose
UREA_MIN_FACTOR = 0.6
UREA_MAX_FACTOR = 1.5
PESTICIDE_PRODUCT_L_HA = 0.40      # formulated product at label rate (illustrative)
PESTICIDE_PRICE_RS_PER_L = 1500.0  # illustrative price of the formulated product
SPRAY_VOLUME_L_HA = 20.0           # drone low-volume tank mix (approx. 10-25 L/ha)
PEST_BUFFER_M = 2                  # also treat a 2 m ring round pest zones (front moves ~1 m/day)
WATER_NO_SPRAY_M = 3               # never spray within 3 m of open water

# --------------------------------------------------------------------------- drone
DRONE_TANK_L = 10.0                # common 10-litre class agri-drone (approx.)
DRONE_SWATH_M = 4                  # effective spray swath (approx. 3-5 m)
DRONE_SPRAY_SPEED_MS = 4.0         # ground speed while spraying (approx.)
DRONE_TRANSIT_SPEED_MS = 7.0       # ferry speed, spray off (approx.)
DRONE_TURN_S = 4.0                 # decelerate + yaw + accelerate at a lane end (illustrative)
DRONE_ENDURANCE_S = 540.0          # ~9 min per battery with payload (approx.)
DRONE_RESERVE_FRAC = 0.20          # land with 20 % battery left
DRONE_TAKEOFF_LAND_S = 20.0
DRONE_TURNAROUND_S = 180.0         # battery swap + tank refill on the ground (illustrative)
DRONE_GAP_BRIDGE_CELLS = 3         # fly straight over gaps up to 3 m inside a lane, spray off
HOME_XY = (-6.0, 40.0)             # launch point on the road at the west gate (metres)
