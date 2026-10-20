"""Text normalisation and n-gram feature extraction for the Naive Bayes model."""
import re
from collections import Counter

from . import config
from .extract import URL_RE, EMAIL_RE, UPI_RE, PHONE_RE, MONEY_RE

WORD_RE = re.compile(r"__[a-z]+__|[^\W\d_]+", re.UNICODE)
NUM_RE = re.compile(r"\d+")

# Placeholders keep the *kind* of entity (useful evidence) but drop the exact
# value (which would never repeat and only memorises the training set).
PLACEHOLDERS = ("__url__", "__email__", "__upi__", "__phone__", "__money__", "__num__")


def normalise(text):
    t = text.lower()
    t = URL_RE.sub(" __url__ ", t)
    t = EMAIL_RE.sub(" __email__ ", t)
    t = UPI_RE.sub(" __upi__ ", t)
    t = PHONE_RE.sub(" __phone__ ", t)
    t = MONEY_RE.sub(" __money__ ", t)
    t = NUM_RE.sub(" __num__ ", t)
    return t


def words(text):
    """Lower-cased word tokens with entity placeholders (length >= 2)."""
    return [w for w in WORD_RE.findall(normalise(text)) if len(w) >= 2]


def char_ngrams(word, lo=None, hi=None):
    lo = lo or config.CHAR_NGRAM_MIN
    hi = hi or config.CHAR_NGRAM_MAX
    padded = "#" + word + "#"
    grams = []
    for n in range(lo, hi + 1):
        for i in range(len(padded) - n + 1):
            grams.append(padded[i:i + n])
    return grams


def features(text):
    """Bag of weighted features: ``w:`` words, ``b:`` bigrams, ``c:`` char n-grams.

    Char n-grams of one word share a total weight of 1.0 so that a single long
    word does not dominate the multinomial counts.
    """
    toks = words(text)
    bag = Counter()
    for w in toks:
        bag["w:" + w] += 1.0
    for a, b in zip(toks, toks[1:]):
        bag["b:" + a + " " + b] += 1.0
    for w in toks:
        if w in PLACEHOLDERS:
            continue
        grams = char_ngrams(w)
        if not grams:
            continue
        share = 1.0 / len(grams)
        for g in grams:
            bag["c:" + g] += share
    return bag


def pretty_feature(name):
    kind, _, val = name.partition(":")
    label = {"w": "word", "b": "phrase", "c": "char-gram"}.get(kind, kind)
    return label, val
