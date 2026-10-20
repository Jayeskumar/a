"""CART decision trees + Random Forest, from scratch.

CART: binary splits `x[f] <= t`, chosen to minimise weighted Gini impurity
      G = 1 - sum_k p_k^2. The best threshold per feature is found with one sorted sweep
      (O(n log n)) while class counts and sum-of-squares are updated incrementally.
Random Forest: each tree sees a bootstrap sample (draw n rows with replacement) and only
      `max_features` randomly chosen features at each node (feature bagging). Prediction =
      average of leaf class distributions (soft voting).
Explanations: every node stores its class distribution, so a prediction path can be
      decomposed into per-feature contributions (Saabas / "tree interpreter" method):
      P(c|x) = P_root(c) + sum over splits on the path of [P_child(c) - P_parent(c)].
"""
import random


class Node:
    __slots__ = ("feature", "threshold", "left", "right", "dist", "n")

    def __init__(self, dist, n):
        self.feature = None
        self.threshold = None
        self.left = None
        self.right = None
        self.dist = dist        # list of class probabilities at this node
        self.n = n

    @property
    def is_leaf(self):
        return self.feature is None


def gini_from_counts(counts, n):
    if n == 0:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in counts)


class DecisionTree:
    def __init__(self, max_depth=10, min_samples_split=2, max_features=None, rng=None):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.max_features = max_features
        self.rng = rng or random.Random(0)
        self.root = None
        self.n_classes = 0
        self.n_features = 0
        self.importances = []

    # X: list of rows; y: list of int class ids in [0, n_classes)
    def fit(self, X, y, n_classes=None):
        self.n_classes = n_classes or (max(y) + 1)
        self.n_features = len(X[0])
        self.importances = [0.0] * self.n_features
        self._n_total = float(len(X))
        self.root = self._build(X, y, list(range(len(X))), 0)
        return self

    def _dist(self, y, idx):
        counts = [0] * self.n_classes
        for i in idx:
            counts[y[i]] += 1
        n = len(idx)
        return counts, [c / n for c in counts]

    def best_split(self, X, y, idx, features):
        """Return (gain, feature, threshold) of the best Gini split or None."""
        n = len(idx)
        parent_counts = [0] * self.n_classes
        for i in idx:
            parent_counts[y[i]] += 1
        parent_g = gini_from_counts(parent_counts, n)
        best = None
        total_sq = sum(c * c for c in parent_counts)
        for f in features:
            order = sorted(idx, key=lambda i: X[i][f])
            left = [0] * self.n_classes
            right = parent_counts[:]
            left_sq, right_sq = 0, total_sq
            for pos in range(n - 1):
                k = y[order[pos]]
                # move one sample from right to left; update sums of squares in O(1)
                left_sq += 2 * left[k] + 1
                left[k] += 1
                right_sq -= 2 * right[k] - 1
                right[k] -= 1
                v, v_next = X[order[pos]][f], X[order[pos + 1]][f]
                if v == v_next:
                    continue
                nl, nr = pos + 1, n - pos - 1
                g = (nl * (1 - left_sq / (nl * nl)) + nr * (1 - right_sq / (nr * nr))) / n
                gain = parent_g - g
                if best is None or gain > best[0] + 1e-12:
                    best = (gain, f, (v + v_next) / 2.0)
        return best

    def _build(self, X, y, idx, depth):
        counts, dist = self._dist(y, idx)
        node = Node(dist, len(idx))
        pure = max(counts) == len(idx)
        if pure or depth >= self.max_depth or len(idx) < self.min_samples_split:
            return node
        feats = list(range(self.n_features))
        if self.max_features and self.max_features < self.n_features:
            feats = self.rng.sample(feats, self.max_features)
        split = self.best_split(X, y, idx, feats)
        if split is None or split[0] <= 0:
            return node
        gain, f, t = split
        left_idx = [i for i in idx if X[i][f] <= t]
        right_idx = [i for i in idx if X[i][f] > t]
        if not left_idx or not right_idx:
            return node
        self.importances[f] += gain * len(idx) / self._n_total   # mean decrease in impurity
        node.feature, node.threshold = f, t
        node.left = self._build(X, y, left_idx, depth + 1)
        node.right = self._build(X, y, right_idx, depth + 1)
        return node

    def leaf(self, x):
        node = self.root
        while not node.is_leaf:
            node = node.left if x[node.feature] <= node.threshold else node.right
        return node

    def predict_proba(self, x):
        return self.leaf(x).dist

    def predict(self, x):
        d = self.predict_proba(x)
        return max(range(len(d)), key=d.__getitem__)

    def contributions(self, x, cls):
        """(bias, per-feature contributions) such that bias + sum(contrib) = P(cls | x)."""
        contrib = [0.0] * self.n_features
        node = self.root
        bias = node.dist[cls]
        while not node.is_leaf:
            child = node.left if x[node.feature] <= node.threshold else node.right
            contrib[node.feature] += child.dist[cls] - node.dist[cls]
            node = child
        return bias, contrib

    def depth(self, node=None):
        node = node or self.root
        if node.is_leaf:
            return 0
        return 1 + max(self.depth(node.left), self.depth(node.right))


