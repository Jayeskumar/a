"""PhishGuard engine: trains the models and produces explainable verdicts.

Combined risk (noisy-OR, each signal can independently raise the alarm):

    risk = 1 - (1 - W_TEXT * p_text) * prod_r (1 - w_r) * (1 - W_URL * p_url) * (1 - W_ENTITY * p_entity)

    p_text   = sigmoid(NB log-odds / NB_TEMPERATURE + log(prior / (1 - prior)))
    w_r      = weight of every rule that fired
    p_url    = highest logistic-regression probability among embedded links
    p_entity = highest heuristic score among phone numbers / UPI IDs
"""
import math
import re
import time

from . import config, corpus, rules as rules_mod, text as text_mod, urlfeatures
from .entities import score_phone, score_upi
from .extract import extract_all, URL_RE
from .logreg import LogisticRegression, sigmoid
from .metrics import report
from .naive_bayes import MultinomialNB

SINGLE_URL_RE = re.compile(r"^\S+$")


def combine(values):
    """Noisy-OR of values in [0, 1]."""
    keep = 1.0
    for v in values:
        keep *= 1.0 - min(max(v, 0.0), 1.0)
    return 1.0 - keep


PRIOR_SHIFT = math.log(config.NB_DEPLOY_PRIOR / (1.0 - config.NB_DEPLOY_PRIOR))


def calibrate(log_odds):
    """Temperature-scaled NB log-odds with the balanced training prior replaced
    by the deployment prior: p = sigmoid(log_odds / T + log(pi / (1 - pi)))."""
    return sigmoid(log_odds / config.NB_TEMPERATURE + PRIOR_SHIFT)


def verdict(risk):
    if risk >= config.DANGEROUS_FROM:
        return "Dangerous"
    if risk >= config.SAFE_BELOW:
        return "Suspicious"
    return "Safe"


def looks_like_single_url(s):
    s = s.strip()
    if not s or not SINGLE_URL_RE.match(s):
        return False
    m = URL_RE.match(s)
    return bool(m and m.end() >= len(s.rstrip(".,;:!?")))


def train_nb(items):
    nb = MultinomialNB(alpha=config.NB_ALPHA)
    nb.fit([text_mod.features(it["text"]) for it in items], [it["label"] for it in items])
    return nb


def train_lr(items):
    X = [urlfeatures.extract(it["url"])[0] for it in items]
    y = [it["label"] for it in items]
    lr = LogisticRegression(config.LR_LEARNING_RATE, config.LR_EPOCHS, config.LR_L2)
    return lr.fit(X, y)


