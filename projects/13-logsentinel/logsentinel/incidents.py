"""Group related alerts from one source into a single incident with a
kill-chain-style timeline, so an analyst reads one story instead of 30 rows.
"""

from . import config as C
from .mitre import enrich

# Rough Lockheed-Martin-style kill-chain phase for each rule, used to order the
# incident timeline into a narrative.
PHASE = {
    "WEB-SCANNER-UA": ("Reconnaissance", 1),
    "ANOM-UA": ("Reconnaissance", 1),
    "ANOM-PATH": ("Reconnaissance", 1),
    "FW-PORTSCAN": ("Reconnaissance", 1),
    "FW-SWEEP": ("Reconnaissance", 1),
    "WEB-ENUM": ("Reconnaissance", 1),
    "ANOM-RATE": ("Reconnaissance", 1),
    "SSH-BRUTE": ("Credential Access", 2),
    "SSH-SPRAY": ("Credential Access", 2),
    "SSH-STUFFING": ("Credential Access", 2),
    "WEB-SQLI": ("Exploitation", 3),
    "WEB-XSS": ("Exploitation", 3),
    "WEB-TRAVERSAL": ("Exploitation", 3),
    "WEB-CMDI": ("Exploitation", 3),
    "SSH-COMPROMISE": ("Initial Access", 4),
    "SSH-OFFHOURS": ("Initial Access", 4),
    "SUDO-ESCALATION": ("Privilege Escalation", 5),
}


def _sev_rank(s):
    return C.SEVERITY_ORDER.index(s) if s in C.SEVERITY_ORDER else 0


def group(alerts):
    """Return a list of incident dicts. Alerts are grouped by source IP; alerts
    from the same IP within INCIDENT_GAP_S of each other join one incident.
    Alerts without a source IP (e.g. unlinked sudo) become singletons."""
    by_ip = {}
    singles = []
    for a in alerts:
        if a.src:
            by_ip.setdefault(a.src, []).append(a)
        else:
            singles.append([a])

    groups = []
    for ip, al in by_ip.items():
        al.sort(key=lambda x: (x.start or x.end).timestamp())
        cur = [al[0]]
        for a in al[1:]:
            last_end = (cur[-1].end or cur[-1].start).timestamp()
            if (a.start or a.end).timestamp() - last_end <= C.INCIDENT_GAP_S:
                cur.append(a)
            else:
                groups.append(cur)
                cur = [a]
        groups.append(cur)
    groups += singles

    incidents = []
    for i, members in enumerate(groups, 1):
        members.sort(key=lambda a: ((a.start or a.end).timestamp(),
                                    PHASE.get(a.rule, ("", 9))[1]))
        sev = max((m.severity for m in members), key=_sev_rank)
        start = min((m.start or m.end) for m in members)
        end = max((m.end or m.start) for m in members)
        src = members[0].src
        mitre_ids = []
        for m in members:
            for t in m.mitre:
                if t not in mitre_ids:
                    mitre_ids.append(t)
        timeline = []
        for m in members:
            phase, order = PHASE.get(m.rule, ("Activity", 9))
            timeline.append({
                "ts": (m.start or m.end).isoformat(),
                "phase": phase, "order": order,
                "alert_id": m.id, "rule": m.rule,
                "severity": m.severity, "title": m.title,
                "category": m.category,
            })
        timeline.sort(key=lambda x: (x["ts"], x["order"]))
        phases = []
        for t in timeline:
            if t["phase"] not in phases:
                phases.append(t["phase"])
        incidents.append({
            "id": "INC%03d" % i,
            "src": src,
            "severity": sev,
            "alert_count": len(members),
            "alert_ids": [m.id for m in members],
            "categories": sorted({m.category for m in members}),
            "mitre": enrich(mitre_ids),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "phases": phases,
            "timeline": timeline,
            "summary": _summary(src, members, phases),
        })
    incidents.sort(key=lambda inc: (_sev_rank(inc["severity"]), inc["alert_count"]),
                   reverse=True)
    return incidents


def _summary(src, members, phases):
    cats = sorted({m.category for m in members})
    phase_str = " -> ".join(phases)
    return ("%s drove %d alert(s) across %d category(ies) [%s]; kill-chain: %s."
            % (src or "n/a", len(members), len(cats), ", ".join(cats), phase_str))
