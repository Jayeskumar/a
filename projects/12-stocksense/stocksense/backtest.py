"""Rolling-origin backtesting and automatic model selection per SKU."""
import math

from . import config
from .forecast import forecast, rmse


def rolling_origin_splits(n, folds=None, horizon=None, step=None, min_train=None):
    """[(train_end, test_end), ...] oldest first; the last test window ends at n.

    Fold k trains on days [0, train_end) and tests on [train_end, train_end + horizon).
    """
    folds = folds or config.BACKTEST_FOLDS
    horizon = horizon or config.BACKTEST_HORIZON
    step = step or config.BACKTEST_STEP
    min_train = config.MIN_TRAIN_DAYS if min_train is None else min_train
    out = []
    for k in range(folds):
        test_end = n - (folds - 1 - k) * step
        train_end = test_end - horizon
        if train_end >= min_train and test_end <= n:
            out.append((train_end, test_end))
    return out


def metrics(actual, pred):
    """MAPE / sMAPE in %, plus MAE, RMSE and bias, on paired lists."""
    ape = [abs(a - p) / a for a, p in zip(actual, pred) if a > 0]
    sape = [2 * abs(a - p) / (abs(a) + abs(p)) for a, p in zip(actual, pred) if abs(a) + abs(p) > 0]
    err = [p - a for a, p in zip(actual, pred)]
    n = len(err) or 1
    return {
        "mape": round(100 * sum(ape) / len(ape), 2) if ape else None,
        "smape": round(100 * sum(sape) / len(sape), 2) if sape else 0.0,
        "mae": round(sum(abs(e) for e in err) / n, 3),
        "rmse": round(rmse(err), 3),
        "bias": round(sum(err) / n, 3),
        "n": len(err),
    }


def _score(m, metric):
    v = m.get(metric)
    return v if v is not None else m["smape"]


def choose(model_metrics, metric=None):
    metric = metric or config.SELECT_METRIC
    best = None
    for name in config.MODEL_ORDER:
        if name not in model_metrics:
            continue
        s = _score(model_metrics[name], metric)
        if best is None or s < best[1] - 1e-9:
            best = (name, s)
    return best[0]


def backtest_sku(ctx, end, metric=None):
    """Backtest all models on data[:end]. Returns a dict with per-model metrics, the choice,
    the forecast-error sigma of the chosen model and an honest hold-out comparison."""
    splits = rolling_origin_splits(end)
    if not splits:
        raise ValueError("not enough history to backtest")
    hw_params = None
    pairs = {m: [] for m in config.MODEL_ORDER}     # (actual, pred, fold) on uncensored days
    for fold, (tr, te) in enumerate(splits):
        h = te - tr
        u = ctx.festival_uplift(tr)
        for m in config.MODEL_ORDER:
            params = {"abg": hw_params} if (m == "hw" and hw_params) else None
            pred, used, _ = forecast(ctx, m, tr, h, params=params, uplift=u)
            if m == "hw":
                hw_params = used["abg"]      # tuned once on the oldest training window only
            for i in range(h):
                t = tr + i
                if not ctx.flags[t]:
                    pairs[m].append((ctx.y[t], pred[i], fold))
    per_model = {}
    for m, rows in pairs.items():
        per_model[m] = metrics([a for a, _, _ in rows], [p for _, p, _ in rows])
    chosen = choose(per_model, metric)
    errs = [p - a for a, p, _ in pairs[chosen]]
    sigma = rmse(errs)

    # Honest hold-out: pick the model on folds 1..k-1 only, then score it on the unseen last fold.
    last = len(splits) - 1
    early = {m: metrics([a for a, _, f in rows if f < last], [p for _, p, f in rows if f < last])
             for m, rows in pairs.items()}
    pick = choose(early, metric) if last > 0 else chosen
    holdout = {}
    for m in (pick, "snaive"):
        rows = [(a, p) for a, p, f in pairs[m] if f == last]
        holdout[m] = rows
    return {
        "splits": splits,
        "models": per_model,
        "chosen": chosen,
        "sigma": sigma,
        "hw_params": hw_params,
        "holdout_pick": pick,
        "holdout_pairs": holdout[pick],
        "holdout_naive_pairs": holdout["snaive"],
    }


def wape(pairs):
    tot = sum(a for a, _ in pairs)
    return 100.0 * sum(abs(a - p) for a, p in pairs) / tot if tot > 0 else 0.0


def safe_round(v, nd=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, nd)
