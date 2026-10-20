"""Forecasting models, implemented from scratch.

Every model answers the same question: given the first `n` days of a SKU's (cleaned) sales,
forecast days n .. n+h-1. That makes rolling-origin backtesting trivial and leak-free.

Pipeline for the three time-series models (seasonal naive, moving average, Holt-Winters):
  1. stock-out days were already imputed (dataset.clean_series)
  2. festival effects are estimated from training data and divided out ("calendar adjustment")
  3. the model is fitted on the adjusted series
  4. learned festival uplifts are multiplied back onto upcoming festival days
The regression model instead learns festival effects directly as features.
"""
import math
from operator import mul

from . import config, festivals
from .stats import solve

GROUPS = config.FESTIVAL_GROUPS
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SkuContext:
    """Everything the models need for one SKU, shared across folds."""

    def __init__(self, y, flags, promo, dates, horizon=None):
        self.y = list(y)               # cleaned daily sales (stock-outs imputed)
        self.flags = list(flags)       # True = censored stock-out day
        self.promo = list(promo)
        self.dates = list(dates)
        self.n_all = len(self.y)
        h = horizon or config.FORECAST_HORIZON
        from datetime import timedelta
        ext = self.dates + [self.dates[-1] + timedelta(days=i + 1) for i in range(h + 7)]
        self.ext_dates = ext
        self.fest = festivals.feature_rows(ext)          # [diwali, pongal, other] per day
        self.dow = [d.weekday() for d in ext]
        self.has_fest = [any(r) for r in self.fest]
        self._reg_cols = None

    # ---------------------------------------------------------------- festival layer
    def dow_index(self, n):
        sums, cnts = [0.0] * 7, [0] * 7
        for t in range(n):
            if not self.flags[t] and not self.has_fest[t] and not self.promo[t]:
                sums[self.dow[t]] += self.y[t]
                cnts[self.dow[t]] += 1
        means = [sums[i] / cnts[i] if cnts[i] else 0.0 for i in range(7)]
        overall = sum(means) / 7.0
        if overall <= 0:
            return [1.0] * 7
        return [m / overall if m > 0 else 1.0 for m in means]

    def festival_uplift(self, n):
        """Peak uplift per festival group learned from days < n (0 if never seen)."""
        return {g: v["uplift"] for g, v in self.festival_uplift_detail(n).items()}

    def festival_uplift_detail(self, n):
        """Least-squares peak uplift per group, then shrunk toward 0 by its noise.

        For festival-window day t:  r_t = y_t / (local level x weekday index) - 1 ~ u * shape_t
        u_raw = sum(shape * r) / sum(shape^2);  se = sigma_r / sqrt(sum(shape^2)), where sigma_r is
        the same ratio's spread on ordinary days. Positive-part James-Stein style shrinkage:
        u = u_raw * max(0, 1 - (se / u_raw)^2)  -> one noisy festival week cannot fake an uplift.
        """
        idx = self.dow_index(n)
        z = [self.y[t] / idx[self.dow[t]] for t in range(n)]
        ok = [not (self.flags[t] or self.has_fest[t] or self.promo[t]) for t in range(n)]
        cs, cc = [0.0], [0]
        for t in range(n):
            cs.append(cs[-1] + (z[t] if ok[t] else 0.0))
            cc.append(cc[-1] + (1 if ok[t] else 0))

        def level(t):   # mean of ordinary days in [t-34, t-7]
            a, b = max(0, t - 34), max(0, t - 6)
            c = cc[b] - cc[a]
            return (cs[b] - cs[a]) / c if c >= 7 else None

        num = {g: 0.0 for g in GROUPS}
        den = {g: 0.0 for g in GROUPS}
        noise = []
        for t in range(n):
            if self.flags[t] or self.promo[t]:
                continue   # promotions would be mistaken for festival uplift
            lv = level(t)
            if not lv or lv <= 0:
                continue
            r = z[t] / lv - 1.0
            if not self.has_fest[t]:
                noise.append(r)
                continue
            active = [i for i, v in enumerate(self.fest[t]) if v > 0]
            if len(active) != 1:
                continue
            sh = self.fest[t][active[0]]
            num[GROUPS[active[0]]] += sh * r
            den[GROUPS[active[0]]] += sh * sh
        if len(noise) > 1:
            mu = sum(noise) / len(noise)
            sigma_r = math.sqrt(sum((v - mu) ** 2 for v in noise) / (len(noise) - 1))
        else:
            sigma_r = 0.0
        out = {}
        for g in GROUPS:
            if den[g] < 1.0:
                out[g] = {"uplift": 0.0, "raw": 0.0, "se": None}
                continue
            raw = max(-0.5, min(12.0, num[g] / den[g]))
            se = sigma_r / math.sqrt(den[g])
            shrink = max(0.0, 1.0 - (se / raw) ** 2) if raw else 0.0
            out[g] = {"uplift": raw * shrink, "raw": raw, "se": se}
        return out

    def fest_factor(self, t, u):
        f = self.fest[t]
        return max(0.2, 1.0 + u["diwali"] * f[0] + u["pongal"] * f[1] + u["other"] * f[2])

    def adjusted(self, n, u):
        return [self.y[t] / self.fest_factor(t, u) for t in range(n)]

    def reapply(self, base, n, u):
        return [max(0.0, v * self.fest_factor(n + i, u)) for i, v in enumerate(base)]

    # ---------------------------------------------------------------- regression design
    def reg_columns(self):
        if self._reg_cols is None:
            T = len(self.ext_dates)
            cols = [[1.0] * T, [t / 365.0 for t in range(T)]]
            for d in range(1, 7):
                cols.append([1.0 if self.dow[t] == d else 0.0 for t in range(T)])
            for g in range(3):
                cols.append([self.fest[t][g] for t in range(T)])
            cols.append([float(self.promo[t]) if t < self.n_all else 0.0 for t in range(T)])
            w = [0.0 if (t < self.n_all and self.flags[t]) else 1.0 for t in range(T)]
            wcols = [[a * b for a, b in zip(c, w)] for c in cols]
            self._reg_cols = (cols, wcols)
        return self._reg_cols


