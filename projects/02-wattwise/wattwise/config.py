"""All tunable assumptions live here, each with its source or reasoning.

Figures marked "approx." are rough planning numbers, not precise statistics.
Change them in one place and every module (carbon, solar, what-if) follows.
"""

# ---------------------------------------------------------------- carbon / cost
# India grid emission factor, kg CO2 per kWh consumed.
# approx. - the Central Electricity Authority (CEA) CO2 Baseline Database puts
# the all-India grid average at roughly 0.7 kg CO2/kWh.
GRID_EMISSION_FACTOR_KG_PER_KWH = 0.71

# Average electricity tariff for an educational institution, Rs per kWh.
# approx. - planning assumption for a Tamil Nadu HT/LT institutional tariff
# including fixed charges spread per unit; edit for your own bill.
TARIFF_INR_PER_KWH = 8.0

# CO2 absorbed by one mature tree in a year, kg.
# approx. - the commonly quoted figure of about 21 kg CO2 per tree per year.
TREE_KG_CO2_PER_YEAR = 21.0

# ---------------------------------------------------------------- rooftop solar
# Specific yield of a fixed-tilt rooftop PV plant in Tamil Nadu, kWh/kWp/year.
# approx. - typical planning range is 1,400-1,500 kWh/kWp/yr for TN.
SOLAR_YIELD_KWH_PER_KWP_YEAR = 1450.0

# Shadow-free roof area needed per kWp, m2.
# approx. - common Indian rule of thumb is ~10 m2 per kWp.
SOLAR_AREA_M2_PER_KWP = 10.0

# Installed cost of a grid-tied rooftop system, Rs per kWp (before subsidy).
# approx. - planning assumption; real quotes vary with size and vendor.
SOLAR_COST_INR_PER_KWP = 50000.0

# Fraction of the roof that is usable (parapets, water tanks, walkways).
SOLAR_USABLE_ROOF_FRACTION = 0.75

# Module output degradation per year.
# approx. - crystalline-silicon warranties typically assume ~0.5%/yr.
SOLAR_DEGRADATION_PER_YEAR = 0.005

# Annual operation & maintenance cost as a fraction of capex (assumption).
SOLAR_OM_FRACTION_PER_YEAR = 0.01

# Plant life used for lifetime savings, years.
SOLAR_LIFETIME_YEARS = 25

# Size cap: do not size beyond this fraction of annual consumption
# (net-metering rules usually cap export; assumption).
SOLAR_MAX_FRACTION_OF_CONSUMPTION = 1.0

# ---------------------------------------------------------------- what-if levers
# AC energy saved per +1 degC of setpoint.
# approx. - Bureau of Energy Efficiency (BEE) guidance is about 6% per degC.
AC_SAVING_PER_DEGC = 0.06
AC_MAX_SETPOINT_DELTA = 4

# LED vs fluorescent tube / CFL energy saving (approx. ~50%).
LED_SAVING_FRACTION = 0.5

# BLDC vs conventional induction ceiling fan saving (approx. ~50%).
BLDC_SAVING_FRACTION = 0.5

# Share of after-hours excess load that an auto-off timer/relay actually removes
# (assumption: some loads are manually overridden).
AUTO_OFF_EFFECTIVENESS = 0.85

# Night hours used to learn each building's essential base load.
NIGHT_HOURS = (0, 1, 2, 3, 4)
# Percentile of night load treated as "essential" (servers, fridges, security).
ESSENTIAL_BASE_PERCENTILE = 0.20
# Auto-off window ends at this hour (06:00).
AUTO_OFF_END_HOUR = 6

# ---------------------------------------------------------------- analytics
# Cooling-degree base temperature, degC (AC rarely needed below this).
COOLING_BASE_C = 24.0

# Anomaly detector thresholds.
ANOMALY_Z_THRESHOLD = 3.5        # Iglewicz & Hoaglin modified z-score cut-off
ANOMALY_MIN_EXCESS_KW = 2.0      # ignore tiny absolute deviations
ANOMALY_MIN_EXCESS_FRAC = 0.30   # and deviations < 30% of the baseline
ANOMALY_MIN_HOURS = 2            # an event must last at least 2 hours
ANOMALY_MAX_GAP_HOURS = 1        # merge flagged hours separated by <= 1 hour

# Forecaster.
RIDGE_LAMBDA = 0.01              # tiny L2 penalty keeps sparse categories solvable
RECENCY_HALF_LIFE_DAYS = 21.0    # recent weeks weigh more (behaviour drifts)
ROBUST_REFIT_Z = 3.5             # trim training points with robust |z| above this

# ---------------------------------------------------------------- leaderboard
# Weeks 1-6 are the "baseline period", weeks 7-8 the "challenge period".
BASELINE_WEEKS = 6
CHAMPION_MIN_SAVING_PCT = 0.0
