"""Reproducible measurements for REPORT.md:  python -m wastewise.evaluate

Prints the simulated-month comparison, routing-only gains, solver runtime (incl. larger
random instances), forecast backtest and classifier hold-out accuracy.
"""

import random
import time

from . import classifier
from . import config as C
from . import routing as R
from .forecast import backtest
from .simulator import Simulation, simulate_month
from .town import Town


def month(seed=None, days=None):
    old = C.SEED
    try:
        if seed is not None:
            C.SEED = seed
        town = Town()
        t0 = time.perf_counter()
        sim, out = simulate_month(days or C.MONTH_DAYS, town)
        wall = (time.perf_counter() - t0) * 1000.0
    finally:
        C.SEED = old
    f, s = sim.worlds["fixed"].totals(), sim.worlds["smart"].totals()
    return f, s, wall


def solver_scaling(sizes=(20, 40, 100, 200, 400), reps=5):
    rng = random.Random(1)
    rows = []
    for n in sizes:
        best = []
        gain = []
        for _ in range(reps):
            pts = [(3.0, -0.5)] + [(rng.uniform(0, 12), rng.uniform(0, 8)) for _ in range(n)]
            d = R.distance_matrix(pts)
            dem = [0] + [rng.uniform(150, 900) for _ in range(n)]
            t0 = time.perf_counter()
            routes, _ = R.clarke_wright(d, dem, C.TRUCK_CAPACITY_L)
            routes = [R.two_opt(r, d)[0] for r in routes]
            best.append((time.perf_counter() - t0) * 1000.0)
            opt = sum(R.route_length(r, d) for r in routes)
            naive = sum(R.route_length(r, d) for r in R.fixed_order(list(range(1, n + 1)), dem,
                                                                  C.TRUCK_CAPACITY_L))
            gain.append(100 * (1 - opt / naive))
        rows.append((n, sum(best) / reps, sum(gain) / reps))
    return rows


def main():
    print("WasteWise evaluation (seed %d)\n" % C.SEED)
    f, s, wall = month()
    print("Simulated month (%d days), fixed beat vs WasteWise:" % f["days"])
    for k in ("km", "fuel_l", "co2_kg", "cost_inr", "truck_hours", "stops", "avg_fill_at_pickup",
              "half_empty_pickups", "overflow_bins", "overflow_l", "collected_l"):
        a, b = f[k], s[k]
        ch = (100 * (1 - b / a)) if a else 0.0
        print("  %-20s %12.2f %12.2f   %+6.1f%%" % (k, a, b, -ch))
    print("  wall time for both 30-day simulations: %.0f ms\n" % wall)

    print("Robustness across other seeds (different towns):")
    for seed in (7, 99, 31337):
        f2, s2, _ = month(seed)
        print("  seed %-6d km saved %5.1f%%   overflow bin-days fixed %3d -> smart %3d" % (
            seed, 100 * (1 - s2["km"] / f2["km"]), f2["overflow_bins"], s2["overflow_bins"]))

    town = Town()
    ms, fo, cw, op = [], 0.0, 0.0, 0.0
    sim = Simulation(town)
    for _ in range(C.MONTH_DAYS):
        a = sim.preview()["plan"]["algorithm"]
        ms.append(a["total_ms"])
        fo += a["fixed_order_km"]
        cw += a["clarke_wright_km"]
        op += a["two_opt_km"]
        sim.step()
    print("\nRouting only (same selected bins, 30 days): fixed order %.1f km, CW %.1f km (%.1f%% shorter),"
          " +2-opt %.1f km (%.2f%% more)" % (fo, cw, 100 * (1 - cw / fo), op, 100 * (1 - op / cw)))
    ms.sort()
    print("Daily planning time (decide + CW + 2-opt + assignment): mean %.2f ms, median %.2f ms, max %.2f ms"
          % (sum(ms) / len(ms), ms[len(ms) // 2], ms[-1]))

    print("\nSolver scaling on random instances (CW + 2-opt, mean of 5):")
    for n, t, g in solver_scaling():
        print("  n=%4d   %8.1f ms   %5.1f%% shorter than visiting in (random) id order" % (n, t, g))

    agg = {}
    for b in town.bins:
        for k, v in backtest([(dow, v) for _, dow, v in town.history(b)]).items():
            agg.setdefault(k, []).append(v)
    print("\nForecast backtest (last 14 of 42 history days, one-step-ahead MAE, all bins):")
    for k, v in sorted(agg.items(), key=lambda kv: sum(kv[1])):
        print("  %-16s %.4f" % (k, sum(v) / len(v)))

    ev = classifier.evaluate()
    print("\nClassifier hold-out: %d/%d = %.1f%% (train %d incl. lexicon)" % (
        round(ev["accuracy"] * ev["test"]), ev["test"], 100 * ev["accuracy"], ev["train"]))
    for c, r in ev["per_class"].items():
        print("  %-11s %d/%d" % (c, r["correct"], r["total"]))


if __name__ == "__main__":
    main()
