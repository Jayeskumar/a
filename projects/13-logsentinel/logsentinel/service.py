"""Stateful service object the HTTP layer talks to. No HTTP code here.

Holds the current Analysis (demo data by default), serves JSON-friendly views,
handles log uploads, builds the tail-replay stream and exports.
"""

from . import config as C
from . import generator, reports
from .parsers import parse_text, detect_format
from .engine import Analysis
from .evaluation import evaluate


class Service:
    def __init__(self):
        self._eval = None
        self.load_demo()

    # ---------------------------------------------------------- loading
    def load_demo(self):
        self.gen = generator.generate()
        self.source = "demo"
        self.source_label = "Deterministic demo log (seed %d)" % generator.SEED
        events, stats = parse_text(self.gen.text())
        self.an = Analysis(events, stats)
        self._index_lines()

    def analyze_text(self, text, fmt=None):
        events, stats = parse_text(text, fmt=fmt)
        if not events:
            raise ValueError("No parseable log lines found. Expected Apache/Nginx "
                             "access, Linux auth.log, or iptables/UFW firewall lines.")
        self.an = Analysis(events, stats)
        self.gen = None
        self.source = "upload"
        detected = detect_format(text.splitlines()[:C.DETECT_SAMPLE_LINES])
        self.source_label = "Uploaded log (%d lines, detected: %s)" % (
            stats["total"], detected or "mixed")
        self._index_lines()
        return self.summary()

    # ---------------------------------------------------------- replay index
    def _index_lines(self):
        """Tag each event with the worst alert whose window+IP covers it, so the
        tail-replay can light up the attack as it streams past."""
        evs = sorted(self.an.events, key=lambda e: e.epoch)
        self.stream_events = evs
        # bucket alerts by src for a quick lookup
        by_src = {}
        for a in self.an.alerts:
            by_src.setdefault(a.src, []).append(a)
        tags = []
        for ev in evs:
            best = None
            for a in by_src.get(ev.src, []):
                s = a.start.timestamp() if a.start else None
                e = a.end.timestamp() if a.end else None
                if s is None or e is None:
                    continue
                if s - 1 <= ev.epoch <= e + 1:
                    if best is None or a.weight > best.weight:
                        best = a
            tags.append(best)
        self.stream_tags = tags

    # ---------------------------------------------------------- views
    def health(self):
        return {"status": "ok", "source": self.source,
                "events": len(self.an.events), "alerts": len(self.an.alerts),
                "incidents": len(self.an.incidents)}

    def summary(self):
        s = self.an.summary()
        s["source"] = self.source
        s["source_label"] = self.source_label
        return s

    def alerts(self, severity=None, category=None, src=None, rule=None):
        rows = []
        for a in self.an.alerts:
            if severity and a.severity != severity:
                continue
            if category and a.category != category:
                continue
            if src and a.src != src:
                continue
            if rule and a.rule != rule:
                continue
            d = a.to_dict()
            d["evidence"] = d["evidence"][:4]     # list view stays light
            rows.append(d)
        rows.sort(key=lambda d: (C.SEVERITY_ORDER.index(d["severity"]),), reverse=True)
        return {"alerts": rows, "total": len(rows)}

    def alert(self, aid):
        a = self.an.by_id.get(aid)
        if not a:
            raise KeyError(aid)
        return a.to_dict()

    def incidents(self):
        return {"incidents": self.an.incidents}

    def incident(self, iid):
        for inc in self.an.incidents:
            if inc["id"] == iid:
                out = dict(inc)
                out["alerts"] = [self.an.by_id[a].to_dict()
                                 for a in inc["alert_ids"] if a in self.an.by_id]
                return out
        raise KeyError(iid)

    def rpm(self):
        return self.an.rpm

    def stream(self, offset=0, limit=400):
        offset = max(0, offset)
        chunk = self.stream_events[offset:offset + limit]
        tags = self.stream_tags[offset:offset + limit]
        out = []
        for ev, tag in zip(chunk, tags):
            out.append({
                "idx": offset + len(out),
                "t": ev.epoch,
                "iso": ev.ts.isoformat(),
                "kind": ev.kind,
                "src": ev.src,
                "line": ev.raw,
                "sev": tag.severity if tag else None,
                "alert": tag.id if tag else None,
                "category": tag.category if tag else None,
            })
        return {"events": out, "offset": offset,
                "total": len(self.stream_events),
                "next": offset + len(out),
                "done": offset + len(out) >= len(self.stream_events)}

    def blocklist(self):
        rows = self.an.blocklist()
        return {"rows": rows, "text": reports.blocklist_text(rows)}

    def report(self, iid, fmt="md"):
        inc = None
        for i in self.an.incidents:
            if i["id"] == iid:
                inc = i
                break
        if inc is None:
            raise KeyError(iid)
        if fmt == "html":
            return reports.incident_html(inc, self.an.by_id)
        return reports.incident_markdown(inc, self.an.by_id)

    def evaluation(self):
        if self._eval is None:
            self._eval = evaluate()
        return self._eval
