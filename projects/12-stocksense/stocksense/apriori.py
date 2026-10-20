"""Apriori frequent itemsets and association rules (support, confidence, lift), from scratch."""
from itertools import combinations


def frequent_itemsets(transactions, min_support, max_len=4):
    """Return dict frozenset -> support count for all itemsets with support >= min_support.

    min_support may be a fraction (< 1) of transactions or an absolute count (>= 1).
    Level-wise: count k-itemsets, join frequent (k-1)-itemsets that share k-2 items,
    prune candidates having any infrequent (k-1)-subset (the Apriori property).
    """
    tx = [frozenset(t) for t in transactions if t]
    n = len(tx)
    min_count = min_support if min_support >= 1 else min_support * n
    counts = {}
    for t in tx:
        for i in t:
            counts[i] = counts.get(i, 0) + 1
    current = {frozenset([i]): c for i, c in counts.items() if c >= min_count}
    result = dict(current)
    k = 2
    while current and k <= max_len:
        prev = sorted(tuple(sorted(s)) for s in current)
        prev_set = set(current)
        candidates = set()
        for i in range(len(prev)):
            for j in range(i + 1, len(prev)):
                a, b = prev[i], prev[j]
                if a[:-1] != b[:-1]:
                    break  # sorted: no later b shares the prefix
                cand = frozenset(a + (b[-1],))
                if all(frozenset(sub) in prev_set for sub in combinations(sorted(cand), k - 1)):
                    candidates.add(cand)
        if not candidates:
            break
        frequent_items = set().union(*candidates)
        cnt = {}
        for t in tx:
            items = sorted(t & frequent_items)
            if len(items) < k:
                continue
            for combo in combinations(items, k):
                fs = frozenset(combo)
                if fs in candidates:
                    cnt[fs] = cnt.get(fs, 0) + 1
        current = {s: c for s, c in cnt.items() if c >= min_count}
        result.update(current)
        k += 1
    return result, n


def association_rules(freq, n, min_confidence=0.5, min_lift=0.0):
    """Rules A -> C from every frequent itemset; sorted by lift then confidence."""
    rules = []
    for itemset, count in freq.items():
        if len(itemset) < 2:
            continue
        items = sorted(itemset)
        for r in range(1, len(items)):
            for ante in combinations(items, r):
                a = frozenset(ante)
                c = itemset - a
                conf = count / freq[a]
                lift = conf / (freq[c] / n)
                if conf >= min_confidence and lift >= min_lift:
                    rules.append({
                        "antecedent": sorted(a), "consequent": sorted(c),
                        "support": count / n, "confidence": conf, "lift": lift, "count": count,
                    })
    rules.sort(key=lambda r: (-r["lift"], -r["confidence"], r["antecedent"], r["consequent"]))
    return rules


def placement_suggestions(rules, items, limit=8):
    """Turn strong rules into shelf / bundle advice a shopkeeper can act on.

    Mixes three kinds so one aisle does not dominate: cross-category adjacency (most valuable:
    customers would not otherwise walk past), bundles of 3+ items, and same-bay pairs.
    """
    name = lambda s: items.get(s, {}).get("name", s)
    cat = lambda s: items.get(s, {}).get("category", "")
    quota = {"adjacent": 4, "bundle": 2, "same-bay": 3}
    picked, used = [], []
    for r in rules:
        if r["lift"] < 1.5:
            continue
        key = frozenset(r["antecedent"] + r["consequent"])
        if any(key <= u or u <= key for u in used):
            continue   # skip mirror rules and sub/supersets of an itemset already suggested
        if any(sum(1 for u in used if x in u) >= 2 for x in key):
            continue   # no single SKU in more than two suggestions
        a = " + ".join(name(s) for s in r["antecedent"])
        c = " + ".join(name(s) for s in r["consequent"])
        why = "%.0f%% of bills with %s also have %s (lift %.1fx, %d bills)" % (
            100 * r["confidence"], a, c, r["lift"], r["count"])
        if len(key) >= 3:
            kind, action = "bundle", "Bundle offer: %s with %s" % (a, c)
        elif len({cat(x) for x in key}) > 1:
            kind, action = "adjacent", "Cross-merchandise: shelve %s next to %s" % (c, a)
        else:
            kind, action = "same-bay", "Keep %s and %s side by side; try a combo price" % (a, c)
        if quota[kind] <= 0:
            continue
        quota[kind] -= 1
        used.append(key)
        picked.append({"action": action, "why": why, "kind": kind, "lift": round(r["lift"], 2),
                       "confidence": round(r["confidence"], 3), "items": sorted(key)})
        if len(picked) >= limit:
            break
    order = {"adjacent": 0, "bundle": 1, "same-bay": 2}
    picked.sort(key=lambda x: (order[x["kind"]], -x["lift"]))
    return picked
