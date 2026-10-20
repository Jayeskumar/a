"""Sales dataset: CSV parsing + validation, stock-out detection and cleaning.

CSV format (header required, case-insensitive):
    date, sku, qty                      required
    stockout, promo                     optional 0/1 flags
    name, price, cost, lead_time, shelf_life, pack   optional item master columns
Dates may be YYYY-MM-DD, DD-MM-YYYY or DD/MM/YYYY.
"""
import csv
import io
import math
import re
from datetime import date, datetime, timedelta

from . import config

SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-./&]{0,39}$")
ALIASES = {
    "date": ("date", "day", "sale_date", "bill_date"),
    "sku": ("sku", "item", "item_code", "product", "product_code", "code"),
    "qty": ("qty", "quantity", "units", "sales", "units_sold"),
    "stockout": ("stockout", "stock_out", "oos"),
    "promo": ("promo", "promotion", "on_promo"),
}
MASTER_COLS = ("name", "price", "cost", "lead_time", "shelf_life", "pack")


class ValidationError(ValueError):
    """Raised for bad user input; message is safe to show to the user."""


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _num(s):
    try:
        v = float((s or "").strip().replace(",", ""))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


class Dataset:
    """Dense daily series per SKU plus item master and stock on hand."""

    def __init__(self, dates, items, qty, stockout, promo, on_hand, source,
                 baskets=None, warnings=None, stockout_given=True):
        self.dates = dates                  # list[date], continuous daily
        self.items = items                  # dict sku -> item master
        self.skus = list(items.keys())
        self.qty = qty                      # dict sku -> list[float] (raw, censored on stock-outs)
        self.stockout = stockout            # dict sku -> list[bool]
        self.promo = promo                  # dict sku -> list[int]
        self.on_hand = on_hand              # dict sku -> {"on_hand", "on_order", "assumed"}
        self.source = source
        self.baskets = baskets or []
        self.warnings = warnings or []
        self.stockout_given = stockout_given
        self.clean = {}
        self.detected = {}
        for s in self.skus:
            if not stockout_given:
                stockout[s] = detect_stockouts(qty[s])
                self.detected[s] = sum(stockout[s])
            self.clean[s] = clean_series(qty[s], stockout[s])

    @property
    def n(self):
        return len(self.dates)

    @property
    def today(self):
        return self.dates[-1] + timedelta(days=1)


def detect_stockouts(q):
    """Flag zero-sales days that are implausible given recent demand (Poisson P(0) < 1%)."""
    flags = [False] * len(q)
    limit = -math.log(config.STOCKOUT_P0)   # P(0) = exp(-lam) < p0  <=>  lam > -ln p0
    for t in range(len(q)):
        if q[t] > 0 or t < 14:
            continue
        window = [q[i] for i in range(max(0, t - 28), t) if not flags[i]]
        if len(window) >= 7 and sum(window) / len(window) > limit:
            flags[t] = True
    return flags


def clean_series(q, flags):
    """Replace censored (stock-out) days by the mean of the same weekday in the last 4 weeks."""
    out = list(map(float, q))
    good = [i for i in range(len(q)) if not flags[i]]
    overall = sum(out[i] for i in good) / len(good) if good else 0.0
    for t in range(len(q)):
        if not flags[t]:
            continue
        same = [out[t - 7 * k] for k in range(1, 5) if t - 7 * k >= 0 and not flags[t - 7 * k]]
        if not same:
            recent = [out[i] for i in range(max(0, t - 28), t) if not flags[i]]
            same = recent or [overall]
        out[t] = max(out[t] if q[t] else 0.0, sum(same) / len(same))
    return out


def _header_map(header):
    norm = [re.sub(r"[^a-z_]", "", (h or "").strip().lower().replace(" ", "_")) for h in header]
    found = {}
    for key, names in ALIASES.items():
        for i, h in enumerate(norm):
            if h in names and key not in found:
                found[key] = i
    for col in MASTER_COLS:
        if col in norm:
            found[col] = norm.index(col)
    return found


