"""Which bin does this go in? A from-scratch multinomial Naive Bayes over item names in
English, Tamil and Tanglish (romanised Tamil).

Features: whole words (with a light English plural strip) + character 3-grams inside each word.
Character n-grams make it robust to spelling variants and Tamil suffixes ("தோல்" / "தோலை").
A dictionary of exact item names is checked first ("rule: exact match"); otherwise NB decides.
"""

import math
import re

LABELS = ("wet", "dry", "recyclable", "hazardous")

BIN_INFO = {
    "wet": {"bin": "Green bin - wet / biodegradable", "color": "#16a34a",
            "tip": "Drain liquids, no plastic covers. Goes to compost / biogas.",
            "ta": "பச்சை தொட்டி - மக்கும் குப்பை"},
    "dry": {"bin": "Blue bin - dry (non-recyclable)", "color": "#2563eb",
            "tip": "Wrap sanitary waste in newspaper before binning.",
            "ta": "நீல தொட்டி - மக்காத குப்பை"},
    "recyclable": {"bin": "Yellow bin - recyclables", "color": "#d97706",
                   "tip": "Rinse and flatten. Sold to recyclers - keep it clean and dry.",
                   "ta": "மஞ்சள் தொட்டி - மறுசுழற்சி"},
    "hazardous": {"bin": "No bin - hazardous drop point", "color": "#dc2626",
                  "tip": "Never in a street bin. Hand over at the ward hazardous / e-waste point.",
                  "ta": "அபாயகரமான கழிவு - வார்டு சேகரிப்பு மையம்"},
}

