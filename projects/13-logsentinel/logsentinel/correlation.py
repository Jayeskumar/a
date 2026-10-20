"""Stateful sliding-window correlation rules.

These are the rules a single log line can never trigger on its own: they need
memory of what an IP did over seconds or minutes. Everything here is expressed
as "cluster an IP's events, then test a sliding window inside each cluster", so
the logic is small and unit-testable.
"""

from collections import deque, OrderedDict

from . import config as C
from .alerts import Alert


# --------------------------------------------------------------- primitives
def sliding_count_trigger(times, n, window_s):
    """True if any window of length window_s holds >= n of the sorted times."""
    dq = deque()
    for t in times:
        dq.append(t)
        while dq and t - dq[0] > window_s:
            dq.popleft()
        if len(dq) >= n:
            return True
    return False


def max_distinct_in_window(pairs, window_s):
    """pairs = sorted (time, key); return the largest number of distinct keys
    visible in any window of length window_s."""
    dq = deque()                 # (time, key)
    counts = {}
    best = 0
    for t, k in pairs:
        dq.append((t, k))
        counts[k] = counts.get(k, 0) + 1
        while dq and t - dq[0][0] > window_s:
            _, ok = dq.popleft()
            counts[ok] -= 1
            if counts[ok] == 0:
                del counts[ok]
        if len(counts) > best:
            best = len(counts)
    return best


def cluster_by_gap(events, gap_s):
    """Split time-sorted events into clusters separated by gaps > gap_s."""
    clusters = []
    cur = []
    last = None
    for ev in events:
        t = ev.epoch
        if last is not None and t - last > gap_s:
            clusters.append(cur)
            cur = []
        cur.append(ev)
        last = t
    if cur:
        clusters.append(cur)
    return clusters


def _by_ip(events, kind=None, pred=None):
    out = OrderedDict()
    for ev in events:
        if kind and ev.kind != kind:
            continue
        if pred and not pred(ev):
            continue
        if not ev.src:
            continue
        out.setdefault(ev.src, []).append(ev)
    return out


def _evidence(evs):
    lines = [e.raw for e in evs[:C.EVIDENCE_CAP]]
    return lines


def _span(evs):
    return evs[0].ts, evs[-1].ts


# --------------------------------------------------------------- SSH rules
def ssh_bruteforce(events):
    alerts = []
    fails = _by_ip(events, "ssh", lambda e: e.get("outcome") == "fail")
    for ip, evs in fails.items():
        for cluster in cluster_by_gap(evs, C.BRUTE_SLOW_WINDOW_S):
            times = [e.epoch for e in cluster]
            users = {e.get("user") for e in cluster if e.get("user")}
            fast = sliding_count_trigger(times, C.BRUTE_FAILS, C.BRUTE_WINDOW_S)
            slow = sliding_count_trigger(times, C.BRUTE_SLOW_FAILS, C.BRUTE_SLOW_WINDOW_S)
            # Brute force targets one or few accounts; many users -> spraying rule.
            if (fast or slow) and len(users) <= C.BRUTE_MAX_USERS:
                start, end = _span(cluster)
                sub = "T1110.001"
                sev = "high" if len(cluster) >= C.BRUTE_SLOW_FAILS else "medium"
                a = Alert(
                    "SSH-BRUTE", "SSH Brute Force", sev, ip,
                    "SSH brute force from %s" % ip,
                    "%d failed SSH logins against %d account(s) (%s)."
                    % (len(cluster), len(users), ", ".join(sorted(users)[:4]) or "?"),
                    ["T1110", sub], "ssh-brute",
                    _evidence(cluster), start, end,
                    extra={"fail_count": len(cluster), "users": sorted(users)})
                a.evidence_count = len(cluster)
                alerts.append(a)
    return alerts


