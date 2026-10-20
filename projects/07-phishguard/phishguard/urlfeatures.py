"""Lexical URL features (no network lookups) for the phishing-link model.

Every feature is scaled into [0, 1] so logistic-regression weights are
comparable and each contribution can be shown to the user.
"""
import ipaddress
import math
import re
from collections import Counter
from urllib.parse import urlsplit

# Second-level suffixes where the registrable domain has three labels.
MULTI_SUFFIXES = {
    "co.in", "gov.in", "nic.in", "ac.in", "edu.in", "org.in", "net.in", "res.in",
    "bank.in", "firm.in", "gen.in", "ind.in", "co.uk", "org.uk", "ac.uk", "com.au",
}
# Registry-restricted Indian zones (only verified entities can register).
RESTRICTED_SUFFIXES = ("gov.in", "nic.in", "ac.in", "edu.in", "res.in", "bank.in")

# TLDs that are cheap/free and over-represented in phishing feeds.
SUSPICIOUS_TLDS = {
    "xyz", "top", "club", "online", "site", "live", "icu", "buzz", "click", "link",
    "tk", "ml", "ga", "cf", "gq", "win", "loan", "work", "rest", "monster", "support",
    "help", "cyou", "sbs", "cfd", "bond", "vip", "shop",
}

SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "rb.gy", "t.ly", "shorturl.at",
    "tiny.cc", "goo.gl", "ow.ly", "s.id", "v.gd", "shorte.st", "bitly.com", "t.co",
}

