"""Signature rules for web attacks: SQLi, XSS, path traversal and scanners.

The decoder runs FIRST. Attackers hide payloads behind percent-encoding (and
double-encoding) and the '+'-as-space convention, so a raw-string regex set is
trivially bypassed. We URL-decode (twice) and also fold HTML entities before the
patterns run, then match against the decoded request line AND the raw user agent.
"""

import re
from urllib.parse import unquote_plus

# ----- decode -------------------------------------------------------------
_ENTITY = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&#x27;": "'",
           "&amp;": "&", "&#40;": "(", "&#41;": ")"}


def decode(s):
    """URL-decode (twice, to catch double-encoding), fold a few HTML entities,
    and lower-case. Idempotent enough for matching; never raises."""
    if s is None:
        return ""
    try:
        out = unquote_plus(s)
        out = unquote_plus(out)
    except Exception:
        out = s
    low = out.lower()
    for k, v in _ENTITY.items():
        low = low.replace(k, v)
    return low


# ----- rule table ---------------------------------------------------------
# Each rule: id, category, severity, MITRE ids, compiled patterns, description.
class SigRule:
    def __init__(self, rid, category, severity, mitre, patterns, desc, target="path"):
        self.rid = rid
        self.category = category
        self.severity = severity
        self.mitre = mitre
        self.patterns = [re.compile(p, re.I) for p in patterns]
        self.desc = desc
        self.target = target          # "path" (decoded req) or "ua" (raw user agent)

    def match(self, text):
        for p in self.patterns:
            m = p.search(text)
            if m:
                return m.group(0)[:120]
        return None


SQLI = SigRule(
    "WEB-SQLI", "SQL Injection", "high", ["T1190"],
    [
        r"\bunion\b[\s/*]+\bselect\b",
        r"\bselect\b.+\bfrom\b",
        r"\binsert\b\s+\binto\b",
        r"\b(or|and)\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+",
        r"'\s*(or|and)\s+'?\d",
        r";\s*(drop|update|delete|insert)\b",
        r"\bsleep\s*\(\s*\d+\s*\)",
        r"\bbenchmark\s*\(",
        r"\bwaitfor\s+delay\b",
        r"\binformation_schema\b",
        r"--\s|#\s*$|/\*.*\*/",
        r"\bxp_cmdshell\b",
    ],
    "Classic SQL injection tokens in the request (union/select, boolean tautology, "
    "stacked query, time-based blind, schema probing).",
)

XSS = SigRule(
    "WEB-XSS", "Cross-Site Scripting", "medium", ["T1190"],
    [
        r"<script\b", r"</script>", r"javascript:",
        r"\bon(error|load|mouseover|click|focus)\s*=",
        r"<img\b[^>]*\bsrc\s*=", r"<svg\b[^>]*onload",
        r"document\.cookie", r"\balert\s*\(", r"\bprompt\s*\(",
        r"String\.fromCharCode", r"<iframe\b",
    ],
    "Script injection markers in the request (inline <script>, javascript: URI, "
    "event-handler attributes, cookie theft).",
)

TRAVERSAL = SigRule(
    "WEB-TRAVERSAL", "Path Traversal / LFI", "high", ["T1190", "T1083"],
    [
        r"\.\./", r"\.\.\\",
        r"/etc/passwd", r"/etc/shadow", r"\bboot\.ini\b",
        r"\bwin\.ini\b", r"\\windows\\system32",
        r"\bphp://(filter|input)", r"\bfile://",
        r"/proc/self/environ",
    ],
    "Directory traversal / local file inclusion attempts (../ sequences, access to "
    "/etc/passwd, PHP wrappers).",
)

CMDI = SigRule(
    "WEB-CMDI", "Command Injection", "high", ["T1190"],
    [
        r";\s*(cat|ls|id|whoami|uname|wget|curl|nc)\b",
        r"\|\s*(cat|ls|id|whoami|bash|sh)\b",
        r"`[^`]+`", r"\$\([^)]+\)",
        r"&&\s*(cat|ls|id|whoami)\b",
    ],
    "Shell command injection markers (command separators followed by recon/download "
    "commands, backtick or $() substitution).",
)

SCANNER_UA = SigRule(
    "WEB-SCANNER-UA", "Scanner / Tool User-Agent", "medium", ["T1595"],
    [
        r"\bsqlmap\b", r"\bnikto\b", r"\bnmap\b", r"\bmasscan\b",
        r"\bwpscan\b", r"\bnuclei\b", r"\bdirbuster\b", r"\bgobuster\b",
        r"\bffuf\b", r"\bhydra\b", r"\bmetasploit\b", r"\bzgrab\b",
        r"\bacunetix\b", r"\bnessus\b", r"\bcurl/\b", r"\bpython-requests\b",
        r"\bwfuzz\b", r"\bferoxbuster\b",
    ],
    "The User-Agent names a known vulnerability scanner or brute-force tool.",
    target="ua",
)

RULES = [SQLI, XSS, TRAVERSAL, CMDI, SCANNER_UA]


def scan_event(ev):
    """Return a list of signature hits for one web event.

    Each hit: {rule, category, severity, mitre, match, target}.
    The decoded request line is matched for payload rules; the raw UA for the
    scanner-UA rule (decoding a UA would mangle it).
    """
    if ev.kind != "web":
        return []
    decoded_req = decode(ev.get("path", "")) + " " + decode(ev.get("ref", ""))
    ua_raw = ev.get("ua", "") or ""
    hits = []
    for rule in RULES:
        text = ua_raw if rule.target == "ua" else decoded_req
        m = rule.match(text)
        if m:
            hits.append({
                "rule": rule.rid, "category": rule.category,
                "severity": rule.severity, "mitre": list(rule.mitre),
                "match": m, "target": rule.target, "desc": rule.desc,
            })
    return hits
