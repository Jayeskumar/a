"""Find URLs, phone numbers, UPI IDs, e-mails and money amounts inside free text.

Every finder returns dicts with the matched ``value`` and its ``start``/``end``
character offsets in the original text so the UI can highlight them.
"""
import re

# TLDs we accept for bare domains such as "bit.ly/abc" or "sbi-kyc.xyz".
# Restricting to a list stops "Rs.500" or "e.g." being read as links.
_TLDS = (
    "com|in|net|org|co|io|ly|me|info|xyz|top|club|online|site|live|icu|buzz|"
    "click|link|shop|store|app|tk|ml|ga|cf|gq|win|loan|work|gov|edu|ac|sbi|"
    "cc|ws|to|gl|gd|page|biz|vip|rest|monster|support|help|cyou|sbs|cfd|bond|be|at"
)

URL_RE = re.compile(
    r"(?<![@\w.\-])("
    r"(?:https?://|www\.)[^\s<>\"'()\[\]{}]+"            # explicit scheme / www
    r"|(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+(?:" + _TLDS + r")\b"
    r"(?::\d{2,5})?(?:/[^\s<>\"'()\[\]{}]*)?"             # bare domain + path
    r"|(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?/[^\s<>\"'()\[\]{}]*"  # bare IP + path
    r")",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(r"\b[\w.+\-]+@[a-z0-9\-]+(?:\.[a-z0-9\-]+)+\b", re.IGNORECASE)

# UPI virtual payment address: handle@psp with no dot after the @.
UPI_RE = re.compile(r"(?<![\w.])([a-z0-9][a-z0-9.\-_]{1,48}@[a-z]{2,20})(?![\w.@])", re.IGNORECASE)

PHONE_RE = re.compile(
    r"(?<![\d\w])("
    r"1800[\s\-]?\d{3,4}[\s\-]?\d{3,4}"                    # toll free
    r"|(?:\+91[\s\-]?|0)?[6-9]\d{4}[\s\-]?\d{5}"           # Indian mobile
    r")(?!\d)"
)

MONEY_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|cr|k))?"
    r"|\d[\d,]*(?:\.\d+)?\s?(?:lakh|lakhs|crore)\b",
    re.IGNORECASE,
)

_TRAILING = ".,;:!?)'\"]"


def _clean_url(value, start):
    end = start + len(value)
    while value and value[-1] in _TRAILING:
        value = value[:-1]
        end -= 1
    return value, end


def find_urls(text):
    out = []
    for m in URL_RE.finditer(text):
        value, end = _clean_url(m.group(1), m.start(1))
        if "." not in value:
            continue
        out.append({"value": value, "start": m.start(1), "end": end})
    return out


def find_emails(text):
    return [{"value": m.group(0), "start": m.start(), "end": m.end()} for m in EMAIL_RE.finditer(text)]


def find_upi_ids(text):
    emails = find_emails(text)
    out = []
    for m in UPI_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        if any(em["start"] <= s < em["end"] for em in emails):
            continue
        out.append({"value": m.group(1), "start": s, "end": e})
    return out


def find_phones(text):
    taken = [(u["start"], u["end"]) for u in find_urls(text)]
    out = []
    for m in PHONE_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        if any(a <= s < b for a, b in taken):
            continue
        digits = re.sub(r"\D", "", m.group(1))
        out.append({"value": m.group(1), "digits": digits, "start": s, "end": e})
    return out


def find_money(text):
    return [{"value": m.group(0), "start": m.start(), "end": m.end()} for m in MONEY_RE.finditer(text)]


def extract_all(text):
    return {
        "urls": find_urls(text),
        "phones": find_phones(text),
        "upi": find_upi_ids(text),
        "emails": find_emails(text),
    }
