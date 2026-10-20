"""Gamified leaderboard: weather-normalised savings vs each building's own past.

A regression baseline (same model as the forecaster) is trained on the
baseline period (weeks 1-6) and asked: "given this weather and calendar, how
much would the building have used in the challenge period (weeks 7-8)?"
Savings % = (expected - actual) / expected. Comparing a building with its own
weather-adjusted past is fair - a hostel is never ranked against a library by
raw kWh (the idea mirrors IPMVP Option C whole-building baselines).
"""

from . import config
from .carbon import co2_kg, cost_inr
from .dataset import BUILDING_BY_ID
from .forecast import LinearForecaster


def compute(ds, detected=None):
    split = config.BASELINE_WEEKS * 168
    rows = []
    for bid, y in ds.loads.items():
        m = LinearForecaster().fit(ds.timestamps[:split], ds.temps[:split], y[:split])
        expected = sum(m.predict(ds.timestamps[split:], ds.temps[split:]))
        actual = sum(y[split:])
        saved = expected - actual
        pct = 100.0 * saved / expected if expected else 0.0
        n_waste = 0
        if detected is not None:
            n_waste = sum(1 for e in detected.get(bid, []) if e["end_index"] >= split)
        b = BUILDING_BY_ID[bid]
        rows.append({
            "building": bid, "name": b["name"], "type": b["type"],
            "expected_kwh": round(expected), "actual_kwh": round(actual),
            "saved_kwh": round(saved), "saving_pct": round(pct, 1),
            "saved_inr": round(cost_inr(saved)), "co2_saved_kg": round(co2_kg(saved)),
            "waste_events_in_period": n_waste,
            "initiative": (b.get("campaign") or {}).get("label"),
        })
    rows.sort(key=lambda r: -r["saving_pct"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        badges = []
        if i == 0 and r["saving_pct"] > config.CHAMPION_MIN_SAVING_PCT:
            badges.append("Green Champion")
        if r["saving_pct"] >= 3 and i != 0:
            badges.append("Energy Saver")
        if r["waste_events_in_period"] == 0:
            badges.append("Zero Waste Alerts")
        if r["saving_pct"] < 0:
            badges.append("Needs Attention")
        r["badges"] = badges
        # points: 10 per % saved, minus 15 per waste alert, floor 0
        r["points"] = max(0, int(round(r["saving_pct"] * 10)) - 15 * r["waste_events_in_period"] + 50)
    return {
        "baseline_period": "%s to %s" % (ds.timestamps[0].date(), ds.timestamps[split - 1].date()),
        "challenge_period": "%s to %s" % (ds.timestamps[split].date(), ds.timestamps[-1].date()),
        "method": "Weather-normalised: robust regression baseline trained on weeks 1-%d "
                  "predicts expected use in weeks %d-8; saving = expected - actual."
                  % (config.BASELINE_WEEKS, config.BASELINE_WEEKS + 1),
        "points_rule": "50 + 10 x saving% - 15 x waste alerts (min 0)",
        "rows": rows,
    }
