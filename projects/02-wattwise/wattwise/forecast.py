"""Load forecasting from scratch.

Primary model - weighted, robust multiple linear regression:

    kWh(t) = sum_k beta_k  * 1[daytype(t), hour(t) = k]           (72 one-hot)
           + sum_k gamma_k * CDD(t) * 1[daytype(t), hour(t) = k]   (72 terms)
    CDD(t) = max(0, T(t) - 24 degC)   (cooling degrees)

beta is the calendar baseline ("a Tuesday 2 PM normally draws X kWh") and
gamma is the hour-specific weather sensitivity ("+Y kWh per extra degC").

Fitted with ridge-regularised weighted least squares (normal equations solved
by Gaussian elimination). Weights decay with a 21-day half-life so recent
behaviour counts more. Training is robust: it starts from per-category
medians and twice drops hours whose relative residual has a modified z-score
above 3.5, so waste events do not bend the baseline.

Comparators: additive Holt-Winters (season = 168 h) and seasonal-naive.
"""

from . import config
from .dataset import DAYTYPES, cooling_degrees, daytype_of
from .stats import mad, median, mape, solve, wape

N_CAT = len(DAYTYPES) * 24
N_FEAT = 2 * N_CAT
_DT_INDEX = {d: i for i, d in enumerate(DAYTYPES)}


def features(ts, temp_c):
    """Sparse feature row: list of (index, value)."""
    dt = daytype_of(ts.date())
    h = ts.hour
    k = _DT_INDEX[dt] * 24 + h
    row = [(k, 1.0)]
    cdd = cooling_degrees(temp_c)
    if cdd > 0:
        row.append((N_CAT + k, cdd))
    return row


class LinearForecaster(object):
    def __init__(self, ridge=config.RIDGE_LAMBDA,
                 half_life_days=config.RECENCY_HALF_LIFE_DAYS,
                 robust_z=config.ROBUST_REFIT_Z):
        self.ridge = ridge
        self.half_life_days = half_life_days
        self.robust_z = robust_z
        self.coef = None
        self.trimmed = 0

    def _fit_once(self, rows, y, w):
        xtx = [[0.0] * N_FEAT for _ in range(N_FEAT)]
        xty = [0.0] * N_FEAT
        for row, yi, wi in zip(rows, y, w):
            if wi == 0.0:
                continue
            for i, vi in row:
                xty[i] += wi * vi * yi
                for j, vj in row:
                    xtx[i][j] += wi * vi * vj
        for i in range(N_FEAT):
            xtx[i][i] += self.ridge
        return solve(xtx, xty)

    def fit(self, timestamps, temps, y):
        rows = [features(t, x) for t, x in zip(timestamps, temps)]
        last = timestamps[-1]
        if self.half_life_days:
            w = [0.5 ** (((last - t).total_seconds() / 86400.0) / self.half_life_days)
                 for t in timestamps]
        else:
            w = [1.0] * len(y)
        self.trimmed = 0
        if not self.robust_z:
            self.coef = self._fit_once(rows, y, w)
            return self
        # Pass 0: a robust starting point - the median of each day-type x hour
        # category - so a waste event cannot drag the first fit towards itself.
        groups = {}
        for r, yi in zip(rows, y):
            groups.setdefault(r[0][0], []).append(yi)
        cat_med = {k: median(v) for k, v in groups.items()}
        pred0 = [cat_med[r[0][0]] for r in rows]
        keep = self._inliers(y, pred0)
        # Passes 1-2: fit on inliers, re-score every hour against the fit, refit.
        for _ in range(2):
            self.coef = self._fit_once(rows, y, [wi if k else 0.0 for wi, k in zip(w, keep)])
            keep = self._inliers(y, [self._dot(r) for r in rows])
        self.coef = self._fit_once(rows, y, [wi if k else 0.0 for wi, k in zip(w, keep)])
        self.trimmed = sum(1 for k in keep if not k)
        return self

    def _inliers(self, y, pred):
        """Modified z-score on relative residuals. The noise is multiplicative,
        so a 3 kWh miss matters at 3 AM (base load) but not at a 60 kWh peak."""
        res = [(yi - p) / max(abs(p), 1.0) for yi, p in zip(y, pred)]
        med = median(res)
        # floor: a deviation under ~2% is never an outlier, even on very clean data
        scale = max(1.4826 * mad(res, med), 0.02)
        return [abs(r - med) / scale <= self.robust_z for r in res]

    def _dot(self, row):
        return sum(self.coef[i] * v for i, v in row)

    def predict(self, timestamps, temps):
        return [max(0.0, self._dot(features(t, x))) for t, x in zip(timestamps, temps)]

    def explain(self, ts, temp_c):
        """Why this forecast? Split into calendar baseline + weather effect."""
        row = features(ts, temp_c)
        base = self.coef[row[0][0]]
        weather = sum(self.coef[i] * v for i, v in row[1:])
        return {
            "daytype": daytype_of(ts.date()), "hour": ts.hour,
            "calendar_baseline_kwh": round(base, 2),
            "temperature_c": round(temp_c, 1),
            "cooling_degrees": round(cooling_degrees(temp_c), 2),
            "weather_effect_kwh": round(weather, 2),
            "forecast_kwh": round(max(0.0, base + weather), 2),
        }

    def weather_sensitivity(self):
        """kWh per extra degC of cooling, by period."""
        def avg(dts, hours):
            ks = [N_CAT + _DT_INDEX[d] * 24 + h for d in dts for h in hours]
            return round(sum(self.coef[k] for k in ks) / len(ks), 3)
        day, night = range(8, 19), [h for h in range(24) if not 8 <= h < 19]
        return {"workday_daytime": avg(["workday"], day),
                "weekend_daytime": avg(["saturday", "sunday"], day),
                "night": avg(DAYTYPES, night)}