# Brand keyword -> official registrable domains.
BRANDS = {
    "sbi": ["sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "sbicard.com"],
    "yono": ["onlinesbi.sbi", "sbi.co.in"],
    "hdfc": ["hdfcbank.com", "hdfc.com", "hdfcbank.bank.in"],
    "icici": ["icicibank.com", "icici.bank.in"],
    "axis": ["axisbank.com", "axis.bank.in"],
    "kotak": ["kotak.com", "kotak.bank.in"],
    "canara": ["canarabank.com", "canarabank.bank.in"],
    "paytm": ["paytm.com", "paytmbank.com"],
    "phonepe": ["phonepe.com"],
    "gpay": ["google.com"],
    "bhim": ["npci.org.in", "bhimupi.org.in"],
    "npci": ["npci.org.in"],
    "amazon": ["amazon.in", "amazon.com", "amzn.in", "amzn.to"],
    "flipkart": ["flipkart.com"],
    "myntra": ["myntra.com"],
    "meesho": ["meesho.com"],
    "irctc": ["irctc.co.in"],
    "airtel": ["airtel.in"],
    "jio": ["jio.com", "jiomart.com"],
    "bsnl": ["bsnl.co.in"],
    "uidai": ["uidai.gov.in"],
    "aadhaar": ["uidai.gov.in"],
    "incometax": ["incometax.gov.in"],
    "epfo": ["epfindia.gov.in"],
    "indiapost": ["indiapost.gov.in"],
    "netflix": ["netflix.com"],
    "whatsapp": ["whatsapp.com"],
    "google": ["google.com", "google.co.in"],
    "apple": ["apple.com"],
    "microsoft": ["microsoft.com"],
    "swiggy": ["swiggy.com"],
    "zomato": ["zomato.com"],
    "tneb": ["tnebltd.gov.in", "tangedco.gov.in"],
}
OFFICIAL_DOMAINS = {d for ds in BRANDS.values() for d in ds} | {
    "youtube.com", "youtu.be", "wikipedia.org", "github.com", "linkedin.com",
    "python.org", "gmail.com", "forms.gle",
}

PATH_KEYWORDS = [
    "login", "signin", "verify", "verification", "kyc", "update", "secure", "account",
    "banking", "confirm", "wallet", "reward", "bonus", "claim", "refund", "otp", "unlock",
    "suspend", "blocked", "reactivate", "validate", "prize", "gift", "free", "lucky",
    "payment", "billpay", "pay",
]
GOV_WORDS = ["gov", "govt", "nic", "sarkari", "yojana", "pmkisan", "kisan", "scheme", "subsidy"]

HOMOGLYPHS = [("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("3", "e"),
              ("4", "a"), ("5", "s"), ("7", "t"), ("8", "b"), ("@", "a")]

FEATURES = [
    # name, human description shown in the explanation panel
    ("url_length", "Long URL"),
    ("host_length", "Long host name"),
    ("host_dots", "Many dots in host"),
    ("subdomains", "Many sub-domains"),
    ("digit_ratio", "Lots of digits"),
    ("has_at", "'@' trick (text before @ is ignored by the browser)"),
    ("ip_host", "Raw IP address instead of a domain"),
    ("punycode", "Punycode 'xn--' (possible homoglyph domain)"),
    ("non_ascii", "Non-ASCII look-alike characters"),
    ("lookalike_brand", "Look-alike spelling of a brand (e.g. amaz0n, paytrn)"),
    ("brand_in_host_unofficial", "Brand name in host, but not the brand's official domain"),
    ("brand_in_path_unofficial", "Brand name in path, on a non-official domain"),
    ("official_domain", "Known official domain"),
    ("restricted_tld", "Registry-restricted zone (.gov.in / .ac.in / .bank.in)"),
    ("suspicious_tld", "Cheap TLD common in phishing (.xyz, .top, ...)"),
    ("shortener", "URL shortener hides the real destination"),
    ("host_entropy", "Random-looking host name (high entropy)"),
    ("host_hyphens", "Hyphens in host"),
    ("https", "Uses HTTPS"),
    ("explicit_http", "Plain HTTP (not encrypted)"),
    ("path_keywords", "Phishing words in path (login/verify/kyc/...)"),
    ("path_depth", "Deep path"),
    ("query_params", "Many query parameters"),
    ("has_port", "Non-standard port"),
    ("redirect_slash", "Embedded '//' redirect"),
    ("apk_exe", "Direct app download (.apk / .exe)"),
    ("gov_lookalike", "Government words outside a .gov.in domain"),
    ("random_token", "Long random token in path"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
FEATURE_LABELS = dict(FEATURES)


def parse(url):
    raw = url.strip()
    scheme_given = bool(re.match(r"^[a-z][a-z0-9+.\-]*://", raw, re.IGNORECASE))
    to_parse = raw if scheme_given else "http://" + raw
    try:
        parts = urlsplit(to_parse)
        netloc = parts.netloc
        path = parts.path or ""
        query = parts.query or ""
        scheme = parts.scheme.lower() if scheme_given else ""
    except ValueError:
        netloc, path, query, scheme = raw, "", "", ""
    userinfo = ""
    if "@" in netloc:
        userinfo, _, netloc = netloc.rpartition("@")
    host, port = netloc, ""
    if host.startswith("["):
        host = host.strip("[]")
    elif ":" in host:
        host, _, port = host.rpartition(":")
    host = host.lower().rstrip(".")
    return {
        "raw": raw, "scheme": scheme, "userinfo": userinfo, "host": host,
        "port": port, "path": path, "query": query,
    }


def registered_domain(host):
    labels = [l for l in host.split(".") if l]
    if len(labels) >= 3 and ".".join(labels[-2:]) in MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def shannon_entropy(s):
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def deglyph(s):
    for a, b in HOMOGLYPHS:
        s = s.replace(a, b)
    return s


def _official_for(brand, reg):
    return reg in BRANDS.get(brand, ())


# Real words that sit one edit away from a brand name.
NOT_LOOKALIKES = {"apply", "apples", "maple", "ample", "amazing", "axiss"}


def lookalike_brand(host, reg):
    """Return the brand a host label imitates, or ''."""
    if reg in OFFICIAL_DOMAINS:
        return ""
    for label in re.split(r"[.\-]", host):
        if len(label) < 4 or label in NOT_LOOKALIKES:
            continue
        clean = deglyph(label)
        for brand in BRANDS:
            if len(brand) < 5 and clean != brand:
                continue
            if label == brand:
                continue  # exact brand word handled by brand_in_host
            if clean == brand or (len(brand) >= 5 and edit_distance(label, brand) == 1):
                return brand
    return ""


def brands_in(text):
    t = text.lower()
    return [b for b in BRANDS if b in t]


def extract(url):
    """Return (feature_vector, info) for a URL string."""
    p = parse(url)
    host, path, query = p["host"], p["path"], p["query"]
    ip = is_ip(host)
    reg = host if ip else (registered_domain(host) if host else "")
    labels = host.split(".") if host else []
    tld = labels[-1] if labels and not ip else ""
    sub_part = host[: -len(reg)].rstrip(".") if reg and host.endswith(reg) else ""
    n_sub = len([l for l in sub_part.split(".") if l and l != "www"])
    full = p["raw"]
    host_path = host + path

    official = (reg in OFFICIAL_DOMAINS) and not ip
    restricted = any(host == s or host.endswith("." + s) for s in RESTRICTED_SUFFIXES) and not ip

    # text before an '@' is what a victim reads as the host, so it counts too
    brands_host = ([b for b in brands_in(p["userinfo"] + "." + host) if not _official_for(b, reg)]
                   if not official else [])
    brands_path = [b for b in brands_in(path + "?" + query) if not _official_for(b, reg)] if not official else []
    look = lookalike_brand(host, reg) if not ip else ""

    path_l = (path + "?" + query).lower()
    kw_hits = [k for k in PATH_KEYWORDS if k in path_l]
    # 'pay' is a substring of 'payment'/'billpay' – count distinct roots only
    kw_hits = [k for k in kw_hits if not any(k != o and k in o for o in kw_hits)]
    depth = len([s for s in path.split("/") if s])
    n_params = len([q for q in query.split("&") if q]) if query else 0
    host_chars = host.replace(".", "")
    entropy = shannon_entropy(host_chars) if not ip else 0.0
    host_tokens = set(re.split(r"[.\-]", host))
    gov_hits = ([g for g in GOV_WORDS if (g in host_tokens if len(g) <= 4 else g in host)]
                if not restricted else [])
    rand_tok = any(len(t) >= 14 and re.search(r"\d", t) and re.search(r"[a-z]", t, re.I)
                   for t in re.split(r"[/?&=._\-]", path + "?" + query))

    vec = {
        "url_length": min(len(full) / 120.0, 1.0),
        "host_length": min(len(host) / 40.0, 1.0),
        "host_dots": 0.0 if ip else min(host.count(".") / 5.0, 1.0),
        "subdomains": min(n_sub / 3.0, 1.0),
        "digit_ratio": min(sum(ch.isdigit() for ch in (path if ip else host_path)) / max(len(host_path), 1) * 3, 1.0),
        "has_at": 1.0 if p["userinfo"] else 0.0,
        "ip_host": 1.0 if ip else 0.0,
        "punycode": 1.0 if "xn--" in host else 0.0,
        "non_ascii": 1.0 if any(ord(ch) > 127 for ch in host) else 0.0,
        "lookalike_brand": 1.0 if look else 0.0,
        "brand_in_host_unofficial": 1.0 if brands_host else 0.0,
        "brand_in_path_unofficial": 1.0 if brands_path and not brands_host else 0.0,
        "official_domain": 1.0 if official else 0.0,
        "restricted_tld": 1.0 if restricted else 0.0,
        "suspicious_tld": 1.0 if tld in SUSPICIOUS_TLDS else 0.0,
        "shortener": 1.0 if reg in SHORTENERS or host in SHORTENERS else 0.0,
        "host_entropy": min(max(entropy - 2.5, 0.0) / 2.0, 1.0),
        "host_hyphens": min(host.count("-") / 3.0, 1.0),
        "https": 1.0 if p["scheme"] == "https" else 0.0,
        "explicit_http": 1.0 if p["scheme"] == "http" else 0.0,
        "path_keywords": min(len(kw_hits) / 2.0, 1.0),
        "path_depth": min(depth / 5.0, 1.0),
        "query_params": min(n_params / 3.0, 1.0),
        "has_port": 1.0 if p["port"] and p["port"] not in ("80", "443") else 0.0,
        "redirect_slash": 1.0 if "//" in path else 0.0,
        "apk_exe": 1.0 if re.search(r"\.(apk|exe|scr|msi|bat)$", path.lower()) else 0.0,
        "gov_lookalike": 1.0 if gov_hits else 0.0,
        "random_token": 1.0 if rand_tok else 0.0,
    }
    info = {
        "host": host, "registered_domain": reg, "tld": tld, "scheme": p["scheme"] or "(none)",
        "brands": sorted(set(brands_host + brands_path)), "lookalike_of": look,
        "path_keywords": kw_hits, "entropy": round(entropy, 2),
    }
    return [vec[n] for n in FEATURE_NAMES], info
