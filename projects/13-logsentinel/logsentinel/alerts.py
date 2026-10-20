"""The Alert record and the recommended-response playbook.

An alert is the atomic finding. Incidents (incidents.py) group alerts; the
engine (engine.py) produces them. Every alert carries enough to act on it:
severity, the rule that fired, evidence lines, source IP, timeframe, MITRE
mapping and a concrete recommended response.
"""

from .config import SEVERITY_WEIGHT
from .mitre import enrich

# Which response playbook each rule category maps to. Kept here so the advice is
# consistent across signature and correlation rules.
RESPONSES = {
    "ssh-brute": [
        "Block the source IP at the firewall / fail2ban sshd jail.",
        "Confirm the targeted account(s) were not compromised; force a password reset if in doubt.",
        "Enable fail2ban (or raise MaxAuthTries / lower LoginGraceTime) and disable password auth in favour of keys.",
    ],
    "ssh-spray": [
        "Block the source IP; it is testing many accounts, not one.",
        "Check whether any sprayed username succeeded (see linked compromise alerts).",
        "Enforce MFA and move SSH to key-only authentication.",
    ],
    "ssh-stuffing": [
        "Block the source IP; the username list looks like a leaked combo list.",
        "Force password resets on any account that appears in the list and succeeded.",
        "Enable MFA; adopt a breached-password screening policy.",
    ],
    "ssh-compromise": [
        "Treat as a live compromise: isolate the host and review the session's activity.",
        "Reset the account's password and revoke its SSH keys and active sessions.",
        "Hunt for persistence (new keys in authorized_keys, cron jobs, new users).",
    ],
    "ssh-offhours": [
        "Verify the login with the account owner out-of-band; off-hours admin access is unusual.",
        "If unrecognised, reset credentials and review what the session did.",
        "Require MFA and restrict admin SSH to a bastion / allow-list of source IPs.",
    ],
    "sudo-escalation": [
        "Review the sudo command(s) run; confirm the user is authorised for them.",
        "If tied to a suspicious login, treat the host as compromised and rotate credentials.",
        "Tighten sudoers to least privilege and enable sudo I/O logging.",
    ],
    "fw-scan": [
        "Block the scanning IP at the perimeter firewall.",
        "Confirm no scanned port exposes an unpatched service; close unused ports.",
        "Rate-limit / tarpit new connections and enable port-scan detection.",
    ],
    "fw-sweep": [
        "Block the source IP; it is sweeping many hosts for a live target.",
        "Ensure internet-facing hosts expose only required services.",
        "Deploy a honeypot / alert on sweeps to catch the next stage early.",
    ],
    "web-sqli": [
        "Block the source IP and patch input validation / use parameterised queries on the hit endpoint.",
        "Review DB logs for data exfiltration from that endpoint.",
        "Put the app behind a WAF rule for SQLi and audit the query layer.",
    ],
    "web-xss": [
        "Block the source IP; output-encode and sanitise the reflected parameter.",
        "Add a Content-Security-Policy and set HttpOnly on session cookies.",
        "Audit the endpoint for stored XSS as well as reflected.",
    ],
    "web-traversal": [
        "Block the source IP; canonicalise and allow-list file paths on the endpoint.",
        "Confirm no sensitive file was served (check the response sizes/status).",
        "Run the app as a low-privilege user chrooted away from system files.",
    ],
    "web-cmdi": [
        "Block the source IP immediately; command injection can be full RCE.",
        "Patch the endpoint to never pass user input to a shell; use exec arrays / allow-lists.",
        "Assume the host may be compromised and begin incident response.",
    ],
    "web-scanner": [
        "Block the scanning IP; it is using an automated vulnerability tool.",
        "Review which endpoints it reached and whether any returned 200.",
        "Deploy a WAF and rate-limit by IP.",
    ],
    "web-enum": [
        "Block the source IP; it is brute-forcing directory/file names.",
        "Ensure no hidden admin/backup path is reachable; return uniform 404s.",
        "Rate-limit 404s per IP and add a WAF path-enumeration rule.",
    ],
    "anomaly-rate": [
        "Investigate the IP's traffic; a sudden rate spike can be scraping, DoS or a scripted attack.",
        "Rate-limit the IP if the volume is not from a known partner/crawler.",
        "Correlate with signature alerts from the same IP.",
    ],
    "anomaly-novelty": [
        "Review the novel user-agent / paths; novelty often precedes an exploitation attempt.",
        "Block if the client is clearly a tool rather than a browser.",
        "Keep the baseline updated so legitimate new clients stop alerting.",
    ],
}


class Alert:
    _seq = 0

    def __init__(self, rule, category, severity, src, title, detail,
                 mitre, response_key, evidence, start, end, extra=None):
        Alert._seq += 1
        self.id = "A%04d" % Alert._seq
        self.rule = rule
        self.category = category
        self.severity = severity
        self.src = src
        self.title = title
        self.detail = detail
        self.mitre = list(mitre)
        self.response_key = response_key
        self.evidence = list(evidence)       # list of raw log lines
        self.evidence_count = len(evidence)   # may be bumped past len(evidence)
        self.start = start                    # datetime
        self.end = end                        # datetime
        self.extra = extra or {}

    @property
    def weight(self):
        return SEVERITY_WEIGHT.get(self.severity, 10)

    def to_dict(self):
        return {
            "id": self.id,
            "rule": self.rule,
            "category": self.category,
            "severity": self.severity,
            "src": self.src,
            "title": self.title,
            "detail": self.detail,
            "mitre": enrich(self.mitre),
            "response": RESPONSES.get(self.response_key, []),
            "evidence": self.evidence,
            "evidence_count": self.evidence_count,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "extra": self.extra,
        }


def reset_ids():
    Alert._seq = 0
