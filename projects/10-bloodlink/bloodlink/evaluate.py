"""Reproduce every number quoted in REPORT.md:  python -m bloodlink.evaluate

All figures come from the synthetic registry / network and the simulator assumptions in
config.py; they compare strategies under identical assumptions, they are not field data.
"""
import json
import time

from . import config, inventory, ranking, simulation
from .dataset import generate_donors


def _time(fn, reps):
    t = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t) / reps * 1000.0


def main(n_requests=300, month_seeds=20):
    donors = generate_donors()
    out = {"registry_donors": len(donors)}

    # 1. Time-to-fulfil: BloodLink waves vs baselines (Monte Carlo, common random numbers)
    out["strategies_default"] = simulation.evaluate_strategies(
        donors, config.HOSPITALS, config.DEMO_NOW, config.DEMO_TODAY, n=n_requests, seed=11)
    out["strategies_no_bystander"] = simulation.evaluate_strategies(
        donors, config.HOSPITALS, config.DEMO_NOW, config.DEMO_TODAY, n=n_requests, seed=11,
        broadcast_factor=1.0)

    # 2. Expired / unmet units over a simulated month, with vs without transfers
    base = inventory.build_snapshot(config.SEED)
    month = inventory.compare_month(base, range(1, month_seeds + 1))
    out["month"] = month["summary"]

    # 3. Demand forecast accuracy (moving average vs naive), 180 synthetic days x 5 banks
    evs = inventory.generate_events(config.SEED + 99, 180)
    tot = {"ma": 0.0, "naive": 0.0, "n": 0}
    for b in config.BANKS:
        series = [sum(e["banks"][b["id"]]["demand"].values()) for e in evs]
        r = inventory.backtest_moving_average(series)
        tot["ma"] += r["mae_ma"] * r["n"]
        tot["naive"] += r["mae_naive"] * r["n"]
        tot["n"] += r["n"]
    out["forecast_mae"] = {"ma7": round(tot["ma"] / tot["n"], 3), "naive": round(tot["naive"] / tot["n"], 3),
                           "points": tot["n"]}

    # 4. Latency of the core operations on this laptop
    req = ranking.normalize_request({"hospital_id": "H1", "group": "A+", "units": 3, "urgency": "critical"},
                                    config.HOSPITALS)
    out["latency_ms"] = {
        "rank_300_donors": round(_time(lambda: ranking.rank(donors, req, config.DEMO_NOW, config.DEMO_TODAY), 50), 2),
        "simulate_3_strategies": round(_time(lambda: simulation.compare(donors, req, config.DEMO_NOW,
                                                                        config.DEMO_TODAY, seed=3), 20), 2),
        "transfer_suggestions": round(_time(lambda: inventory.suggest_transfers(base.stock, base.rates(), 0), 50), 2),
    }
    demo = simulation.compare(donors, req, config.DEMO_NOW, config.DEMO_TODAY, seed=3)
    out["demo_request"] = {k: {m: v[m] for m in ("time_to_fulfil", "alerts", "surplus_trips", "wasted_trips", "wasted_calls")}
                           for k, v in demo.items()}
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