class PhishGuard:
    def __init__(self, messages=None, urls=None):
        t0 = time.perf_counter()
        self.messages = messages if messages is not None else corpus.generate_messages()
        self.urls = urls if urls is not None else corpus.generate_urls()
        self.msg_train, self.msg_test = corpus.split(self.messages)
        self.url_train, self.url_test = corpus.split(self.urls)
        self.nb = train_nb(self.msg_train)
        self.lr = train_lr(self.url_train)
        self.train_seconds = time.perf_counter() - t0
        self._stats = None

    # ------------------------------------------------------------ URL model
    def score_url(self, url):
        x, info = urlfeatures.extract(url)
        p = self.lr.predict_proba(x)
        contribs = self.lr.contributions(x, urlfeatures.FEATURE_NAMES)
        reasons = [{
            "feature": n, "label": urlfeatures.FEATURE_LABELS[n], "value": round(v, 3),
            "weight": round(w, 3), "contribution": round(c, 3),
        } for n, v, w, c in contribs if abs(c) >= 0.05]
        risk = int(round(p * config.W_URL * 100))
        return {"url": url, "probability": round(p, 4), "risk": risk,
                "verdict": verdict(risk), "reasons": reasons[:8], "info": info,
                "bias": round(self.lr.bias, 3)}

    # -------------------------------------------------------- text model
    def _text_explain(self, feats, nb):
        rows = nb.contributions(feats)
        words, chars = [], 0.0
        for f, n, r, c in rows:
            kind, _, val = f.partition(":")
            if kind == "c":
                chars += c
            elif not (kind == "w" and val in text_mod.PLACEHOLDERS and abs(c) < 0.3):
                words.append({"feature": f, "kind": "word" if kind == "w" else "phrase", "token": val,
                              "display": display_token(val), "count": round(n, 2), "llr": round(r, 3),
                              "contribution": round(c, 3)})
        words.sort(key=lambda d: -d["contribution"])
        scam = [w for w in words if w["contribution"] > 0][:10]
        ham = sorted([w for w in words if w["contribution"] < 0], key=lambda d: d["contribution"])[:6]
        return scam, ham, round(chars, 3)

    def _score(self, text, nb, explain=True):
        feats = text_mod.features(text)
        log_odds = nb.log_odds(feats)
        p_text = calibrate(log_odds)
        fired = rules_mod.evaluate(text)
        s_rules = rules_mod.rule_score(fired)
        ents = extract_all(text)
        urls = [dict(self.score_url(u["value"]), start=u["start"], end=u["end"]) for u in ents["urls"]] if ents["urls"] else []
        phones, upis = [], []
        for ph in ents["phones"]:
            s, why = score_phone(ph, text)
            phones.append({"value": ph["value"], "score": s, "reason": why, "start": ph["start"], "end": ph["end"]})
        for u in ents["upi"]:
            s, why = score_upi(u, text)
            upis.append({"value": u["value"], "score": s, "reason": why, "start": u["start"], "end": u["end"]})
        p_url = max([u["probability"] for u in urls], default=0.0)
        p_ent = max([e["score"] for e in phones + upis], default=0.0)
        components = [
            {"key": "text", "label": "Text model (Naive Bayes)", "raw": p_text, "weight": config.W_TEXT},
            {"key": "rules", "label": "Scam-pattern rules", "raw": s_rules, "weight": 1.0},
            {"key": "links", "label": "Link model (log. regression)", "raw": p_url, "weight": config.W_URL},
            {"key": "entities", "label": "Phone / UPI heuristics", "raw": p_ent, "weight": config.W_ENTITY},
        ]
        for c in components:
            c["value"] = c["raw"] * c["weight"]
        risk = combine([c["value"] for c in components]) * 100
        if not explain:
            return risk
        scam_tokens, ham_tokens, char_total = self._text_explain(feats, nb)
        return {
            "risk": risk, "p_text": p_text, "log_odds": log_odds, "fired": fired, "urls": urls,
            "phones": phones, "upi": upis, "components": components,
            "scam_tokens": scam_tokens, "ham_tokens": ham_tokens, "char_total": char_total,
        }

    def risk_only(self, text, nb=None):
        return self._score(text, nb or self.nb, explain=False)

    # ------------------------------------------------------------ public
    def analyse(self, text, kind="auto"):
        t0 = time.perf_counter()
        text = (text or "")[: config.MAX_INPUT_CHARS]
        if kind == "url" or (kind == "auto" and looks_like_single_url(text)):
            out = self._analyse_url(text.strip())
        else:
            out = self._analyse_message(text)
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        out["privacy"] = "Analysed locally on this device. Nothing was sent anywhere."
        return out

    def _analyse_message(self, text):
        r = self._score(text, self.nb)
        risk = min(int(round(r["risk"])), 99)  # never claim 100% certainty
        v = verdict(risk)
        total = sum(c["value"] for c in r["components"]) or 1.0
        comps = [{"key": c["key"], "label": c["label"], "raw": round(c["raw"], 4), "weight": c["weight"],
                  "value": round(c["value"], 4), "share": round(c["value"] / total, 4)} for c in r["components"]]
        spans = []
        for rule in r["fired"]:
            for h in rule["matches"]:
                spans.append((0, h["start"], h["end"], "rule", rule["title"]))
        for u in r["urls"]:
            spans.append((1, u["start"], u["end"], "url", "Link - {} ({}%)".format(u["verdict"], u["risk"])))
        for e in r["phones"]:
            spans.append((1, e["start"], e["end"], "phone", "Phone - risk {}%".format(int(e["score"] * 100))))
        for e in r["upi"]:
            spans.append((1, e["start"], e["end"], "upi", "UPI ID - risk {}%".format(int(e["score"] * 100))))
        for tok in r["scam_tokens"][:8]:
            for s, e in _token_spans(text, tok["token"]):
                spans.append((2, s, e, "token", "Scam word (LLR +{:.2f})".format(tok["llr"])))
        for tok in r["ham_tokens"][:4]:
            for s, e in _token_spans(text, tok["token"]):
                spans.append((3, s, e, "safe", "Safe word (LLR {:.2f})".format(tok["llr"])))
        return {
            "mode": "message", "risk": risk, "verdict": v, "components": comps,
            "nb": {"probability": round(r["p_text"], 4), "posterior": round(sigmoid(r["log_odds"]), 6),
                   "log_odds": round(r["log_odds"], 3), "temperature": config.NB_TEMPERATURE,
                   "deploy_prior": config.NB_DEPLOY_PRIOR,
                   "char_ngram_total": r["char_total"], "scam_tokens": r["scam_tokens"], "ham_tokens": r["ham_tokens"]},
            "rules": [_rule_out(rule) for rule in r["fired"]],
            "entities": {"urls": r["urls"], "phones": r["phones"], "upi": r["upi"]},
            "segments": build_segments(text, spans),
            "advice": advice(v, r["fired"], r["urls"], r["phones"] + r["upi"]),
        }

    def _analyse_url(self, url):
        s = self.score_url(url)
        risk = s["risk"]
        v = verdict(risk)
        fired = rules_mod.evaluate(url)
        return {
            "mode": "url", "risk": risk, "verdict": v,
            "components": [{"key": "links", "label": "Link model (log. regression)", "raw": s["probability"],
                            "weight": config.W_URL, "value": round(s["probability"] * config.W_URL, 4), "share": 1.0}],
            "nb": None, "rules": [_rule_out(f) for f in fired],
            "entities": {"urls": [dict(s, start=0, end=len(url))], "phones": [], "upi": []},
            "segments": build_segments(url, [(1, 0, len(url), "url", "Link - {} ({}%)".format(v, risk))]),
            "advice": advice(v, [], [s], []),
        }

    def bulk(self, lines):
        rows = []
        for i, line in enumerate(lines[: config.MAX_BULK_LINES]):
            line = line.strip()
            if not line:
                continue
            a = self.analyse(line)
            reason = ""
            if a["rules"]:
                reason = a["rules"][0]["title"]
            elif a["mode"] == "url":
                rs = a["entities"]["urls"][0]["reasons"]
                if a["verdict"] == "Safe":
                    good = [x for x in rs if x["contribution"] < 0]
                    reason = "Normal-looking link" + (": " + good[0]["label"].lower() if good else "")
                else:
                    bad = [x for x in rs if x["contribution"] > 0]
                    reason = bad[0]["label"] if bad else "Unusual link"
            elif a["entities"]["urls"] and max(u["risk"] for u in a["entities"]["urls"]) >= config.SAFE_BELOW:
                reason = "Risky link inside"
            elif a.get("nb") and a["nb"]["scam_tokens"] and a["verdict"] != "Safe":
                reason = "Scam-like wording: " + ", ".join(t["display"] for t in a["nb"]["scam_tokens"][:3])
            else:
                reason = "No scam signals"
            rows.append({"line": i + 1, "text": line, "risk": a["risk"], "verdict": a["verdict"],
                         "mode": a["mode"], "reason": reason, "latency_ms": a["latency_ms"]})
        summary = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("Safe", "Suspicious", "Dangerous")}
        return {"rows": rows, "summary": summary, "count": len(rows)}

    # ------------------------------------------------------------ stats
    def stats(self):
        if self._stats is None:
            self._stats = self._compute_stats()
        return self._stats

    def _compute_stats(self):
        yt = [it["label"] for it in self.msg_test]
        nb_pred = [self.nb.predict(text_mod.features(it["text"])) for it in self.msg_test]
        t0 = time.perf_counter()
        risks = [self.risk_only(it["text"]) for it in self.msg_test]
        msg_latency = (time.perf_counter() - t0) * 1000 / max(len(self.msg_test), 1)
        comb_pred = [1 if r >= config.SAFE_BELOW else 0 for r in risks]
        danger_pred = [1 if r >= config.DANGEROUS_FROM else 0 for r in risks]
        rule_pred = [1 if rules_mod.rule_score(rules_mod.evaluate(it["text"])) >= 0.35 else 0 for it in self.msg_test]

        uy = [it["label"] for it in self.url_test]
        t0 = time.perf_counter()
        up = [self.lr.predict(urlfeatures.extract(it["url"])[0]) for it in self.url_test]
        url_latency = (time.perf_counter() - t0) * 1000 / max(len(self.url_test), 1)

        # Harder check: whole templates never seen in training.
        ht_train, ht_test = corpus.template_split(self.messages)
        nb_ht = train_nb(ht_train)
        ht_y = [it["label"] for it in ht_test]
        ht_nb = [nb_ht.predict(text_mod.features(it["text"])) for it in ht_test]
        ht_comb = [1 if self.risk_only(it["text"], nb_ht) >= config.SAFE_BELOW else 0 for it in ht_test]

        top = self.nb.top_features(k=40, min_count=4)

        def readable(rows):
            out = []
            for f, r in rows:
                kind, _, val = f.partition(":")
                if kind in ("w", "b"):
                    out.append({"token": display_token(val), "kind": "word" if kind == "w" else "phrase", "llr": round(r, 3)})
            return out[:14]

        weights = sorted(({"feature": n, "label": urlfeatures.FEATURE_LABELS[n], "weight": round(w, 3)}
                          for n, w in zip(urlfeatures.FEATURE_NAMES, self.lr.weights)), key=lambda d: -d["weight"])
        return {
            "dataset": {
                "messages": len(self.messages), "messages_train": len(self.msg_train), "messages_test": len(self.msg_test),
                "scam_messages": sum(it["label"] for it in self.messages),
                "urls": len(self.urls), "urls_train": len(self.url_train), "urls_test": len(self.url_test),
                "phishing_urls": sum(it["label"] for it in self.urls),
                "scam_templates": len(corpus.SCAM_TEMPLATES), "ham_templates": len(corpus.HAM_TEMPLATES),
                "nb_vocabulary": len(self.nb.vocab), "url_features": len(urlfeatures.FEATURE_NAMES),
                "rules": len(rules_mod.RULES),
            },
            "message_nb": report(yt, nb_pred),
            "message_rules_only": report(yt, rule_pred),
            "message_combined": report(yt, comb_pred),
            "message_combined_dangerous": report(yt, danger_pred),
            "url_lr": report(uy, up),
            "heldout_templates": {
                "train": len(ht_train), "test": len(ht_test),
                "nb": report(ht_y, ht_nb), "combined": report(ht_y, ht_comb),
            },
            "latency_ms": {"message": round(msg_latency, 3), "url": round(url_latency, 3)},
            "train_seconds": round(self.train_seconds, 3),
            "top_tokens": {"scam": readable(top["scam"]), "ham": readable(top["ham"])},
            "lr_weights": weights, "lr_bias": round(self.lr.bias, 3),
            "lr_loss": [round(x, 4) for x in self.lr.loss_history],
            "config": {"nb_alpha": config.NB_ALPHA, "nb_temperature": config.NB_TEMPERATURE, "nb_deploy_prior": config.NB_DEPLOY_PRIOR,
                       "char_ngrams": [config.CHAR_NGRAM_MIN, config.CHAR_NGRAM_MAX],
                       "w_text": config.W_TEXT, "w_url": config.W_URL, "w_entity": config.W_ENTITY,
                       "safe_below": config.SAFE_BELOW, "dangerous_from": config.DANGEROUS_FROM,
                       "lr_epochs": config.LR_EPOCHS, "lr_learning_rate": config.LR_LEARNING_RATE, "lr_l2": config.LR_L2},
            "note": "Synthetic, template-generated data: these numbers overestimate real-world performance.",
        }


