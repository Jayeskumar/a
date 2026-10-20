"""Statistical anomaly detection - all from scratch, no numpy.

Two signals:
  1. Per-IP request-rate spikes. We keep an EWMA mean and EWMA variance of each
     IP's requests-per-active-minute and z-score the latest minute. An IP with
     too little history is compared against the site-wide per-IP-minute baseline
     instead, so a brand-new IP that opens with a burst is still caught.
  2. Novelty. A user-agent first seen only after warm-up and then used heavily by
     a single IP, or many never-before-seen path shapes from one IP in a window.

EWMA update (per new value x):
    delta  = x - mean
    mean  += alpha * delta
    var    = (1 - alpha) * (var + alpha * delta * delta)      # West's EWMVar
    std    = sqrt(var)
    z      = (x - mean_before_update) / max(std, floor)
"""

import math
from collections import OrderedDict, defaultdict

from . import config as C
from .alerts import Alert


def _minute(ev):
    return int(ev.epoch // 60) * 60


def _norm_path(path):
    """Collapse a URL path to a shape so /user/12 and /user/99 count as one."""
    out = []
    for seg in (path or "").split("?")[0].split("/"):
        if not seg:
            continue
        if seg.isdigit() or len(seg) > 24:
            out.append("*")
        else:
            out.append(seg.lower())
    return "/" + "/".join(out)


# --------------------------------------------------------------- rate
def rate_anomalies(events):
    web = [e for e in events if e.kind == "web" and e.src]
    if not web:
        return []
    # per (ip, minute) -> events
    buckets = defaultdict(list)
    for e in web:
        buckets[(e.src, _minute(e))].append(e)

    per_ip = defaultdict(list)       # ip -> [(minute, count, events)]
    all_counts = []
    for (ip, minute), evs in buckets.items():
        per_ip[ip].append((minute, len(evs), evs))
        all_counts.append(len(evs))

    gmean = sum(all_counts) / float(len(all_counts))
    gvar = sum((c - gmean) ** 2 for c in all_counts) / float(len(all_counts))
    gstd = max(math.sqrt(gvar), C.RATE_SIGMA_FLOOR)

    alerts = []
    for ip, series in per_ip.items():
        series.sort()
        worst = None            # (z, count, minute, events, baseline)
        if len(series) >= C.IP_HISTORY_MIN_MINUTES:
            mean = series[0][1]
            var = 0.0
            for minute, count, evs in series[1:]:
                std = max(math.sqrt(var), C.RATE_SIGMA_FLOOR)
                z = (count - mean) / std
                if count >= C.RATE_MIN_COUNT and z >= C.Z_THRESHOLD:
                    if worst is None or z > worst[0]:
                        worst = (z, count, minute, evs, mean)
                delta = count - mean
                mean += C.EWMA_ALPHA * delta
                var = (1 - C.EWMA_ALPHA) * (var + C.EWMA_ALPHA * delta * delta)
        else:
            for minute, count, evs in series:
                if count < C.RATE_MIN_COUNT:
                    continue
                z = (count - gmean) / gstd
                if z >= C.Z_THRESHOLD and (worst is None or z > worst[0]):
                    worst = (z, count, minute, evs, gmean)
        if worst:
            z, count, minute, evs, base = worst
            # don't alert on well-behaved known crawlers
            ua = (evs[0].get("ua") or "").lower()
            if any(b in ua for b in C.KNOWN_GOOD_BOTS):
                continue
            start, end = evs[0].ts, evs[-1].ts
            a = Alert(
                "ANOM-RATE", "Request-Rate Anomaly", "medium", ip,
                "Traffic spike from %s" % ip,
                "%d requests in one minute vs an expected ~%.1f (z=%.1f) - a sudden "
                "burst from this IP." % (count, base, z),
                ["T1595"], "anomaly-rate",
                [e.raw for e in evs[:C.EVIDENCE_CAP]], start, end,
                extra={"peak_rpm": count, "baseline": round(base, 1), "z": round(z, 2)})
            a.evidence_count = count
            alerts.append(a)
    return alerts


# --------------------------------------------------------------- novelty
def novelty(events):
    web = [e for e in events if e.kind == "web"]
    alerts = []

    # ---- rare user-agent novelty ----
    seen_ua = set()
    ua_after_warmup = defaultdict(lambda: defaultdict(int))   # ua -> ip -> count
    ua_first_raw = {}
    for i, e in enumerate(web):
        ua = e.get("ua") or "-"
        if i < C.NOVELTY_WARMUP_EVENTS:
            seen_ua.add(ua)
            continue
        if ua not in seen_ua:
            ua_after_warmup[ua][e.src] += 1
            ua_first_raw.setdefault((ua, e.src), e)
    for ua, ips in ua_after_warmup.items():
        for ip, cnt in ips.items():
            if cnt < C.NOVEL_UA_MIN_REQUESTS:
                continue
            if any(b in ua.lower() for b in C.KNOWN_GOOD_BOTS):
                continue
            ref = ua_first_raw[(ua, ip)]
            a = Alert(
                "ANOM-UA", "Novel User-Agent", "low", ip,
                "Unseen user-agent from %s" % ip,
                "A user-agent never seen during the baseline made %d requests from "
                "one IP: %s" % (cnt, ua[:80]),
                ["T1595"], "anomaly-novelty",
                [ref.raw], ref.ts, ref.ts,
                extra={"ua": ua, "requests": cnt})
            a.evidence_count = cnt
            alerts.append(a)

    # ---- path-shape novelty burst ----
    seen_paths = set()
    per_ip_novel = defaultdict(list)
    for i, e in enumerate(web):
        shape = _norm_path(e.get("path"))
        if i < C.NOVELTY_WARMUP_EVENTS:
            seen_paths.add(shape)
            continue
        if shape not in seen_paths:
            per_ip_novel[e.src].append(e)
    for ip, evs in per_ip_novel.items():
        evs.sort(key=lambda x: x.epoch)
        shapes = {_norm_path(e.get("path")) for e in evs}
        if len(shapes) < C.NOVEL_PATH_MIN:
            continue
        # require them clustered in a window
        times = [e.epoch for e in evs]
        burst = any(times[j + C.NOVEL_PATH_MIN - 1] - times[j] <= C.NOVEL_PATH_WINDOW_S
                    for j in range(0, max(0, len(times) - C.NOVEL_PATH_MIN + 1)))
        if not burst:
            continue
        a = Alert(
            "ANOM-PATH", "Novel-Path Burst", "low", ip,
            "Many unseen paths from %s" % ip,
            "%d never-before-seen path shapes requested from one IP in a short "
            "window - exploratory probing." % len(shapes),
            ["T1595", "T1083"], "anomaly-novelty",
            [e.raw for e in evs[:C.EVIDENCE_CAP]], evs[0].ts, evs[-1].ts,
            extra={"novel_shapes": len(shapes)})
        a.evidence_count = len(evs)
        alerts.append(a)
    return alerts


# --------------------------------------------------------------- global RPM chart
def global_rpm(events):
    """Requests-per-minute series with EWMA baseline + anomaly markers, for the
    dashboard chart. Counts web + firewall + ssh events per minute."""
    if not events:
        return {"points": []}
    counts = OrderedDict()
    lo = min(e.epoch for e in events)
    hi = max(e.epoch for e in events)
    m = int(lo // 60) * 60
    while m <= hi:
        counts[m] = 0
        m += 60
    for e in events:
        counts[int(e.epoch // 60) * 60] += 1

    points = []
    mean = None
    var = 0.0
    for i, (minute, c) in enumerate(counts.items()):
        if mean is None:
            mean, base, z, anom = c, c, 0.0, False
        else:
            std = max(math.sqrt(var), C.GLOBAL_RPM_FLOOR)
            z = (c - mean) / std
            base = mean
            anom = (i >= C.GLOBAL_RPM_WARMUP and z >= C.GLOBAL_RPM_Z
                    and c >= C.RATE_MIN_COUNT)
            delta = c - mean
            mean += C.EWMA_ALPHA * delta
            var = (1 - C.EWMA_ALPHA) * (var + C.EWMA_ALPHA * delta * delta)
        points.append({"t": minute, "count": c, "baseline": round(base, 1),
                       "z": round(z, 2), "anomaly": bool(anom)})
    return {"points": points}
