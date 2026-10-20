"""MITRE ATT&CK technique lookup for the rules LogSentinel ships.

Only technique IDs we are confident about are used. Each entry carries the
canonical name and a one-line "why this maps here" so the dashboard can explain
the mapping instead of just printing an opaque T-number.
"""

MITRE = {
    "T1110":     ("Brute Force", "Repeated credential guessing against an account or service."),
    "T1110.001": ("Brute Force: Password Guessing", "Many passwords tried against one or few accounts."),
    "T1110.003": ("Brute Force: Password Spraying", "A few common passwords tried across many accounts."),
    "T1110.004": ("Brute Force: Credential Stuffing", "Leaked username/password pairs replayed in bulk."),
    "T1078":     ("Valid Accounts", "Use of legitimate credentials for access/persistence."),
    "T1190":     ("Exploit Public-Facing Application", "Malicious input aimed at a public web app."),
    "T1595":     ("Active Scanning", "Probing hosts/services to map the attack surface."),
    "T1595.001": ("Active Scanning: Scanning IP Blocks", "Sweeping a range of hosts to find live targets."),
    "T1046":     ("Network Service Discovery", "Enumerating listening services/ports on a host."),
    "T1083":     ("File and Directory Discovery", "Enumerating files/paths, e.g. dir brute-forcing."),
    "T1068":     ("Exploitation for Privilege Escalation", "Abusing a flaw to gain higher privileges."),
    "T1548.003": ("Abuse Elevation Control: Sudo", "Using sudo to run commands as a privileged user."),
}


def lookup(tid):
    name, why = MITRE.get(tid, ("Unknown Technique", ""))
    return {"id": tid, "name": name, "why": why}


def enrich(tids):
    return [lookup(t) for t in tids]