def ssh_spraying(events):
    alerts = []
    # Failed + invalid-user attempts, keyed by IP.
    fails = _by_ip(events, "ssh",
                   lambda e: e.get("outcome") == "fail")
    for ip, evs in fails.items():
        for cluster in cluster_by_gap(evs, C.SPRAY_WINDOW_S):
            pairs = [(e.epoch, e.get("user") or "?") for e in cluster]
            distinct = max_distinct_in_window(pairs, C.SPRAY_WINDOW_S)
            if distinct < C.SPRAY_MIN_USERS:
                continue
            users = sorted({e.get("user") for e in cluster if e.get("user")})
            invalid = sum(1 for e in cluster if e.get("invalid_user"))
            ratio = invalid / float(len(cluster)) if cluster else 0.0
            start, end = _span(cluster)
            if ratio >= C.STUFFING_INVALID_RATIO:
                a = Alert(
                    "SSH-STUFFING", "Credential Stuffing", "high", ip,
                    "Credential stuffing from %s" % ip,
                    "%d login attempts spanning %d usernames, %.0f%% of them "
                    "non-existent accounts - looks like a leaked combo list."
                    % (len(cluster), len(users), ratio * 100),
                    ["T1110", "T1110.004"], "ssh-stuffing",
                    _evidence(cluster), start, end,
                    extra={"distinct_users": len(users), "invalid_ratio": round(ratio, 2),
                           "users": users[:20]})
            else:
                a = Alert(
                    "SSH-SPRAY", "Password Spraying", "high", ip,
                    "Password spraying from %s" % ip,
                    "%d login attempts across %d distinct usernames from one IP."
                    % (len(cluster), len(users)),
                    ["T1110", "T1110.003"], "ssh-spray",
                    _evidence(cluster), start, end,
                    extra={"distinct_users": len(users), "users": users[:20]})
            a.evidence_count = len(cluster)
            alerts.append(a)
    return alerts


def ssh_compromise(events):
    """Failures from an IP immediately followed by a success = likely compromise."""
    alerts = []
    ssh = _by_ip(events, "ssh", lambda e: e.get("outcome") in ("fail", "success"))
    for ip, evs in ssh.items():
        recent_fails = deque()           # (epoch, event)
        for ev in evs:
            t = ev.epoch
            while recent_fails and t - recent_fails[0][0] > C.COMPROMISE_WINDOW_S:
                recent_fails.popleft()
            if ev.get("outcome") == "fail":
                recent_fails.append((t, ev))
            elif ev.get("outcome") == "success":
                if len(recent_fails) >= C.COMPROMISE_MIN_FAILS:
                    group = [e for _, e in recent_fails] + [ev]
                    start, end = group[0].ts, ev.ts
                    user = ev.get("user")
                    a = Alert(
                        "SSH-COMPROMISE", "Likely Account Compromise", "critical", ip,
                        "Possible SSH compromise of '%s' from %s" % (user, ip),
                        "%d failed attempts were followed by a SUCCESSFUL login as "
                        "'%s' from the same IP - the guessing likely worked."
                        % (len(recent_fails), user),
                        ["T1110", "T1078"], "ssh-compromise",
                        _evidence(group), start, end,
                        extra={"user": user, "preceding_fails": len(recent_fails),
                               "success_ts": ev.ts.isoformat()})
                    a.evidence_count = len(group)
                    alerts.append(a)
                    recent_fails.clear()
    return alerts


def ssh_offhours_admin(events):
    alerts = []
    lo, hi = C.BUSINESS_HOURS
    for ev in events:
        if ev.kind != "ssh" or ev.get("outcome") != "success":
            continue
        user = (ev.get("user") or "").lower()
        if user not in C.ADMIN_USERS:
            continue
        wd = ev.ts.weekday()
        off = not (lo <= ev.ts.hour < hi)
        weekend = C.WEEKEND_IS_OFF_HOURS and wd >= 5
        if off or weekend:
            when = "weekend" if weekend and not off else "outside business hours"
            a = Alert(
                "SSH-OFFHOURS", "Off-Hours Admin Login", "high", ev.src,
                "Off-hours admin login as '%s' from %s" % (user, ev.src),
                "Privileged account '%s' logged in at %s (%s)."
                % (user, ev.ts.strftime("%a %H:%M"), when),
                ["T1078"], "ssh-offhours",
                [ev.raw], ev.ts, ev.ts,
                extra={"user": user, "hour": ev.ts.hour, "weekday": wd})
            a.evidence_count = 1
            alerts.append(a)
    return alerts