def parse_csv(text, base_items=None, base_on_hand=None, source="upload", baskets=None):
    """Validate CSV text and build a Dataset. Raises ValidationError with a readable message."""
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("CSV is empty")
    if len(text.encode("utf-8")) > config.MAX_UPLOAD_BYTES:
        raise ValidationError("CSV larger than %d MB" % (config.MAX_UPLOAD_BYTES // (1024 * 1024)))
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise ValidationError("CSV has no header row")
    cols = _header_map(header)
    missing = [k for k in ("date", "sku", "qty") if k not in cols]
    if missing:
        raise ValidationError("missing required column(s): %s (found: %s)"
                              % (", ".join(missing), ", ".join(h.strip() for h in header[:12])))
    errors, agg, flags, promos, master = [], {}, {}, {}, {}
    rows = 0
    for lineno, row in enumerate(reader, start=2):
        if not row or all(not c.strip() for c in row):
            continue
        rows += 1
        if rows > config.MAX_ROWS:
            raise ValidationError("too many rows (limit %d)" % config.MAX_ROWS)

        def cell(key):
            i = cols.get(key)
            return row[i] if i is not None and i < len(row) else ""

        d = parse_date(cell("date"))
        sku = cell("sku").strip()
        q = _num(cell("qty"))
        problem = None
        if d is None:
            problem = "bad date %r" % cell("date")[:20]
        elif not SKU_RE.match(sku):
            problem = "bad sku %r" % sku[:20]
        elif q is None:
            problem = "qty is not a number"
        elif q < 0:
            problem = "negative qty (returns are not supported)"
        elif q > 1e6:
            problem = "qty unrealistically large"
        if problem:
            if len(errors) < 1000:
                errors.append("line %d: %s" % (lineno, problem))
            continue
        key = (d, sku)
        agg[key] = agg.get(key, 0.0) + q
        if cell("stockout").strip() in ("1", "true", "yes", "y"):
            flags[key] = True
        if cell("promo").strip() in ("1", "true", "yes", "y"):
            promos[key] = 1
        m = master.setdefault(sku, {})
        for col in MASTER_COLS:
            v = cell(col).strip()
            if v and col not in m:
                m[col] = v
    if rows == 0:
        raise ValidationError("CSV has a header but no data rows")
    if errors and len(errors) > max(5, rows * 0.05):
        raise ValidationError("%d of %d rows are invalid, e.g. %s" % (len(errors), rows, "; ".join(errors[:3])))
    if not agg:
        raise ValidationError("no valid rows")

    all_dates = sorted({k[0] for k in agg})
    start, end = all_dates[0], all_dates[-1]
    warnings = ["skipped %d invalid row(s): %s" % (len(errors), "; ".join(errors[:3]))] if errors else []
    span = (end - start).days + 1
    if span > config.MAX_HISTORY_DAYS:
        start = end - timedelta(days=config.MAX_HISTORY_DAYS - 1)
        warnings.append("kept only the last %d days" % config.MAX_HISTORY_DAYS)
        span = config.MAX_HISTORY_DAYS
    if span < config.MIN_HISTORY_DAYS:
        raise ValidationError("need at least %d days of history for backtesting (got %d)"
                              % (config.MIN_HISTORY_DAYS, span))
    dates = [start + timedelta(days=i) for i in range(span)]
    pos = {d: i for i, d in enumerate(dates)}

    totals = {}
    for (d, s), q in agg.items():
        if d in pos:
            totals[s] = totals.get(s, 0.0) + q
    skus = sorted(totals, key=lambda s: -totals[s])
    if len(skus) > config.MAX_SKUS:
        warnings.append("kept the %d highest-volume SKUs of %d" % (config.MAX_SKUS, len(skus)))
        skus = skus[:config.MAX_SKUS]
    skus = [s for s in skus if totals[s] > 0]
    if not skus:
        raise ValidationError("all quantities are zero")
    if base_items:   # keep the familiar catalogue order for known SKUs
        order = {s: i for i, s in enumerate(base_items)}
        skus.sort(key=lambda s: (order.get(s, 10 ** 6), -totals[s]))

    qty, so, pr, items, on_hand = {}, {}, {}, {}, {}
    filled = 0
    assumed = []
    for s in skus:
        qty[s] = [0.0] * span
        so[s] = [False] * span
        pr[s] = [0] * span
    for (d, s), q in agg.items():
        if s in qty and d in pos:
            qty[s][pos[d]] = q
    for s in skus:
        seen = sum(1 for d in dates if (d, s) in agg)
        filled += span - seen
        for (d, s2) in flags:
            if s2 == s and d in pos:
                so[s][pos[d]] = True
        for (d, s2) in promos:
            if s2 == s and d in pos:
                pr[s][pos[d]] = 1
        items[s] = _item_for(s, master.get(s, {}), (base_items or {}).get(s), assumed)
        if base_on_hand and s in base_on_hand:
            on_hand[s] = dict(base_on_hand[s], assumed=False)
        else:
            m28 = sum(qty[s][-28:]) / 28.0
            on_hand[s] = {"on_hand": int(round(m28 * 7)), "on_order": 0, "assumed": True}
    if filled:
        warnings.append("%d missing date/SKU combinations treated as zero sales" % filled)
    if assumed:
        warnings.append("default price/cost/lead time assumed for %d SKU(s): %s"
                        % (len(assumed), ", ".join(assumed[:6]) + ("..." if len(assumed) > 6 else "")))
    if any(v["assumed"] for v in on_hand.values()):
        warnings.append("stock on hand unknown - assumed 7 days of cover (edit it in the reorder table)")
    stockout_given = "stockout" in cols
    return Dataset(dates, items, qty, so, pr, on_hand, source, baskets=baskets,
                   warnings=warnings, stockout_given=stockout_given)


def _item_for(sku, cols, base, assumed):
    if base:
        item = dict(base)
    else:
        item = dict(config.DEFAULT_ITEM, sku=sku, name=sku)
        assumed.append(sku)
    item["sku"] = sku
    if cols.get("name"):
        item["name"] = cols["name"][:60]
    for col, cast, lo, hi in (("price", float, 0.01, 1e6), ("cost", float, 0.01, 1e6),
                              ("lead_time", int, 0, 90), ("shelf_life", int, 1, 3650), ("pack", int, 1, 10000)):
        v = _num(cols.get(col, ""))
        if v is not None and lo <= v <= hi:
            item[col] = cast(v)
    if item["cost"] >= item["price"]:
        item["cost"] = round(item["price"] * 0.8, 2)
    return item


def parse_baskets(text):
    """bill,date,items(semicolon separated) -> list of item sets."""
    out = []
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    for row in reader:
        if len(row) >= 3 and row[2].strip():
            out.append(frozenset(x.strip() for x in row[2].split(";") if x.strip()))
    return out


def weekly_totals(series, weeks=52):
    """Sum of the last `weeks` complete 7-day blocks (aligned to the end of the series)."""
    n = len(series)
    k = min(weeks, n // 7)
    return [sum(series[n - 7 * (i + 1): n - 7 * i]) for i in range(k)][::-1]


def to_date(s):
    d = parse_date(s)
    if d is None:
        raise ValidationError("bad date")
    return d


__all__ = ["Dataset", "ValidationError", "parse_csv", "parse_baskets", "detect_stockouts",
           "clean_series", "weekly_totals", "date"]
