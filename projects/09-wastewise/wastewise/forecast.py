"""Per-bin fill forecasting, from scratch.

Main model: seasonal exponential smoothing (Holt-Winters, multiplicative day-of-week season,
no trend). Smoothing constants are picked per bin by grid search on one-step-ahead error.

Also implemented for comparison/backtesting:
  * naive (tomorrow = today), seasonal naive (= same weekday last week)
  * simple exponential smoothing (SES)
  * ordinary least squares with a day-index trend + 6 weekday dummies (normal equations,
    solved by Gaussian elimination)
"""

import math

ALPHAS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7)
GAMMAS = (0.05, 0.1, 0.2, 0.3, 0.5)
DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ============================================================================ Holt-Winters
class SeasonalES:
    """level_t = a * x_t / s[dow] + (1-a) * level_{t-1};  s[dow] = g * x_t / level_t + (1-g) * s[dow]
    forecast(dow) = level * s[dow]."""

    def __init__(self, alpha=0.2, gamma=0.1):
        self.alpha, self.gamma = alpha, gamma
        self.level = None
        self.season = [1.0] * 7
        self.sigma = 0.0
        self.n = 0
        self._sq = 0.0
        self._ne = 0

    def _init(self, obs):
        head = obs[:14] if len(obs) >= 14 else obs
        lvl = sum(v for _, v in head) / max(1, len(head))
        lvl = max(lvl, 1e-6)
        sums, cnt = [0.0] * 7, [0] * 7
        for dow, v in head:
            sums[dow] += v
            cnt[dow] += 1
        self.season = [(sums[k] / cnt[k] / lvl) if cnt[k] else 1.0 for k in range(7)]
        self.level = lvl

    def fit(self, obs):
        """obs: list of (dow, value). Runs the filter over the whole history."""
        self._init(obs)
        self.n, self._sq, self._ne = 0, 0.0, 0
        for k, (dow, v) in enumerate(obs):
            if k >= 7:  # skip the warm-up week when scoring
                e = v - self.forecast(dow)
                self._sq += e * e
                self._ne += 1
            self.update(dow, v, score=False)
        self.sigma = math.sqrt(self._sq / self._ne) if self._ne else 0.0
        return self

    def update(self, dow, v, score=True):
        if self.level is None:
            self.level, self.season = max(v, 1e-6), [1.0] * 7
        if score:
            e = v - self.forecast(dow)
            self._sq += e * e
            self._ne += 1
            self.sigma = math.sqrt(self._sq / self._ne)
        s = max(self.season[dow], 1e-3)
        new_level = self.alpha * (v / s) + (1 - self.alpha) * self.level
        self.level = max(new_level, 1e-6)
        self.season[dow] = self.gamma * (v / self.level) + (1 - self.gamma) * self.season[dow]
        self.n += 1

    def forecast(self, dow):
        return max(0.0, self.level * self.season[dow])

    def sse(self):
        return self._sq

    def to_json(self):
        return {"model": "seasonal-exponential-smoothing", "alpha": self.alpha,
                "gamma": self.gamma, "level": round(self.level, 4),
                "season": [round(s, 3) for s in self.season], "sigma": round(self.sigma, 4)}


def fit_seasonal_es(obs):
    """Grid-search alpha/gamma minimising one-step-ahead squared error. obs = [(dow, value)]."""
    best = None
    for a in ALPHAS:
        for g in GAMMAS:
            m = SeasonalES(a, g).fit(obs)
            if best is None or m.sse() < best.sse() - 1e-12:
                best = m
    return best


# ============================================================================ simple models
def ses_forecast(values, alpha=0.3):
    if not values:
        return 0.0
    lvl = values[0]
    for v in values[1:]:
        lvl = alpha * v + (1 - alpha) * lvl
    return lvl


def solve_linear(A, b):
    """Gaussian elimination with partial pivoting. A is n x n (copied), b length n."""
    n = len(A)
    M = [list(map(float, A[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            raise ValueError("singular system")
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                if f:
                    for c in range(col, n + 1):
                        M[r][c] -= f * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols(X, y, ridge=1e-6):
    """Least squares beta = (X'X + ridge I)^-1 X'y via the normal equations."""
    p = len(X[0])
    XtX = [[0.0] * p for _ in range(p)]
    Xty = [0.0] * p
    for row, t in zip(X, y):
        for i in range(p):
            Xty[i] += row[i] * t
            ri = row[i]
            for j in range(p):
                XtX[i][j] += ri * row[j]
    for i in range(1, p):
        XtX[i][i] += ridge
    return solve_linear(XtX, Xty)


def weekday_design(t, dow):
    """[1, t, D_Tue..D_Sun] - Monday is the reference weekday."""
    return [1.0, float(t)] + [1.0 if dow == k else 0.0 for k in range(1, 7)]


def ols_weekday_forecast(obs, next_dow):
    X = [weekday_design(t, d) for t, (d, _) in enumerate(obs)]
    y = [v for _, v in obs]
    beta = ols(X, y)
    row = weekday_design(len(obs), next_dow)
    return max(0.0, sum(b * x for b, x in zip(beta, row))), beta


# ============================================================================ backtest
def backtest(obs, holdout=14):
    """Rolling one-step-ahead MAE on the last `holdout` points for every model."""
    if len(obs) < holdout + 14:
        holdout = max(1, len(obs) - 14)
    train = obs[:-holdout]
    hw = fit_seasonal_es(train)
    errs = {"naive": [], "seasonal_naive": [], "ses": [], "ols_weekday": [], "seasonal_es": []}
    for k in range(len(obs) - holdout, len(obs)):
        dow, actual = obs[k]
        past = obs[:k]
        vals = [v for _, v in past]
        errs["naive"].append(abs(actual - vals[-1]))
        errs["seasonal_naive"].append(abs(actual - vals[-7]))
        errs["ses"].append(abs(actual - ses_forecast(vals)))
        errs["ols_weekday"].append(abs(actual - ols_weekday_forecast(past, dow)[0]))
        errs["seasonal_es"].append(abs(actual - hw.forecast(dow)))
        hw.update(dow, actual)
    return {m: sum(e) / len(e) for m, e in errs.items()}


# ============================================================================ time to full
def hours_to_full(level, daily_forecasts, start_h=0.0, deposit=(5.0, 23.0), max_days=14):
    """Hours from `start_h` on day 0 until the bin reaches 100%.

    level           : current fill fraction at start_h
    daily_forecasts : predicted increments for day 0, 1, 2, ... (fraction of capacity)
    Waste arrives uniformly between deposit[0] and deposit[1] each day. Returns None if the bin
    will not be full within the horizon.
    """
    if level >= 1.0:
        return 0.0
    d0, d1 = deposit
    span = d1 - d0
    lvl = level
    for k in range(min(max_days, len(daily_forecasts))):
        inc = daily_forecasts[k]
        lo = d0 if k > 0 else min(max(start_h, d0), d1)
        rate = inc / span  # per hour
        remaining = (d1 - lo) * rate
        if rate > 0 and lvl + remaining >= 1.0:
            t = lo + (1.0 - lvl) / rate
            return round(24.0 * k + t - start_h, 2)
        lvl += remaining
    return None