# (item name, label). English, Tamil and Tanglish variants of common household items.
DATA = [
    # ---------------------------------------------------------------- wet
    ("banana peel", "wet"), ("banana skin", "wet"), ("vegetable peels", "wet"),
    ("vegetable waste", "wet"), ("fruit peels", "wet"), ("orange peel", "wet"),
    ("mango peel", "wet"), ("mango seed", "wet"), ("apple core", "wet"),
    ("onion peels", "wet"), ("potato peels", "wet"), ("leftover food", "wet"),
    ("cooked rice", "wet"), ("stale food", "wet"), ("rotten vegetables", "wet"),
    ("rotten fruits", "wet"), ("tea leaves", "wet"), ("used tea powder", "wet"),
    ("coffee grounds", "wet"), ("coffee powder", "wet"), ("egg shells", "wet"),
    ("fish waste", "wet"), ("fish bones", "wet"), ("chicken bones", "wet"),
    ("meat waste", "wet"), ("mutton bones", "wet"), ("coconut shell", "wet"),
    ("coconut husk", "wet"), ("tender coconut shell", "wet"), ("flowers", "wet"),
    ("temple flowers", "wet"), ("flower garland", "wet"), ("dry leaves", "wet"),
    ("garden leaves", "wet"), ("grass clippings", "wet"), ("banana leaf", "wet"),
    ("areca leaf plate", "wet"), ("curry leaves", "wet"), ("cow dung", "wet"),
    ("sugarcane waste", "wet"), ("corn cob", "wet"), ("groundnut shells", "wet"),
    ("peanut shells", "wet"), ("tamarind seeds", "wet"), ("spoiled idli batter", "wet"),
    ("bread", "wet"), ("chapati", "wet"), ("spoilt milk", "wet"), ("food scraps", "wet"),
    ("kitchen waste", "wet"), ("watermelon rind", "wet"), ("lemon peel", "wet"),
    ("வாழைப்பழத் தோல்", "wet"), ("வாழைப்பழ தோல்", "wet"), ("காய்கறி தோல்", "wet"),
    ("காய்கறி கழிவு", "wet"), ("பழத் தோல்", "wet"), ("ஆரஞ்சு தோல்", "wet"),
    ("மாம்பழத் தோல்", "wet"), ("வெங்காயத் தோல்", "wet"), ("உருளைக்கிழங்கு தோல்", "wet"),
    ("மீதமுள்ள உணவு", "wet"), ("மிச்ச சாப்பாடு", "wet"), ("பழைய சாதம்", "wet"),
    ("கெட்டுப்போன காய்கறி", "wet"), ("டீ தூள்", "wet"), ("காபி தூள்", "wet"),
    ("முட்டை ஓடு", "wet"), ("மீன் கழிவு", "wet"), ("மீன் முள்", "wet"),
    ("கோழி எலும்பு", "wet"), ("இறைச்சி கழிவு", "wet"), ("தேங்காய் ஓடு", "wet"),
    ("தேங்காய் மட்டை", "wet"), ("இளநீர் மட்டை", "wet"), ("பூக்கள்", "wet"),
    ("கோவில் பூ", "wet"), ("பூ மாலை", "wet"), ("காய்ந்த இலைகள்", "wet"), ("புல்", "wet"),
    ("வாழை இலை", "wet"), ("பாக்கு மட்டை தட்டு", "wet"), ("கறிவேப்பிலை", "wet"),
    ("சாணம்", "wet"), ("கரும்புச் சக்கை", "wet"), ("வேர்க்கடலை தோல்", "wet"),
    ("புளியங்கொட்டை", "wet"), ("சமையலறை கழிவு", "wet"), ("சப்பாத்தி", "wet"),
    ("vazhaipazham thol", "wet"), ("thengai odu", "wet"), ("muttai odu", "wet"),
    ("kaaikari kazhivu", "wet"), ("meen kazhivu", "wet"), ("poo maalai", "wet"),
    ("pazhaya saadham", "wet"), ("tea thool", "wet"), ("vazhai ilai", "wet"),
    # ---------------------------------------------------------------- dry
    ("chips packet", "dry"), ("biscuit wrapper", "dry"), ("chocolate wrapper", "dry"),
    ("multilayer packet", "dry"), ("sanitary napkin", "dry"), ("diaper", "dry"),
    ("baby diaper", "dry"), ("cigarette butt", "dry"), ("broken ceramic cup", "dry"),
    ("broken ceramic plate", "dry"), ("thermocol", "dry"), ("styrofoam box", "dry"),
    ("rubber slipper", "dry"), ("old chappal", "dry"), ("old shoes", "dry"),
    ("old clothes", "dry"), ("torn clothes", "dry"), ("rags", "dry"), ("sweepings", "dry"),
    ("floor dust", "dry"), ("hair", "dry"), ("cotton swab", "dry"), ("band aid", "dry"),
    ("chewing gum", "dry"), ("paper cup", "dry"), ("toothbrush", "dry"),
    ("toothpaste tube", "dry"), ("kitchen sponge", "dry"), ("steel scrubber", "dry"),
    ("face mask", "dry"), ("rubber gloves", "dry"), ("candle wax", "dry"),
    ("noodles wrapper", "dry"), ("gutka sachet", "dry"), ("shampoo sachet", "dry"),
    ("சிப்ஸ் பாக்கெட்", "dry"), ("பிஸ்கட் கவர்", "dry"), ("சாக்லேட் கவர்", "dry"),
    ("சானிட்டரி நாப்கின்", "dry"), ("டயப்பர்", "dry"), ("குழந்தை டயப்பர்", "dry"),
    ("சிகரெட் துண்டு", "dry"), ("உடைந்த பீங்கான் கோப்பை", "dry"), ("தெர்மாகோல்", "dry"),
    ("ரப்பர் செருப்பு", "dry"), ("பழைய செருப்பு", "dry"), ("பழைய துணி", "dry"),
    ("கிழிந்த துணி", "dry"), ("பெருக்கிய தூசி", "dry"), ("முடி", "dry"),
    ("பல் துலக்கும் பிரஷ்", "dry"), ("பற்பசை குழாய்", "dry"), ("முகக்கவசம்", "dry"),
    ("பேப்பர் கப்", "dry"), ("ஷாம்பு சாஷே", "dry"),
    ("pazhaya thuni", "dry"), ("pazhaya seruppu", "dry"), ("chips cover", "dry"),
    # ---------------------------------------------------------------- recyclable
    ("plastic bottle", "recyclable"), ("water bottle", "recyclable"),
    ("pet bottle", "recyclable"), ("plastic container", "recyclable"),
    ("plastic box", "recyclable"), ("plastic bucket", "recyclable"),
    ("milk packet", "recyclable"), ("milk cover", "recyclable"),
    ("oil packet", "recyclable"), ("shampoo bottle", "recyclable"),
    ("newspaper", "recyclable"), ("old newspapers", "recyclable"),
    ("magazine", "recyclable"), ("notebook", "recyclable"), ("old books", "recyclable"),
    ("paper", "recyclable"), ("office paper", "recyclable"), ("cardboard", "recyclable"),
    ("cardboard box", "recyclable"), ("carton box", "recyclable"),
    ("glass bottle", "recyclable"), ("glass jar", "recyclable"),
    ("pickle jar", "recyclable"), ("tin can", "recyclable"),
    ("aluminium can", "recyclable"), ("soft drink can", "recyclable"),
    ("steel vessel", "recyclable"), ("steel tumbler", "recyclable"),
    ("iron scrap", "recyclable"), ("metal scrap", "recyclable"),
    ("brass vessel", "recyclable"), ("aluminium foil", "recyclable"),
    ("bottle caps", "recyclable"), ("egg tray", "recyclable"),
    ("plastic jar", "recyclable"), ("paper bag", "recyclable"),
    ("பிளாஸ்டிக் பாட்டில்", "recyclable"), ("தண்ணீர் பாட்டில்", "recyclable"),
    ("பிளாஸ்டிக் டப்பா", "recyclable"), ("பிளாஸ்டிக் வாளி", "recyclable"),
    ("பால் பாக்கெட்", "recyclable"), ("பால் கவர்", "recyclable"),
    ("எண்ணெய் பாக்கெட்", "recyclable"), ("ஷாம்பு பாட்டில்", "recyclable"),
    ("செய்தித்தாள்", "recyclable"), ("பழைய செய்தித்தாள்", "recyclable"),
    ("பழைய புத்தகம்", "recyclable"), ("நோட்டுப் புத்தகம்", "recyclable"),
    ("காகிதம்", "recyclable"), ("அட்டைப்பெட்டி", "recyclable"), ("அட்டை", "recyclable"),
    ("கண்ணாடி பாட்டில்", "recyclable"), ("கண்ணாடி ஜாடி", "recyclable"),
    ("ஊறுகாய் பாட்டில்", "recyclable"), ("தகர டப்பா", "recyclable"),
    ("அலுமினியம் டப்பா", "recyclable"), ("குளிர்பான டின்", "recyclable"),
    ("எவர்சில்வர் பாத்திரம்", "recyclable"), ("பழைய இரும்பு", "recyclable"),
    ("பித்தளை பாத்திரம்", "recyclable"), ("முட்டை அட்டை", "recyclable"),
    ("paal packet", "recyclable"), ("plastic dabba", "recyclable"),
    ("pazhaya irumbu", "recyclable"), ("pazhaya paper", "recyclable"),
    # ---------------------------------------------------------------- hazardous
    ("battery", "hazardous"), ("used batteries", "hazardous"), ("aa battery", "hazardous"),
    ("mobile battery", "hazardous"), ("power bank", "hazardous"), ("tube light", "hazardous"),
    ("cfl bulb", "hazardous"), ("led bulb", "hazardous"), ("expired medicines", "hazardous"),
    ("old tablets", "hazardous"), ("syringe", "hazardous"), ("injection needle", "hazardous"),
    ("paint can", "hazardous"), ("paint tin", "hazardous"), ("pesticide bottle", "hazardous"),
    ("insecticide spray can", "hazardous"), ("mercury thermometer", "hazardous"),
    ("broken thermometer", "hazardous"), ("mobile phone", "hazardous"),
    ("phone charger", "hazardous"), ("earphones", "hazardous"), ("laptop", "hazardous"),
    ("computer keyboard", "hazardous"), ("nail polish", "hazardous"), ("hair dye", "hazardous"),
    ("toilet acid bottle", "hazardous"), ("used engine oil", "hazardous"),
    ("razor blade", "hazardous"), ("electric wires", "hazardous"), ("printer cartridge", "hazardous"),
    ("பேட்டரி", "hazardous"), ("பழைய பேட்டரி", "hazardous"), ("டியூப் லைட்", "hazardous"),
    ("சிஎஃப்எல் பல்பு", "hazardous"), ("எல்இடி பல்பு", "hazardous"),
    ("காலாவதியான மருந்து", "hazardous"), ("பழைய மாத்திரைகள்", "hazardous"),
    ("ஊசி", "hazardous"), ("சிரிஞ்ச்", "hazardous"), ("பெயிண்ட் டப்பா", "hazardous"),
    ("பூச்சிக்கொல்லி பாட்டில்", "hazardous"), ("கொசு மருந்து ஸ்ப்ரே", "hazardous"),
    ("தெர்மாமீட்டர்", "hazardous"), ("கைபேசி", "hazardous"), ("பழைய மொபைல் போன்", "hazardous"),
    ("சார்ஜர்", "hazardous"), ("இயர்போன்", "hazardous"), ("ஆசிட் பாட்டில்", "hazardous"),
    ("இன்ஜின் ஆயில்", "hazardous"), ("பிளேடு", "hazardous"),
    ("pazhaya battery", "hazardous"), ("marundhu", "hazardous"), ("tube light udainjadhu", "hazardous"),
]