class RandomForest:
    def __init__(self, n_trees=30, max_depth=10, min_samples_split=4, max_features=3, seed=7):
        self.n_trees = n_trees
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.max_features = max_features
        self.seed = seed
        self.trees = []
        self.classes = []
        self.oob_score = None

    def fit(self, X, y):
        self.classes = sorted(set(y))
        cid = {c: i for i, c in enumerate(self.classes)}
        yi = [cid[v] for v in y]
        rng = random.Random(self.seed)
        n = len(X)
        self.trees = []
        oob_votes = [None] * n
        for _ in range(self.n_trees):
            sample = [rng.randrange(n) for _ in range(n)]     # bootstrap
            Xb = [X[i] for i in sample]
            yb = [yi[i] for i in sample]
            tree = DecisionTree(self.max_depth, self.min_samples_split, self.max_features,
                                random.Random(rng.random()))
            tree.fit(Xb, yb, len(self.classes))
            self.trees.append(tree)
            in_bag = set(sample)
            for i in range(n):                                 # out-of-bag votes
                if i not in in_bag:
                    d = tree.predict_proba(X[i])
                    if oob_votes[i] is None:
                        oob_votes[i] = list(d)
                    else:
                        oob_votes[i] = [a + b for a, b in zip(oob_votes[i], d)]
        scored = [(v, yi[i]) for i, v in enumerate(oob_votes) if v is not None]
        if scored:
            hits = sum(1 for v, t in scored if max(range(len(v)), key=v.__getitem__) == t)
            self.oob_score = hits / float(len(scored))
        return self

    def predict_proba(self, x):
        acc = [0.0] * len(self.classes)
        for t in self.trees:
            for i, p in enumerate(t.predict_proba(x)):
                acc[i] += p
        k = float(len(self.trees))
        return {c: acc[i] / k for i, c in enumerate(self.classes)}

    def predict(self, x):
        p = self.predict_proba(x)
        return max(p, key=p.get)

    def feature_importances(self):
        n_feat = self.trees[0].n_features
        tot = [0.0] * n_feat
        for t in self.trees:
            for i, v in enumerate(t.importances):
                tot[i] += v
        s = sum(tot) or 1.0
        return [v / s for v in tot]

    def contributions(self, x, cls_label):
        ci = self.classes.index(cls_label)
        bias, contrib = 0.0, None
        for t in self.trees:
            b, c = t.contributions(x, ci)
            bias += b
            contrib = c if contrib is None else [a + v for a, v in zip(contrib, c)]
        k = float(len(self.trees))
        return bias / k, [v / k for v in contrib]
