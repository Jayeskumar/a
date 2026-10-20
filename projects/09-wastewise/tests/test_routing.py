import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wastewise import routing as R  # noqa: E402


def hand_instance():
    """Depot (0,0); customers 1 (0,4), 2 (1,4), 3 (4,0), 4 (4,1) on a street grid.

    Manhattan distances:            savings s_ij = d0i + d0j - dij
      d01=4 d02=5 d03=4 d04=5        s12 = 4+5-1 = 8     s34 = 4+5-1 = 8
      d12=1 d13=8 d14=7              s24 = 5+5-6 = 4
      d23=7 d24=6 d34=1              s14 = 4+5-7 = 2     s23 = 5+4-7 = 2    s13 = 0
    """
    pts = [(0, 0), (0, 4), (1, 4), (4, 0), (4, 1)]
    return R.distance_matrix(pts)


class SavingsTest(unittest.TestCase):
    def test_savings_values_and_order(self):
        d = hand_instance()
        s = R.savings_list(d, [1, 2, 3, 4])
        self.assertEqual(s, [(8, 1, 2), (8, 3, 4), (4, 2, 4), (2, 1, 4), (2, 2, 3)])  # s13=0 dropped

    def test_capacity_two_gives_two_pairs(self):
        d = hand_instance()
        routes, trace = R.clarke_wright(d, [0, 1, 1, 1, 1], capacity=2)
        self.assertEqual(sorted(map(sorted, routes)), [[1, 2], [3, 4]])
        # 36 km for four out-and-back trips minus savings 8 + 8
        self.assertAlmostEqual(sum(R.route_length(r, d) for r in routes), 20.0)
        self.assertEqual(len(trace["merges"]), 2)
        self.assertGreaterEqual(trace["rejected_capacity"], 1)

    def test_capacity_four_links_pairs_through_best_saving(self):
        d = hand_instance()
        routes, _ = R.clarke_wright(d, [0, 1, 1, 1, 1], capacity=4)
        self.assertEqual(len(routes), 1)
        r = routes[0]
        self.assertIn(r, ([1, 2, 4, 3], [3, 4, 2, 1]))  # 2-4 link (saving 4) joins the pairs
        self.assertAlmostEqual(R.route_length(r, d), 36 - 8 - 8 - 4)

    def test_capacity_one_keeps_everyone_separate(self):
        d = hand_instance()
        routes, _ = R.clarke_wright(d, [0, 1, 1, 1, 1], capacity=1)
        self.assertEqual(routes, [[1], [2], [3], [4]])

    def test_duration_limit_blocks_merges(self):
        d = hand_instance()
        # 1 km/min speed, no service: route [1,2] takes 10 min; a 9-minute limit forbids it
        routes, trace = R.clarke_wright(d, [0, 1, 1, 1, 1], capacity=10, max_duration=9,
                                        kmph=60.0, service_min=0.0, unload_min=0.0)
        self.assertEqual(len(routes), 4)
        self.assertGreater(trace["rejected_duration"], 0)


class TwoOptTest(unittest.TestCase):
    def test_uncrosses_square(self):
        pts = [(0, 0), (0, 2), (2, 2), (2, 0)]
        d = R.distance_matrix(pts)
        bad = [1, 3, 2]
        self.assertAlmostEqual(R.route_length(bad, d), 12)
        good, moves = R.two_opt(bad, d)
        self.assertAlmostEqual(R.route_length(good, d), 8)
        self.assertGreaterEqual(moves, 1)

    def test_never_worsens_random_routes(self):
        rng = random.Random(7)
        for trial in range(60):
            n = rng.randint(1, 18)
            pts = [(0.0, 0.0)] + [(rng.uniform(0, 6), rng.uniform(0, 4)) for _ in range(n)]
            d = R.distance_matrix(pts)
            route = list(range(1, n + 1))
            rng.shuffle(route)
            before = R.route_length(route, d)
            after_route, _ = R.two_opt(route, d)
            self.assertLessEqual(R.route_length(after_route, d), before + 1e-9)
            self.assertEqual(sorted(after_route), sorted(route))

    def test_optimal_route_is_unchanged_in_length(self):
        pts = [(0, 0), (0, 1), (0, 2), (0, 3)]
        d = R.distance_matrix(pts)
        r, _ = R.two_opt([1, 2, 3], d)
        self.assertAlmostEqual(R.route_length(r, d), 6)


class CapacityTest(unittest.TestCase):
    def test_random_instances_respect_capacity_and_cover_everyone(self):
        rng = random.Random(42)
        for trial in range(40):
            n = rng.randint(2, 35)
            pts = [(3.0, -0.5)] + [(rng.uniform(0, 6), rng.uniform(0, 4)) for _ in range(n)]
            d = R.distance_matrix(pts)
            demand = [0] + [rng.uniform(100, 1100) for _ in range(n)]
            cap = 5000
            routes, _ = R.clarke_wright(d, demand, cap, max_duration=210, kmph=15,
                                        service_min=8, unload_min=20)
            seen = sorted(c for r in routes for c in r)
            self.assertEqual(seen, list(range(1, n + 1)))
            for r in routes:
                self.assertLessEqual(sum(demand[c] for c in r), cap + 1e-6)
                if len(r) > 1:
                    self.assertLessEqual(R.route_duration(r, d, 15, 8, 20), 210 + 1e-6)
                improved, _ = R.two_opt(r, d)
                self.assertLessEqual(R.route_length(improved, d), R.route_length(r, d) + 1e-9)

    def test_savings_beat_naive_order_on_average(self):
        rng = random.Random(3)
        cw_total = naive_total = 0.0
        for _ in range(20):
            n = 25
            pts = [(3.0, -0.5)] + [(rng.uniform(0, 6), rng.uniform(0, 4)) for _ in range(n)]
            d = R.distance_matrix(pts)
            demand = [0] + [rng.uniform(200, 800) for _ in range(n)]
            routes, _ = R.clarke_wright(d, demand, 5000)
            cw_total += sum(R.route_length(R.two_opt(r, d)[0], d) for r in routes)
            naive = R.fixed_order(list(range(1, n + 1)), demand, 5000)
            naive_total += sum(R.route_length(r, d) for r in naive)
        self.assertLess(cw_total, 0.8 * naive_total)

    def test_fixed_order_splits_when_full(self):
        trips = R.fixed_order([1, 2, 3, 4], [0, 3, 3, 3, 1], 6)
        self.assertEqual(trips, [[1, 2], [3, 4]])

    def test_assign_trips_lpt_and_overflow(self):
        per, un = R.assign_trips([100, 90, 80, 70], 2, 180)
        self.assertEqual(un, [])
        loads = sorted(sum([100, 90, 80, 70][k] for k in t) for t in per)
        self.assertEqual(loads, [170, 170])
        per, un = R.assign_trips([150, 150, 150], 2, 200)
        self.assertEqual(len(un), 1)


if __name__ == "__main__":
    unittest.main()