# Material / category keywords: always part of training (a tiny knowledge base that lets the
# model generalise to item names it has never seen, e.g. "rotten tomato" -> rotten -> wet).
LEXICON = [
    ("food", "wet"), ("rice", "wet"), ("sambar", "wet"), ("curry", "wet"), ("vegetable", "wet"),
    ("fruit", "wet"), ("peel", "wet"), ("leaf", "wet"), ("leaves", "wet"), ("flower", "wet"),
    ("bone", "wet"), ("meat", "wet"), ("fish", "wet"), ("egg", "wet"), ("seed", "wet"),
    ("husk", "wet"), ("garden", "wet"), ("kitchen", "wet"), ("cooked", "wet"), ("rotten", "wet"),
    ("stale", "wet"), ("tea", "wet"), ("coffee", "wet"), ("dung", "wet"), ("compost", "wet"),
    ("உணவு", "wet"), ("சாதம்", "wet"), ("சாப்பாடு", "wet"), ("காய்கறி", "wet"), ("பழம்", "wet"),
    ("தோல்", "wet"), ("இலை", "wet"), ("பூ", "wet"), ("எலும்பு", "wet"), ("மீன்", "wet"),
    ("இறைச்சி", "wet"), ("கொட்டை", "wet"),
    ("wrapper", "dry"), ("sachet", "dry"), ("sanitary", "dry"), ("diaper", "dry"), ("pad", "dry"),
    ("cloth", "dry"), ("rubber", "dry"), ("ceramic", "dry"), ("thermocol", "dry"), ("dust", "dry"),
    ("tissue", "dry"), ("multilayer", "dry"), ("cigarette", "dry"), ("mask", "dry"),
    ("sponge", "dry"), ("foam", "dry"), ("துணி", "dry"), ("செருப்பு", "dry"), ("தூசி", "dry"),
    ("ரப்பர்", "dry"), ("பீங்கான்", "dry"),
    ("plastic", "recyclable"), ("bottle", "recyclable"), ("glass", "recyclable"),
    ("metal", "recyclable"), ("steel", "recyclable"), ("iron", "recyclable"),
    ("aluminium", "recyclable"), ("tin", "recyclable"), ("can", "recyclable"),
    ("paper", "recyclable"), ("cardboard", "recyclable"), ("carton", "recyclable"),
    ("book", "recyclable"), ("container", "recyclable"), ("jar", "recyclable"),
    ("scrap", "recyclable"), ("copper", "recyclable"), ("brass", "recyclable"),
    ("பிளாஸ்டிக்", "recyclable"), ("பாட்டில்", "recyclable"), ("கண்ணாடி", "recyclable"),
    ("இரும்பு", "recyclable"), ("காகிதம்", "recyclable"), ("புத்தகம்", "recyclable"),
    ("டப்பா", "recyclable"), ("பாத்திரம்", "recyclable"),
    ("battery", "hazardous"), ("bulb", "hazardous"), ("medicine", "hazardous"),
    ("tablet", "hazardous"), ("capsule", "hazardous"), ("syringe", "hazardous"),
    ("needle", "hazardous"), ("chemical", "hazardous"), ("acid", "hazardous"),
    ("paint", "hazardous"), ("pesticide", "hazardous"), ("insecticide", "hazardous"),
    ("mercury", "hazardous"), ("electronic", "hazardous"), ("e-waste", "hazardous"),
    ("charger", "hazardous"), ("phone", "hazardous"), ("wire", "hazardous"),
    ("cartridge", "hazardous"), ("blade", "hazardous"), ("dye", "hazardous"),
    ("மருந்து", "hazardous"), ("மாத்திரை", "hazardous"), ("பேட்டரி", "hazardous"),
    ("பல்பு", "hazardous"), ("ஊசி", "hazardous"), ("ரசாயனம்", "hazardous"),
    ("மின்னணு", "hazardous"),
]

