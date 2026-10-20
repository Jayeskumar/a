"""TextRank extractive summarisation (Mihalcea & Tarau, 2004) from scratch.

1. Each sentence is a node. Edge weight = word-overlap similarity of the two
   sentences' content stems, normalised by sentence length:
       sim(Si, Sj) = |Si ∩ Sj| / (log(|Si|+1) + log(|Sj|+1))
   (+1 inside the log avoids log(1)=0 for one-word sentences.)
2. Weighted PageRank by power iteration:
       WS(Vi) = (1-d)/N + d * Σ_j  w_ji / Σ_k w_jk * WS(Vj)
   Nodes with no edges (dangling) spread their score uniformly.
3. The top-k sentences by score are returned in their original order.
"""
import math

DAMPING = 0.85      # standard PageRank damping factor (Brin & Page)
TOLERANCE = 1e-8    # L1 change between iterations at which we stop
MAX_ITER = 200


def similarity(a_terms, b_terms):
    sa, sb = set(a_terms), set(b_terms)
    overlap = len(sa & sb)
    if not overlap:
        return 0.0
    return overlap / (math.log(len(sa) + 1) + math.log(len(sb) + 1))


def build_graph(term_lists):
    n = len(term_lists)
    sets = [set(t) for t in term_lists]
    logs = [math.log(len(st) + 1) for st in sets]
    w = [[0.0] * n for _ in range(n)]
    for i in range(n):
        si, li = sets[i], logs[i]
        for j in range(i + 1, n):
            overlap = len(si & sets[j])
            if overlap:
                w[i][j] = w[j][i] = overlap / (li + logs[j])
    return w


def pagerank(weights, damping=DAMPING, tol=TOLERANCE, max_iter=MAX_ITER):
    """Weighted PageRank by power iteration. Returns (scores, iterations).
    Scores sum to 1."""
    n = len(weights)
    if n == 0:
        return [], 0
    out_sum = [sum(row) for row in weights]
    # sparse incoming lists: (j, w_ji / out_sum_j) for every edge j -> i
    incoming = [[(j, weights[j][i] / out_sum[j]) for j in range(n) if weights[j][i]]
                for i in range(n)]
    dangling_nodes = [j for j in range(n) if out_sum[j] == 0]
    scores = [1.0 / n] * n
    it = 0
    for it in range(1, max_iter + 1):
        dangling = sum(scores[j] for j in dangling_nodes) / n
        base = (1 - damping) / n + damping * dangling
        new = [base + damping * sum(w * scores[j] for j, w in inc) for inc in incoming]
        delta = sum(abs(a - b) for a, b in zip(new, scores))
        scores = new
        if delta < tol:
            break
    total = sum(scores) or 1.0
    return [s / total for s in scores], it


def rank_sentences(term_lists):
    """Return dict with scores, ranks (0 = best), the graph and iterations used."""
    graph = build_graph(term_lists)
    scores, iters = pagerank(graph)
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    ranks = [0] * len(scores)
    for r, i in enumerate(order):
        ranks[i] = r
    return {"scores": scores, "ranks": ranks, "order": order, "graph": graph,
            "iterations": iters}


def summarize(term_lists, k):
    """Indices of the k best sentences, in document order."""
    res = rank_sentences(term_lists)
    k = max(0, min(k, len(term_lists)))
    return sorted(res["order"][:k])
