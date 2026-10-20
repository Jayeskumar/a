"""Sparse features: word 1-2 grams, grapheme 3-4 grams and concept tokens -> TF-IDF.

A document vector is a pair of parallel tuples ``(indices, values)``. Each block
(``w:`` words, ``c:`` characters, ``k:`` concepts) is L2-normalised on its own and then
scaled by ``BLOCK_WEIGHTS`` so the many character n-grams cannot drown the words.
"""

import math

from . import config as C
from .text import char_ngrams, concept_of, tokenize, word_ngrams
from . import lexicon as L


def concepts_with_spans(tokens):
    """[(concept, [token indices])] with lexicon bigrams merged, fillers dropped."""
    seq = []
    for i, t in enumerate(tokens):
        for c in concept_of(t):
            seq.append((c, [i]))
    out, k = [], 0
    while k < len(seq):
        if k + 1 < len(seq) and (seq[k][0], seq[k + 1][0]) in L.PHRASES:
            out.append((L.PHRASES[(seq[k][0], seq[k + 1][0])], sorted(set(seq[k][1] + seq[k + 1][1]))))
            k += 2
        else:
            out.append(seq[k])
            k += 1
    return [(c, s) for c, s in out if c]


def doc_terms(text, with_spans=False):
    """Raw feature counts of one text. With spans, also feature -> token indices (for explanations)."""
    toks = tokenize(text)
    counts, spans = {}, {}

    def add(name, idx):
        counts[name] = counts.get(name, 0) + 1
        if with_spans:
            spans.setdefault(name, []).append(idx)

    for i, t in enumerate(toks):
        add("w:" + t, [i])
        for g in char_ngrams(t, C.CHAR_NGRAMS):
            add("c:" + g, [i])
    for i in range(len(toks) - 1):
        add("w:" + toks[i] + " " + toks[i + 1], [i, i + 1])
    for c, s in concepts_with_spans(toks):
        add("k:" + c, s)
    if with_spans:
        return toks, counts, spans
    return counts


class TfidfVectorizer:
    def __init__(self, min_df=C.MIN_DF, block_weights=None, blocks=("w", "c", "k")):
        self.min_df = min_df
        self.block_weights = dict(block_weights or C.BLOCK_WEIGHTS)
        self.blocks = tuple(blocks)
        self.vocab, self.names, self.idf = {}, [], []

    def _keep(self, name):
        return name[0] in self.blocks

    def fit(self, term_dicts):
        df = {}
        for d in term_dicts:
            for k in d:
                if self._keep(k):
                    df[k] = df.get(k, 0) + 1
        n = len(term_dicts)
        self.names = sorted(k for k, v in df.items() if v >= self.min_df)
        self.vocab = {k: i for i, k in enumerate(self.names)}
        self.idf = [math.log((1.0 + n) / (1.0 + df[k])) + 1.0 for k in self.names]
        return self

    def transform_one(self, terms):
        blocks = {}
        for k, cnt in terms.items():
            j = self.vocab.get(k)
            if j is None:
                continue
            blocks.setdefault(k[0], []).append((j, (1.0 + math.log(cnt)) * self.idf[j]))
        idx, val = [], []
        for b in sorted(blocks):
            items = blocks[b]
            norm = math.sqrt(sum(v * v for _, v in items)) or 1.0
            wgt = self.block_weights.get(b, 1.0) / norm
            for j, v in items:
                idx.append(j)
                val.append(v * wgt)
        order = sorted(range(len(idx)), key=idx.__getitem__)
        return tuple(idx[i] for i in order), tuple(val[i] for i in order)

    def transform(self, term_dicts):
        return [self.transform_one(t) for t in term_dicts]

    def counts_one(self, terms):
        """Raw counts restricted to the vocabulary (input for Multinomial NB)."""
        pairs = sorted((self.vocab[k], float(c)) for k, c in terms.items() if k in self.vocab)
        return tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)

    def counts(self, term_dicts):
        return [self.counts_one(t) for t in term_dicts]

    @property
    def n_features(self):
        return len(self.names)


def append_features(vec, extra):
    """Append extra (index, value) pairs to a sparse vector (indices must be beyond the base vocab)."""
    idx, val = vec
    if not extra:
        return vec
    return tuple(idx) + tuple(i for i, _ in extra), tuple(val) + tuple(v for _, v in extra)


def dot(w, vec):
    idx, val = vec
    return sum(map(float.__mul__, map(w.__getitem__, idx), val)) if idx else 0.0
