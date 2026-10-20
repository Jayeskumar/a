"""Festival calendar features (approximate dates live in config.FESTIVALS)."""
from datetime import timedelta

from . import config


def festival_features(d, festivals=None):
    """Return {group: shape value} for date d; overlapping windows add up."""
    out = {g: 0.0 for g in config.FESTIVAL_GROUPS}
    for _name, group, fd in (festivals or config.FESTIVALS):
        off = (d - fd).days
        w = config.FEST_SHAPE.get(off)
        if w:
            out[group] += w
    return out


def feature_rows(dates):
    """List (one per date) of [diwali, pongal, other] shape values."""
    rows = []
    for d in dates:
        f = festival_features(d)
        rows.append([f[g] for g in config.FESTIVAL_GROUPS])
    return rows


def label_for(d):
    """Name of a festival whose window covers d (for chart annotations), else ''."""
    for name, _group, fd in config.FESTIVALS:
        off = (d - fd).days
        if off in config.FEST_SHAPE:
            return name
    return ""


def upcoming(today, days=45):
    """Festivals whose day falls within [today, today + days]."""
    out = []
    for name, group, fd in config.FESTIVALS:
        delta = (fd - today).days
        if 0 <= delta <= days:
            window_start = fd + timedelta(days=min(config.FEST_SHAPE))
            out.append({"name": name, "group": group, "date": fd.isoformat(),
                        "days_away": delta, "window_start": window_start.isoformat()})
    return out


def in_range(start, end):
    """Festivals whose day is within [start, end]."""
    return [{"name": n, "group": g, "date": fd.isoformat()}
            for n, g, fd in config.FESTIVALS if start <= fd <= end]


def parse_iso(s):
    from datetime import date
    return date.fromisoformat(s)