def sudo_escalation(events, prior_alerts):
    """Flag sudo-to-root tied to a recent suspicious login by the same user,
    or sudo touching sensitive files."""
    alerts = []
    # index suspicious logins: user -> list of (epoch, src)
    suspicious = {}
    for a in prior_alerts:
        if a.rule in ("SSH-COMPROMISE", "SSH-OFFHOURS"):
            u = (a.extra.get("user") or "").lower()
            suspicious.setdefault(u, []).append((a.end.timestamp(), a.src, a))
    for ev in events:
        if ev.kind != "sudo":
            continue
        ruser = (ev.get("ruser") or "").lower()
        tuser = (ev.get("tuser") or "").lower()
        cmd = ev.get("cmd") or ""
        sensitive = any(s in cmd for s in C.SENSITIVE_FILES)
        linked = None
        for lt, lsrc, la in suspicious.get(ruser, []):
            if 0 <= ev.epoch - lt <= C.SUDO_AFTER_COMPROMISE_S:
                linked = (lsrc, la)
                break
        if linked is None and not sensitive:
            continue
        sev = "critical" if linked else "medium"
        src = linked[0] if linked else None
        detail = "User '%s' ran sudo -> '%s': %s" % (ruser, tuser, cmd[:120])
        if linked:
            detail += " (shortly after a suspicious login from %s)" % linked[0]
        elif sensitive:
            detail += " (touches a sensitive file)"
        a = Alert(
            "SUDO-ESCALATION", "Privilege Escalation via sudo", sev, src,
            "Suspicious sudo by '%s'" % ruser, detail,
            ["T1548.003"] + (["T1078"] if linked else []), "sudo-escalation",
            [ev.raw], ev.ts, ev.ts,
            extra={"ruser": ruser, "tuser": tuser, "cmd": cmd,
                   "linked_login": linked[0] if linked else None})
        a.evidence_count = 1
        alerts.append(a)
    return alerts


# --------------------------------------------------------------- firewall rules
def fw_port_scan(events):
    alerts = []
    fw = _by_ip(events, "firewall", lambda e: e.get("action") in ("DROP", "BLOCK", "REJECT", "DENY"))
    for ip, evs in fw.items():
        for cluster in cluster_by_gap(evs, C.SCAN_WINDOW_S):
            pairs = [(e.epoch, e.get("dport")) for e in cluster if e.get("dport") is not None]
            distinct_ports = max_distinct_in_window(pairs, C.SCAN_WINDOW_S)
            hosts = [(e.epoch, e.get("dst")) for e in cluster if e.get("dst")]
            distinct_hosts = max_distinct_in_window(hosts, C.SWEEP_WINDOW_S)
            start, end = _span(cluster)
            if distinct_ports >= C.SCAN_MIN_PORTS:
                ports = sorted({e.get("dport") for e in cluster if e.get("dport") is not None})
                a = Alert(
                    "FW-PORTSCAN", "Port Scan", "medium", ip,
                    "Port scan from %s" % ip,
                    "%d blocked packets touched %d distinct ports - a vertical scan."
                    % (len(cluster), len(ports)),
                    ["T1595", "T1046"], "fw-scan",
                    _evidence(cluster), start, end,
                    extra={"distinct_ports": len(ports), "ports": ports[:40]})
                a.evidence_count = len(cluster)
                alerts.append(a)
            elif distinct_hosts >= C.SWEEP_MIN_HOSTS:
                a = Alert(
                    "FW-SWEEP", "Host Sweep", "medium", ip,
                    "Network sweep from %s" % ip,
                    "%d blocked packets reached %d distinct hosts - a horizontal sweep."
                    % (len(cluster), distinct_hosts),
                    ["T1595", "T1595.001"], "fw-sweep",
                    _evidence(cluster), start, end,
                    extra={"distinct_hosts": distinct_hosts})
                a.evidence_count = len(cluster)
                alerts.append(a)
    return alerts


# --------------------------------------------------------------- web rule
def web_enumeration(events):
    alerts = []
    notfound = _by_ip(events, "web", lambda e: e.get("status") == 404)
    for ip, evs in notfound.items():
        for cluster in cluster_by_gap(evs, C.ENUM_WINDOW_S):
            times = [e.epoch for e in cluster]
            if sliding_count_trigger(times, C.ENUM_MIN_404, C.ENUM_WINDOW_S):
                start, end = _span(cluster)
                paths = [e.get("path") for e in cluster]
                a = Alert(
                    "WEB-ENUM", "Directory / Path Enumeration", "medium", ip,
                    "Path enumeration from %s" % ip,
                    "%d requests returned 404 in a short window - directory/file "
                    "brute forcing." % len(cluster),
                    ["T1595", "T1083"], "web-enum",
                    _evidence(cluster), start, end,
                    extra={"count_404": len(cluster), "sample_paths": paths[:12]})
                a.evidence_count = len(cluster)
                alerts.append(a)
    return alerts


def run(events):
    """Run every correlation rule and return a flat list of alerts."""
    alerts = []
    alerts += ssh_bruteforce(events)
    alerts += ssh_spraying(events)
    comp = ssh_compromise(events)
    offh = ssh_offhours_admin(events)
    alerts += comp
    alerts += offh
    alerts += sudo_escalation(events, comp + offh)
    alerts += fw_port_scan(events)
    alerts += web_enumeration(events)
    return alerts
