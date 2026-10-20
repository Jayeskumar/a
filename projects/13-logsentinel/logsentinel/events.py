"""The one normalized event every parser produces and every rule consumes.

Keeping a single flat record (rather than per-source classes) means the
correlation engine never has to care which file a line came from.
"""

from datetime import datetime


class Event:
    """A single parsed log line, normalized across all sources.

    kind  - one of: web, ssh, sudo, firewall
    ts    - datetime (naive, local wall-clock as written in the log)
    src   - source IP (string) or None
    fields- source-specific extras (method, path, status, user, port, ...)
    raw   - the original line, kept verbatim for evidence display
    """

    __slots__ = ("idx", "kind", "ts", "src", "fields", "raw")

    def __init__(self, kind, ts, src, fields, raw, idx=-1):
        self.idx = idx
        self.kind = kind
        self.ts = ts
        self.src = src
        self.fields = fields
        self.raw = raw

    @property
    def epoch(self):
        return self.ts.timestamp()

    def get(self, key, default=None):
        return self.fields.get(key, default)

    def to_dict(self):
        return {
            "idx": self.idx,
            "kind": self.kind,
            "ts": self.ts.isoformat(),
            "epoch": self.epoch,
            "src": self.src,
            "fields": self.fields,
            "raw": self.raw,
        }

    def __repr__(self):
        return "Event(%s %s %s %r)" % (self.kind, self.ts.isoformat(), self.src, self.fields)


def iso(ts):
    if isinstance(ts, datetime):
        return ts.isoformat()
    return ts