_SPLIT = re.compile(r"[\s,.;:!?()\[\]{}\"'/\\|+\-_*&%#@~`^=<>]+")


def normalise(text):
    return " ".join(t for t in _SPLIT.split((text or "").strip().lower()) if t)


def _stem(w):
    if w.isascii() and len(w) > 3:
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith("es") and w[-3] in "sxhz":
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
    return w


def words(text):
    return [_stem(w) for w in normalise(text).split(" ") if w]


def features(text):
    """[(feature, source_word)] - word features plus char 3-grams of each word."""
    out = []
    for w in words(text):
        out.append(("w:" + w, w))
        padded = "<" + w + ">"
        for i in range(len(padded) - 2):
            out.append(("c:" + padded[i:i + 3], w))
    return out


class NaiveBayes:
    def __init__(self, alpha=0.5):
        self.alpha = alpha
        self.labels = LABELS
        self.vocab = set()
        self.count = {c: {} for c in LABELS}
        self.total = {c: 0 for c in LABELS}
        self.docs = {c: 0 for c in LABELS}
        self.exact = {}

    def fit(self, data):
        for text, label in data:
            self.docs[label] += 1
            self.exact[normalise(text)] = label
            for f, _ in features(text):
                self.vocab.add(f)
                self.count[label][f] = self.count[label].get(f, 0) + 1
                self.total[label] += 1
        return self

    def _logp(self, f, c):
        V = len(self.vocab) + 1
        return math.log((self.count[c].get(f, 0) + self.alpha) / (self.total[c] + self.alpha * V))

    def scores(self, text):
        n = sum(self.docs.values())
        feats = features(text)
        s = {c: math.log(self.docs[c] / n) for c in self.labels}
        for f, _ in feats:
            if f in self.vocab:
                for c in self.labels:
                    s[c] += self._logp(f, c)
        return s, feats

    def predict(self, text):
        s, _ = self.scores(text)
        return max(self.labels, key=lambda c: s[c])

    def explain(self, text):
        norm = normalise(text)
        s, feats = self.scores(text)
        # Char n-grams of one word are strongly correlated, so raw NB is over-confident;
        # temper the log-scores by the number of features before turning them into a %.
        temp = max(1.0, len(feats) / 5.0)
        m = max(s.values())
        exp = {c: math.exp((v - m) / temp) for c, v in s.items()}
        z = sum(exp.values())
        probs = {c: exp[c] / z for c in self.labels}
        ranked = sorted(self.labels, key=lambda c: -probs[c])
        best, runner = ranked[0], ranked[1]
        known = [f for f, _ in feats if f in self.vocab]
        coverage = len(known) / len(feats) if feats else 0.0
        contrib = {}
        for f, w in feats:
            if f in self.vocab:
                contrib[w] = contrib.get(w, 0.0) + self._logp(f, best) - self._logp(f, runner)
        evidence = sorted(({"word": w, "weight": round(v, 2)} for w, v in contrib.items()),
                          key=lambda e: -e["weight"])
        method = "naive-bayes"
        label = best
        confidence = probs[best]
        if norm in self.exact:
            method = "exact-match"
            label = self.exact[norm]
            confidence = max(confidence, 0.99) if label == best else 0.95
        unsure = method != "exact-match" and (coverage < 0.35 or confidence < 0.5)
        info = BIN_INFO[label]
        if method == "exact-match":
            why = "Exact match in the item dictionary (%d known names)." % len(self.exact)
        elif evidence and evidence[0]["weight"] > 0:
            top = ", ".join("'%s'" % e["word"] for e in evidence[:2] if e["weight"] > 0)
            why = "Naive Bayes: %s points to %s over %s." % (top, label.upper(), runner)
        else:
            why = "Naive Bayes: weak evidence; closest class is %s." % label
        return {
            "item": text, "normalised": norm, "label": label, "bin": info["bin"],
            "bin_ta": info["ta"], "color": info["color"], "tip": info["tip"],
            "confidence": round(confidence, 3), "method": method, "unsure": unsure,
            "probabilities": {c: round(probs[c], 3) for c in ranked},
            "evidence": evidence[:4], "coverage": round(coverage, 2), "why": why,
            "runner_up": runner,
        }


def holdout_split(data=None, every=5):
    """Every 5th item name is held out; the keyword lexicon is always in training."""
    data = data or DATA
    train = list(LEXICON) + [d for i, d in enumerate(data) if i % every != 0]
    test = [d for i, d in enumerate(data) if i % every == 0]
    return train, test


def evaluate(data=None):
    """Hold-out accuracy of the NB model alone on item names it has never seen."""
    train, test = holdout_split(data)
    nb = NaiveBayes().fit(train)
    correct = sum(1 for t, y in test if nb.predict(t) == y)
    per = {c: [0, 0] for c in LABELS}
    for t, y in test:
        per[y][1] += 1
        if nb.predict(t) == y:
            per[y][0] += 1
    return {"train": len(train), "test": len(test), "accuracy": round(correct / len(test), 4),
            "per_class": {c: {"correct": a, "total": b} for c, (a, b) in per.items()}}


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = NaiveBayes().fit(list(LEXICON) + DATA)
    return _MODEL


def classify(text):
    return model().explain(text)