PLACEHOLDER_NAMES = {"__url__": "<link>", "__email__": "<email>", "__upi__": "<upi-id>",
                     "__phone__": "<phone>", "__money__": "<amount>", "__num__": "<number>"}


def display_token(tok):
    for k, v in PLACEHOLDER_NAMES.items():
        tok = tok.replace(k, v)
    return tok


def _rule_out(rule):
    return {"id": rule["id"], "title": rule["title"], "category": rule["category"], "weight": rule["weight"],
            "advice": rule["advice"], "matches": [h["text"] for h in rule["matches"]]}


def _token_spans(text, token):
    if token.startswith("__"):
        return []
    parts = [re.escape(p) for p in token.split()]
    pat = r"(?<![^\W\d_])" + r"[\W\d_]+".join(parts) + r"(?![^\W\d_])"
    return [(m.start(), m.end()) for m in re.finditer(pat, text, re.IGNORECASE)][:3]


def build_segments(text, spans):
    """Turn possibly-overlapping spans into a flat list of non-overlapping segments.

    ``spans`` is a list of (priority, start, end, kind, label); lower priority
    numbers win where spans overlap.
    """
    owner = [None] * len(text)
    for pri, s, e, kind, label in sorted(spans, key=lambda t: (t[0], t[1])):
        for i in range(max(s, 0), min(e, len(text))):
            if owner[i] is None:
                owner[i] = (kind, label)
    segs = []
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and owner[j] == owner[i]:
            j += 1
        seg = {"text": text[i:j]}
        if owner[i]:
            seg["kind"], seg["label"] = owner[i]
        segs.append(seg)
        i = j
    return segs


