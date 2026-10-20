"""The detection engine: events in, alerts + incidents + stats out.

Pipeline:
  signatures  (per web line, URL-decoded)   ->  aggregated per IP+rule
  correlation (stateful sliding windows)
  anomaly     (EWMA rate + novelty)
  -------------------------------------------------------------------
  grouped into incidents with a kill-chain timeline
  summarised for the dashboard (severity donut, top attackers, RPM chart)
"""

from . import config as C
from . import signatures, correlation, anomaly, incidents
from .alerts import Alert, reset_ids


# --------------------------------------------------------------- signatures
_SIG_META = {
    "WEB-SQLI": ("web-sqli", "SQL Injection"),
    "WEB-XSS": ("web-xss", "Cross-Site Scripting"),
    "WEB-TRAVERSAL": ("web-traversal", "Path Traversal / LFI"),
    "WEB-CMDI": ("web-cmdi", "Command Injection"),
    "WEB-SCANNER-UA": ("web-scanner", "Scanner User-Agent"),
}


def signature_alerts(events):
    """Scan web events, then aggregate repeated hits from the same IP for the
    same rule into one alert (new hits keep bumping the count)."""
    buckets = {}         # (ip, rule) -> list of (event, hit)
    for ev in events:
        if ev.kind != "web":
            continue
        for hit in signatures.scan_event(ev):
            buckets.setdefault((ev.src, hit["rule"]), []).append((ev, hit))

    alerts = []
    for (ip, rule), items in buckets.items():
        items.sort(key=lambda x: x[0].epoch)
        # split by merge gap so a scan today and one next week aren't merged
        cur = [items[0]]
        clusters = []
        for it in items[1:]:
            if it[0].epoch - cur[-1][0].epoch <= C.ALERT_MERGE_GAP_S:
                cur.append(it)
            else:
                clusters.append(cur)
                cur = [it]
        clusters.append(cur)
        for cluster in clusters:
            evs = [e for e, _ in cluster]
            hit = cluster[0][1]
            key, label = _SIG_META.get(rule, ("web-scanner", hit["category"]))
            samples = sorted({h["match"] for _, h in cluster})[:5]
            a = Alert(
                rule, hit["category"], hit["severity"], ip,
                "%s from %s" % (label, ip),
                "%s %s signature hit(s). Example payload(s): %s"
                % (len(cluster), hit["category"], "; ".join(samples)),
                hit["mitre"], key,
                [e.raw for e in evs[:C.EVIDENCE_CAP]], evs[0].ts, evs[-1].ts,
                extra={"hits": len(cluster), "samples": samples,
                       "endpoints": sorted({e.get("path").split('?')[0]
                                            for e in evs})[:8]})
            a.evidence_count = len(cluster)
            alerts.append(a)
    return alerts


# --------------------------------------------------------------- analysis object
class Analysis:
    def __init__(self, events, stats):
        reset_ids()
        self.events = events
        self.parse_stats = stats
        self.alerts = []
        self.alerts += signature_alerts(events)
        self.alerts += correlation.run(events)
        self.alerts += anomaly.rate_anomalies(events)
        self.alerts += anomaly.novelty(events)
        self.alerts.sort(key=lambda a: ((a.start or a.end).timestamp(), -a.weight))
        self.incidents = incidents.group(self.alerts)
        self.rpm = anomaly.global_rpm(events)
        self.by_id = {a.id: a for a in self.alerts}

    # --------- summaries for the dashboard ---------
    def severity_counts(self):
        counts = {s: 0 for s in C.SEVERITY_ORDER}
        for a in self.alerts:
            counts[a.severity] = counts.get(a.severity, 0) + 1
        return counts

    def category_counts(self):
        out = {}
        for a in self.alerts:
            out[a.category] = out.get(a.category, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def top_attackers(self, n=8):
        agg = {}
        for a in self.alerts:
            if not a.src:
                continue
            d = agg.setdefault(a.src, {"src": a.src, "alerts": 0, "score": 0,
                                       "categories": set(), "worst": "info"})
            d["alerts"] += 1
            d["score"] += a.weight
            d["categories"].add(a.category)
            if C.SEVERITY_ORDER.index(a.severity) > C.SEVERITY_ORDER.index(d["worst"]):
                d["worst"] = a.severity
        rows = []
        for d in agg.values():
            d["categories"] = sorted(d["categories"])
            rows.append(d)
        rows.sort(key=lambda d: d["score"], reverse=True)
        return rows[:n]

    def timespan(self):
        if not self.events:
            return {"start": None, "end": None, "minutes": 0}
        s = min(e.ts for e in self.events)
        e = max(ev.ts for ev in self.events)
        return {"start": s.isoformat(), "end": e.isoformat(),
                "minutes": int((e - s).total_seconds() // 60)}

    def summary(self):
        sev = self.severity_counts()
        return {
            "events": len(self.events),
            "parse_stats": self.parse_stats,
            "alerts": len(self.alerts),
            "incidents": len(self.incidents),
            "severity": sev,
            "critical_high": sev["critical"] + sev["high"],
            "categories": self.category_counts(),
            "top_attackers": self.top_attackers(),
            "timespan": self.timespan(),
        }

    def blocklist(self):
        """Distinct attacker IPs worth blocking (medium+), as iptables and
        fail2ban-style text. Never executed - this is a copy-paste artefact."""
        ips = {}
        for a in self.alerts:
            if not a.src:
                continue
            if C.SEVERITY_ORDER.index(a.severity) < C.SEVERITY_ORDER.index("medium"):
                continue
            d = ips.setdefault(a.src, {"worst": a.severity, "cats": set()})
            d["cats"].add(a.category)
            if C.SEVERITY_ORDER.index(a.severity) > C.SEVERITY_ORDER.index(d["worst"]):
                d["worst"] = a.severity
        return [{"ip": ip, "severity": d["worst"], "reasons": sorted(d["cats"])}
                for ip, d in sorted(ips.items(),
                                    key=lambda kv: -C.SEVERITY_ORDER.index(kv[1]["worst"]))]