# ------------------------------------------------------------------ Holt-Winters
class HoltWinters(object):
    """Additive triple exponential smoothing with a fixed season length."""

    def __init__(self, season=168, alpha=0.2, beta=0.0, gamma=0.3):
        self.season, self.alpha, self.beta, self.gamma = season, alpha, beta, gamma

    def fit(self, y):
        m = self.season
        if len(y) < 2 * m:
            raise ValueError("need at least two seasons of data")
        s1 = sum(y[:m]) / m
        s2 = sum(y[m:2 * m]) / m
        level, trend = s1, (s2 - s1) / m
        seas = [y[i] - s1 for i in range(m)]
        sse = 0.0
        for t in range(m, len(y)):
            pred = level + trend + seas[t % m]
            sse += (y[t] - pred) ** 2
            prev = level
            level = self.alpha * (y[t] - seas[t % m]) + (1 - self.alpha) * (level + trend)
            trend = self.beta * (level - prev) + (1 - self.beta) * trend
            seas[t % m] = self.gamma * (y[t] - level) + (1 - self.gamma) * seas[t % m]
        self.level, self.trend, self.seas, self.n, self.sse = level, trend, seas, len(y), sse
        return self

    def forecast(self, h):
        m = self.season
        return [max(0.0, self.level + (k + 1) * self.trend + self.seas[(self.n + k) % m])
                for k in range(h)]


def fit_holt_winters(y, season=168):
    """Small grid search on in-sample one-step SSE."""
    best = None
    for a in (0.05, 0.1, 0.2, 0.4):
        for g in (0.1, 0.3, 0.5):
            for b in (0.0, 0.001):
                hw = HoltWinters(season, a, b, g).fit(y)
                if best is None or hw.sse < best.sse:
                    best = hw
    return best


def seasonal_naive(y, h, season=168):
    return [y[len(y) - season + (k % season)] for k in range(h)]


# ------------------------------------------------------------------ evaluation
HOLDOUT_HOURS = 168


def backtest(ds, bid):
    """Train on weeks 1-7, forecast the hold-out week 8, compare models."""
    y = ds.loads[bid]
    n = len(y) - HOLDOUT_HOURS
    ts_tr, ts_te = ds.timestamps[:n], ds.timestamps[n:]
    tp_tr, tp_te = ds.temps[:n], ds.temps[n:]
    actual = y[n:]
    waste = set()
    for e in ds.events:
        if e["building"] == bid:
            waste.update(range(e["start_index"] - n, e["end_index"] - n + 1))
    clean = [i for i in range(HOLDOUT_HOURS) if i not in waste]
    mlr = LinearForecaster().fit(ts_tr, tp_tr, y[:n])
    p_mlr = mlr.predict(ts_te, tp_te)
    p_hw = fit_holt_winters(y[:n]).forecast(HOLDOUT_HOURS)
    p_sn = seasonal_naive(y[:n], HOLDOUT_HOURS)
    return {
        "building": bid,
        "timestamps": [t.isoformat() for t in ts_te],
        "actual": actual,
        "predicted": [round(v, 2) for v in p_mlr],
        "mape": {"regression": round(mape(actual, p_mlr), 2),
                 "holt_winters": round(mape(actual, p_hw), 2),
                 "seasonal_naive": round(mape(actual, p_sn), 2)},
        "mape_excluding_waste_hours": round(mape([actual[i] for i in clean],
                                                 [p_mlr[i] for i in clean]), 2),
        "wape": {"regression": round(wape(actual, p_mlr), 2),
                 "holt_winters": round(wape(actual, p_hw), 2),
                 "seasonal_naive": round(wape(actual, p_sn), 2)},
        "trimmed_training_hours": mlr.trimmed,
    }


def forecast_next_week(ds, bid):
    """Fit on all 8 weeks; forecast the next 168 hours using forecast temps."""
    mlr = LinearForecaster().fit(ds.timestamps, ds.temps, ds.loads[bid])
    pred = mlr.predict(ds.forecast_timestamps, ds.forecast_temps)
    peak_i = max(range(len(pred)), key=lambda i: pred[i])
    return {
        "building": bid,
        "timestamps": [t.isoformat() for t in ds.forecast_timestamps],
        "temps": ds.forecast_temps,
        "predicted": [round(v, 2) for v in pred],
        "total_kwh": round(sum(pred), 1),
        "peak": {"timestamp": ds.forecast_timestamps[peak_i].isoformat(),
                 "kwh": round(pred[peak_i], 2),
                 "why": mlr.explain(ds.forecast_timestamps[peak_i], ds.forecast_temps[peak_i])},
        "weather_sensitivity_kwh_per_degc": mlr.weather_sensitivity(),
        "trimmed_training_hours": mlr.trimmed,
        "model": "Robust recency-weighted multiple linear regression "
                 "(72 day-type x hour dummies + 72 day-type x hour cooling-degree terms)",
    }


def model_coefficients(model):
    """Calendar profile (kWh) by daytype x hour, for the 'why' panel."""
    return {dt: [round(model.coef[i * 24 + h], 2) for h in range(24)]
            for i, dt in enumerate(DAYTYPES)}