GENERAL_ADVICE = {
    "Dangerous": [
        "Do not click links, call back numbers, or pay anyone mentioned in this message.",
        "If you already paid or shared an OTP/PIN: call {} immediately and report at {}.".format(config.HELPLINE, config.PORTAL),
        "Report the sender on {} and block the number.".format(config.CHAKSHU),
    ],
    "Suspicious": [
        "Verify through an official channel you look up yourself (bank app, printed helpline), not the contact in the message.",
        "Never share OTP, UPI PIN, CVV or passwords. No genuine organisation asks for them.",
        "Lost money? Call {} (national cyber-fraud helpline) or report at {}.".format(config.HELPLINE, config.PORTAL),
    ],
    "Safe": [
        "No strong scam signals found - but stay alert: never share OTP or UPI PIN, even with 'bank staff'.",
        "In doubt? Ask a family member or call {} before acting.".format(config.HELPLINE),
    ],
}


def advice(v, fired, urls, entities):
    out = list(GENERAL_ADVICE[v])
    seen = set()
    for r in fired:
        if r["advice"] not in seen:
            seen.add(r["advice"])
            out.append(r["advice"])
    if any(u["risk"] >= config.DANGEROUS_FROM for u in urls):
        out.append("The link looks like phishing. Type the official website address yourself instead of tapping the link.")
    if v != "Safe" and any(e.get("score", 0) >= 0.5 for e in entities):
        out.append("The phone number / UPI ID in this message is not an official channel. Do not call or pay it.")
    return out[:7]
