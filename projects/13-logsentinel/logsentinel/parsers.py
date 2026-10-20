"""Parsers for the three log families LogSentinel understands, plus auto-detect.

Every parser is line-oriented and never raises on a bad line: it returns None
and the caller counts the miss. This is deliberate - real log files are full of
truncated lines, rotated-file headers and the occasional binary smear, and a SOC
tool that dies on the first malformed line is useless.

Supported formats:
  * Apache / Nginx "combined" access log
  * Linux auth.log (sshd accepted/failed/invalid-user, plus sudo)
  * A simple iptables-style firewall log
"""

import re
from datetime import datetime

from .config import DEFAULT_YEAR
from .events import Event

# --------------------------------------------------------------- web access log
# host - - [10/Oct/2026:13:55:36 +0000] "GET /path HTTP/1.1" 200 2326 "ref" "ua"
_COMBINED = re.compile(
    r'^(?P<host>\S+)\s+\S+\s+(?P<user>\S+)\s+'
    r'\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<req>[^"]*)"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\d+|-)'
    r'(?:\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)")?'
)
_CLF_TIME = "%d/%b/%Y:%H:%M:%S"

# --------------------------------------------------------------- syslog prefix
# "Oct 10 13:55:36 host sshd[1234]: message"
_SYSLOG = re.compile(
    r'^(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+'
    r'(?P<time>\d{2}:\d{2}:\d{2})\s+'
    r'(?P<host>\S+)\s+'
    r'(?P<proc>[\w./-]+?)(?:\[(?P<pid>\d+)\])?:\s*'
    r'(?P<msg>.*)$'
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

_IP = r'(?P<ip>\d{1,3}(?:\.\d{1,3}){3})'
_SSH_FAILED = re.compile(r'Failed password for (?:invalid user )?(?P<user>\S+) from ' + _IP)
_SSH_INVALID = re.compile(r'Invalid user (?P<user>\S+) from ' + _IP)
_SSH_ACCEPTED = re.compile(r'Accepted (?P<method>\w+) for (?P<user>\S+) from ' + _IP)
_SSH_NOID = re.compile(r'Did not receive identification string from ' + _IP)
_SUDO = re.compile(
    r'(?P<ruser>\S+)\s*:.*?USER=(?P<tuser>\S+)\s*;\s*COMMAND=(?P<cmd>.*)$')

# --------------------------------------------------------------- firewall
# Two shapes:
#   kernel iptables: "... kernel: [..] FW-DROP IN=eth0 ... SRC=.. DST=.. PROTO=TCP ... DPT=22"
#   ufw style:       "... kernel: [UFW BLOCK] IN=eth0 SRC=.. DST=.. PROTO=TCP ... DPT=22"
_FW_KV = re.compile(r'(?P<k>SRC|DST|PROTO|SPT|DPT|IN|OUT)=(?P<v>\S+)')
_FW_ACTION = re.compile(r'(?:\[UFW\s+(?P<ufw>\w+)\]|FW-(?P<fw>DROP|ACCEPT|REJECT)|'
                        r'\b(?P<act>DROP|BLOCK|REJECT|ACCEPT|DENY)\b)')


def _syslog_time(mon, day, hhmmss, year):
    m = _MONTHS.get(mon)
    if not m:
        raise ValueError("bad month " + mon)
    h, mi, s = (int(x) for x in hhmmss.split(":"))
    return datetime(year, m, int(day), h, mi, s)


def parse_web_line(line, idx=-1):
    m = _COMBINED.match(line.rstrip("\n"))
    if not m:
        return None
    try:
        # CLF time includes a trailing " +0000" offset; split it off.
        raw_ts = m.group("ts")
        stamp, _, _off = raw_ts.partition(" ")
        ts = datetime.strptime(stamp, _CLF_TIME)
    except (ValueError, TypeError):
        return None
    req = m.group("req") or ""
    parts = req.split(" ")
    method = parts[0] if parts and parts[0] else "-"
    path = parts[1] if len(parts) > 1 else "-"
    proto = parts[2] if len(parts) > 2 else "-"
    try:
        status = int(m.group("status"))
    except (TypeError, ValueError):
        return None
    size = m.group("size")
    size = 0 if size in (None, "-") else int(size)
    fields = {
        "method": method, "path": path, "proto": proto,
        "status": status, "size": size,
        "ua": m.group("ua") or "-", "ref": m.group("ref") or "-",
    }
    return Event("web", ts, m.group("host"), fields, line.rstrip("\n"), idx)


def parse_auth_line(line, idx=-1, year=DEFAULT_YEAR):
    m = _SYSLOG.match(line.rstrip("\n"))
    if not m:
        return None
    try:
        ts = _syslog_time(m.group("mon"), m.group("day"), m.group("time"), year)
    except ValueError:
        return None
    proc = m.group("proc")
    msg = m.group("msg")
    raw = line.rstrip("\n")

    if proc.startswith("sshd"):
        mm = _SSH_FAILED.search(msg)
        if mm:
            invalid = "invalid user" in msg
            f = {"service": "ssh", "outcome": "fail", "user": mm.group("user"),
                 "invalid_user": invalid}
            return Event("ssh", ts, mm.group("ip"), f, raw, idx)
        mm = _SSH_INVALID.search(msg)
        if mm:
            f = {"service": "ssh", "outcome": "fail", "user": mm.group("user"),
                 "invalid_user": True}
            return Event("ssh", ts, mm.group("ip"), f, raw, idx)
        mm = _SSH_ACCEPTED.search(msg)
        if mm:
            f = {"service": "ssh", "outcome": "success", "user": mm.group("user"),
                 "method": mm.group("method"), "invalid_user": False}
            return Event("ssh", ts, mm.group("ip"), f, raw, idx)
        mm = _SSH_NOID.search(msg)
        if mm:
            f = {"service": "ssh", "outcome": "probe", "user": None, "invalid_user": False}
            return Event("ssh", ts, mm.group("ip"), f, raw, idx)
        return None

    if proc.startswith("sudo"):
        mm = _SUDO.search(msg)
        if mm:
            f = {"service": "sudo", "ruser": mm.group("ruser").strip(),
                 "tuser": mm.group("tuser"), "cmd": mm.group("cmd").strip()}
            return Event("sudo", ts, None, f, raw, idx)
        return None

    return None


def parse_firewall_line(line, idx=-1, year=DEFAULT_YEAR):
    raw = line.rstrip("\n")
    m = _SYSLOG.match(raw)
    if not m:
        return None
    msg = m.group("msg")
    if "SRC=" not in msg or "DPT=" not in msg:
        return None
    try:
        ts = _syslog_time(m.group("mon"), m.group("day"), m.group("time"), year)
    except ValueError:
        return None
    kv = {}
    for g in _FW_KV.finditer(msg):
        kv[g.group("k")] = g.group("v")
    if "SRC" not in kv:
        return None
    am = _FW_ACTION.search(msg)
    action = "DROP"
    if am:
        action = (am.group("ufw") or am.group("fw") or am.group("act") or "DROP").upper()
    try:
        dpt = int(kv.get("DPT")) if kv.get("DPT") else None
    except ValueError:
        dpt = None
    try:
        spt = int(kv.get("SPT")) if kv.get("SPT") else None
    except ValueError:
        spt = None
    f = {"service": "firewall", "action": action, "proto": kv.get("PROTO", "?"),
         "dst": kv.get("DST"), "dport": dpt, "sport": spt, "iface": kv.get("IN")}
    return Event("firewall", ts, kv.get("SRC"), f, raw, idx)


# --------------------------------------------------------------- auto-detect
def classify_line(line):
    """Return 'web' | 'auth' | 'firewall' | None for a single line."""
    s = line.strip()
    if not s:
        return None
    if _COMBINED.match(s):
        return "web"
    m = _SYSLOG.match(s)
    if m:
        msg = m.group("msg")
        if "SRC=" in msg and "DPT=" in msg:
            return "firewall"
        proc = m.group("proc")
        if proc.startswith("sshd") or proc.startswith("sudo"):
            return "auth"
        return "auth"      # some other syslog line; auth parser will skip it
    return None


def detect_format(lines):
    """Guess the dominant format of an iterable of lines by majority vote."""
    votes = {"web": 0, "auth": 0, "firewall": 0}
    for line in lines:
        c = classify_line(line)
        if c:
            votes[c] += 1
    best = max(votes, key=votes.get)
    return best if votes[best] else None


_PARSERS = {
    "web": parse_web_line,
    "auth": parse_auth_line,
    "firewall": parse_firewall_line,
}


def parse_lines(lines, fmt=None, year=DEFAULT_YEAR):
    """Parse an iterable of raw lines.

    If fmt is None, each line is classified on its own, so a single mixed file
    (web + auth + firewall concatenated) parses correctly. Returns
    (events, stats) where stats counts parsed/malformed/blank per format.
    """
    events = []
    stats = {"total": 0, "parsed": 0, "blank": 0, "malformed": 0,
             "by_format": {"web": 0, "auth": 0, "firewall": 0}}
    idx = 0
    for line in lines:
        stats["total"] += 1
        if not line.strip():
            stats["blank"] += 1
            continue
        use = fmt or classify_line(line)
        if use == "auth":
            ev = parse_auth_line(line, idx, year)
        elif use == "web":
            ev = parse_web_line(line, idx)
        elif use == "firewall":
            ev = parse_firewall_line(line, idx, year)
        else:
            ev = None
        if ev is None:
            stats["malformed"] += 1
            continue
        events.append(ev)
        stats["parsed"] += 1
        stats["by_format"][ev.kind if ev.kind in ("web", "firewall") else "auth"] += 1
        idx += 1
    return events, stats


def parse_text(text, fmt=None, year=DEFAULT_YEAR):
    return parse_lines(text.splitlines(), fmt=fmt, year=year)
