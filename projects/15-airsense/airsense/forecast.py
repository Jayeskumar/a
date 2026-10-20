"""Next-24-hour PM forecast per sensor: seasonal profile + AR terms + weather features.

Work on y = ln(PM + 5). For every sensor:
    s(hod)      robust daily profile (median of y per hour of day)
    a_t         = y_t - s(hod_t)                       (anomaly)
    a_(t+1)     = c + p1 a_t + p2 a_(t-1) + p24 a_(t-23)
                  + b1 ln(wind speed) + b2 rain + b3 recent rain + b4 RH
                  + b5 cos(wind dir) + b6 sin(wind dir) + b7 Sunday
fitted by ridge least squares, then iterated 24 steps ahead using the weather forecast.
Prediction intervals come from back-test error quantiles per horizon.
"""

import math

from . import config as C
from .mathx import least_squares, median, percentile, predict

FEATURES = ["a(t)", "a(t-1)", "a(t-23)", "ln wind", "rain", "rain 12h", "RH", "cos wind",
            "sin wind", "Sunday"]
OFFSET = 5.0
CLIP = 2.5


def to_log(v):
    return None if v is None else math.log(max(v, 0.0) + OFFSET)


def from_log(y):
    return max(0.0, math.exp(y) - OFFSET)


def weather_feats(w, k):
    """Weather features for hour index k. w: dict of lists (ws, rain, rh, wdir, sunday)."""
    r12 = sum(w["rain"][max(0, k - 12):k + 1])
    ang = math.radians(w["wdir"][k])
    return [math.log(w["ws"][k] + 0.5), min(w["rain"][k], 10.0), min(r12, 40.0),
            (w["rh"][k] - 70.0) / 10.0, math.cos(ang), math.sin(ang), 1.0 if w["sunday"][k] else 0.0]


class SensorForecaster:
    def __init__(self, values, hods, weather, train_end):
        """values: hourly PM (None = missing/flagged); weather: dict of lists covering at
        least len(values) + 24 hours; train_end: exclusive index of the training window."""
        self.hods = hods
        self.w = weather
        y = [to_log(v) for v in values]
        prof = []
        for h in range(24):
            prof.append(median([y[t] for t in range(train_end) if hods[t] == h and y[t] is not None]))
        fill = median([p for p in prof if p is not None]) or to_log(30.0)
        self.profile = [p if p is not None else fill for p in prof]
        self.y = y
        rows, tgt = [], []
        for t in range(24, train_end - 1):
            a = self._anom(t + 1)
            f = self._lags(t)
            if a is None or f is None:
                continue
            rows.append(f + weather_feats(weather, t + 1))
            tgt.append(max(-CLIP, min(CLIP, a)))
        if len(rows) < 48:
            self.model = None
        else:
            self.model = least_squares(rows, tgt, ridge=0.01)
        self.n_train = len(rows)

    def _anom(self, t, y=None):
        y = self.y if y is None else y
        v = y[t] if 0 <= t < len(y) else None
        return None if v is None else v - self.profile[self.hods[t]]

    def _lags(self, t, y=None):
        a0, a1, a23 = self._anom(t, y), self._anom(t - 1, y), self._anom(t - 23, y)
        if a0 is None:
            return None
        a1 = a0 if a1 is None else a1
        a23 = 0.0 if a23 is None else a23
        return [max(-CLIP, min(CLIP, a)) for a in (a0, a1, a23)]

    def forecast(self, origin, horizon=24, weather=None):
        """Forecast PM for origin+1 .. origin+horizon using data up to `origin`."""
        w = weather or self.w
        y = list(self.y[:origin + 1]) + [None] * horizon
        # fall back to the latest value within 3 h if the origin hour is missing
        if y[origin] is None:
            for back in range(1, 4):
                if origin - back >= 0 and y[origin - back] is not None:
                    y[origin] = self.profile[self.hods[origin]] + (
                        y[origin - back] - self.profile[self.hods[origin - back]])
                    break
        out = []
        for k in range(1, horizon + 1):
            t = origin + k
            lags = self._lags(t - 1, y)
            if self.model is None or lags is None:
                a = 0.0
            else:
                a = predict(self.model, lags + weather_feats(w, t))
            a = max(-CLIP, min(CLIP, a))
            y[t] = self.profile[self.hods[t]] + a
            out.append(from_log(y[t]))
        return out

    def contributions(self, origin):
        """Explain the 1-hour-ahead forecast: each feature's push on the log anomaly."""
        if self.model is None:
            return []
        lags = self._lags(origin)
        if lags is None:
            return []
        f = lags + weather_feats(self.w, origin + 1)
        return [{"feature": n, "coef": round(c, 3), "x": round(x, 2), "effect": round(c * x, 3)}
                for n, c, x in zip(FEATURES, self.model["coef"], f)]


def backtest(values, hods, weather, train_end, step=C.FORECAST_ORIGIN_STEP_H, horizon=24,
             weather_noisy=None):
    """Rolling-origin evaluation on the hold-out window. Returns per-horizon errors."""
    fc = SensorForecaster(values, hods, weather, train_end)
    res = {"model": [[] for _ in range(horizon)], "persistence": [[] for _ in range(horizon)],
           "seasonal": [[] for _ in range(horizon)], "log_err": [[] for _ in range(horizon)]}
    n = len(values)
    origin = train_end - 1
    while origin + horizon < n:
        cur = values[origin]
        if cur is None:
            origin += step
            continue
        wx = weather_noisy(origin) if weather_noisy else weather
        pred = fc.forecast(origin, horizon, wx)
        for k in range(1, horizon + 1):
            actual = values[origin + k]
            if actual is None:
                continue
            res["model"][k - 1].append(abs(pred[k - 1] - actual))
            res["persistence"][k - 1].append(abs(cur - actual))
            sn = values[origin + k - 24]
            if sn is not None:
                res["seasonal"][k - 1].append(abs(sn - actual))
            res["log_err"][k - 1].append(to_log(actual) - to_log(pred[k - 1]))
        origin += step
    return res


def interval_quantiles(log_errs, lo=10, hi=90):
    return [(percentile(e, lo) or 0.0, percentile(e, hi) or 0.0) for e in log_errs]
