"""Capacitated vehicle routing, written from scratch.

* clarke_wright  - parallel Clarke-Wright savings heuristic (capacity + optional duration limit)
* two_opt        - 2-opt local search on a single depot-to-depot route (never makes it longer)
* fixed_order    - the naive baseline: visit customers in a given order, split when the truck is full
* assign_trips   - pack trips onto trucks (longest-trip-first) within a shift

All functions work on an index space where 0 is the depot and 1..n are customers, with a
symmetric distance matrix `dist` (list of lists, km).
"""

EPS = 1e-9


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def distance_matrix(points):
    """points[0] is the depot. Street-grid (Manhattan) distances in km."""
    return [[round(manhattan(p, q), 6) for q in points] for p in points]


def route_length(route, dist, depot=0):
    """Length of depot -> route... -> depot."""
    if not route:
        return 0.0
    total = dist[depot][route[0]] + dist[route[-1]][depot]
    for a, b in zip(route, route[1:]):
        total += dist[a][b]
    return total


def route_duration(route, dist, kmph, service_min, unload_min):
    """Minutes for one trip: drive + service every stop + unload at the depot."""
    if not route:
        return 0.0
    return route_length(route, dist) / kmph * 60.0 + service_min * len(route) + unload_min


def savings_list(dist, customers):
    """All positive savings s_ij = d0i + d0j - dij, sorted high to low (ties by index)."""
    out = []
    for a in range(len(customers)):
        i = customers[a]
        for b in range(a + 1, len(customers)):
            j = customers[b]
            s = dist[0][i] + dist[0][j] - dist[i][j]
            if s > EPS:
                out.append((round(s, 6), i, j))
    out.sort(key=lambda t: (-t[0], t[1], t[2]))
    return out


def clarke_wright(dist, demand, capacity, customers=None, max_duration=None,
                  kmph=None, service_min=0.0, unload_min=0.0):
    """Parallel Clarke-Wright savings algorithm.

    dist      : (n+1)x(n+1) matrix, index 0 = depot
    demand    : list indexed like dist (demand[0] ignored)
    capacity  : vehicle capacity in the same unit as demand
    max_duration (optional): minutes per trip limit, needs kmph/service_min/unload_min

    Returns (routes, trace). routes is a list of customer lists (depot omitted). Every customer
    appears exactly once; no route exceeds capacity (a single customer heavier than the
    capacity still gets its own route, flagged in trace["oversize"]).
    """
    if customers is None:
        customers = list(range(1, len(dist)))
    route_of = {}
    routes = {}
    load = {}
    for c in customers:
        routes[c] = [c]
        route_of[c] = c
        load[c] = demand[c]
    trace = {"savings_considered": 0, "merges": [], "rejected_capacity": 0,
             "rejected_duration": 0, "oversize": [c for c in customers if demand[c] > capacity]}

    def duration(r):
        return route_duration(r, dist, kmph, service_min, unload_min)

    for s, i, j in savings_list(dist, customers):
        trace["savings_considered"] += 1
        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            continue
        A, B = routes[ri], routes[rj]
        if A[-1] == i and B[0] == j:
            new = A + B
        elif A[0] == i and B[-1] == j:
            new = B + A
        elif A[-1] == i and B[-1] == j:
            new = A + B[::-1]
        elif A[0] == i and B[0] == j:
            new = A[::-1] + B
        else:
            continue  # i or j is interior to its route: cannot link them
        if load[ri] + load[rj] > capacity + EPS:
            trace["rejected_capacity"] += 1
            continue
        if max_duration is not None and duration(new) > max_duration + EPS:
            trace["rejected_duration"] += 1
            continue
        routes[ri] = new
        load[ri] += load[rj]
        for c in B:
            route_of[c] = ri
        del routes[rj], load[rj]
        trace["merges"].append({"i": i, "j": j, "saving": s})
    ordered = sorted(routes.values(), key=lambda r: min(r))
    return ordered, trace


def two_opt(route, dist, depot=0, max_passes=50):
    """2-opt improvement of a single trip. Returns (new_route, moves).

    Considers the closed tour depot-route-depot and reverses the segment between two edges
    whenever that strictly shortens the tour. Because only strict improvements are applied,
    the result is never longer than the input.
    """
    tour = [depot] + list(route) + [depot]
    n = len(tour)
    moves = 0
    if n < 5:  # fewer than 3 customers: nothing to uncross
        return list(route), 0
    for _ in range(max_passes):
        improved = False
        for a in range(0, n - 3):
            for b in range(a + 2, n - 1):
                d = (dist[tour[a]][tour[b]] + dist[tour[a + 1]][tour[b + 1]]
                     - dist[tour[a]][tour[a + 1]] - dist[tour[b]][tour[b + 1]])
                if d < -EPS:
                    tour[a + 1:b + 1] = tour[a + 1:b + 1][::-1]
                    moves += 1
                    improved = True
        if not improved:
            break
    return tour[1:-1], moves


def fixed_order(order, demand, capacity):
    """Naive baseline: keep the given order, start a new trip whenever the truck would overflow."""
    trips, cur, load = [], [], 0.0
    for c in order:
        if cur and load + demand[c] > capacity + EPS:
            trips.append(cur)
            cur, load = [], 0.0
        cur.append(c)
        load += demand[c]
    if cur:
        trips.append(cur)
    return trips


def assign_trips(durations, n_trucks, shift_min):
    """Longest-processing-time-first packing of trips onto trucks.

    durations: list of trip durations (minutes). Returns (per_truck, unassigned) where per_truck
    is a list (one per truck) of trip indices and unassigned the trip indices that did not fit.
    """
    order = sorted(range(len(durations)), key=lambda k: (-durations[k], k))
    used = [0.0] * n_trucks
    per_truck = [[] for _ in range(n_trucks)]
    unassigned = []
    for k in order:
        best = None
        for t in range(n_trucks):
            if used[t] + durations[k] <= shift_min + EPS and (best is None or used[t] < used[best]):
                best = t
        if best is None:
            unassigned.append(k)
        else:
            per_truck[best].append(k)
            used[best] += durations[k]
    return per_truck, unassigned