REG_FEATURES = ["Base level", "Trend per year"] + ["%s vs Mon" % d for d in DOW_NAMES[1:]] + \
               ["Diwali peak", "Pongal peak", "Other festival peak", "Promotion"]


# -------------------------------------------------------------------- models
def seasonal_naive(series, h, m=7):
    """Same weekday last week: y[n+i] = y[n - m + (i mod m)]."""
    n = len(series)
    return [series[n - m + (i % m)] for i in range(h)]


def moving_average(series, h, window=None):
    w = series[-(window or config.MA_WINDOW):]
    avg = sum(w) / len(w)
    return [avg] * h


def hw_init(y, m=7):
    """Initial level, trend and seasonal indices from the first (up to 4) seasons."""
    k = max(1, min(len(y) // m, 4))
    means = [sum(y[i * m:(i + 1) * m]) / m for i in range(k)]
    level = means[0]
    trend = (means[-1] - means[0]) / (m * (k - 1)) if k > 1 else 0.0
    seas = [sum(y[w * m + i] - means[w] for w in range(k)) / k for i in range(m)]
    return level, trend, seas


def hw_fit(y, alpha, beta, gamma, phi=None, m=7, burn=14):
    """Additive Holt-Winters with (optionally damped) trend.

        l_t = a (y_t - s_{t-m}) + (1-a)(l_{t-1} + phi b_{t-1})
        b_t = b (l_t - l_{t-1}) + (1-b) phi b_{t-1}
        s_t = g (y_t - l_t) + (1-g) s_{t-m}
    Returns (level, trend, seasonals indexed by t mod m, one-step SSE after burn-in).
    """
    phi = config.HW_PHI if phi is None else phi
    level, trend, seas = hw_init(y, m)
    seas = list(seas)
    sse = 0.0
    a1, b1, g1 = 1.0 - alpha, 1.0 - beta, 1.0 - gamma
    for t, yt in enumerate(y):
        j = t % m
        s = seas[j]
        damped = phi * trend
        e = yt - (level + damped + s)
        if t >= burn:
            sse += e * e
        new_level = alpha * (yt - s) + a1 * (level + damped)
        trend = beta * (new_level - level) + b1 * damped
        seas[j] = gamma * (yt - new_level) + g1 * s
        level = new_level
    return level, trend, seas, sse


def hw_forecast(state, n, h, phi=None, m=7):
    phi = config.HW_PHI if phi is None else phi
    level, trend, seas = state[0], state[1], state[2]
    out, cum, p = [], 0.0, 1.0
    for i in range(1, h + 1):
        p *= phi
        cum += p
        out.append(level + cum * trend + seas[(n + i - 1) % m])
    return out


def hw_grid_search(y, m=7):
    best = None
    for a in config.HW_ALPHAS:
        for b in config.HW_BETAS:
            for g in config.HW_GAMMAS:
                sse = hw_fit(y, a, b, g, m=m)[3]
                if best is None or sse < best[0]:
                    best = (sse, (a, b, g))
    return best[1]


def linreg_fit(ctx, n, lam=None):
    """Ridge-stabilised least squares on days < n (stock-out days get weight 0)."""
    lam = config.RIDGE_LAMBDA if lam is None else lam
    cols, wcols = ctx.reg_columns()
    k = len(cols)
    y = ctx.y[:n]
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for i in range(k):
        wi = wcols[i][:n]
        xty[i] = sum(map(mul, wi, y))
        for j in range(i, k):
            v = sum(map(mul, wi, cols[j][:n]))
            xtx[i][j] = v
            xtx[j][i] = v
    for i in range(1, k):
        xtx[i][i] += lam
    return solve(xtx, xty)


def linreg_predict(ctx, beta, n, h):
    cols, _ = ctx.reg_columns()
    return [max(0.0, sum(beta[j] * cols[j][t] for j in range(len(beta)))) for t in range(n, n + h)]


# -------------------------------------------------------------------- unified API
def forecast(ctx, model, n, h, params=None, uplift=None):
    """Forecast days n..n+h-1 from the first n days. Returns (forecast, params_used, uplift)."""
    if model == "linreg":
        beta = linreg_fit(ctx, n)
        return linreg_predict(ctx, beta, n, h), {"coef": beta}, None
    u = uplift if uplift is not None else ctx.festival_uplift(n)
    adj = ctx.adjusted(n, u)
    if model == "snaive":
        base = seasonal_naive(adj, h)
        p = {}
    elif model == "ma":
        base = moving_average(adj, h)
        p = {"window": config.MA_WINDOW}
    elif model == "hw":
        abg = params.get("abg") if params else None
        if abg is None:
            abg = hw_grid_search(adj)
        state = hw_fit(adj, *abg)
        base = hw_forecast(state, n, h)
        p = {"abg": abg}
    else:
        raise ValueError("unknown model %r" % model)
    return ctx.reapply(base, n, u), p, u


def explain_regression(beta):
    return [{"feature": f, "coef": round(b, 3)} for f, b in zip(REG_FEATURES, beta)]


def rmse(errors):
    return math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else 0.0
