"""Inventory optimisation: safety stock, reorder point, EOQ, perishable caps, reorder list.

Timing: stock is reviewed every morning; an order placed on day t arrives on the morning of
day t + L. If we do not order today the next chance is tomorrow, so stock on hand must cover
the protection interval P = L + R days (R = 1 review day).

    sigma_P = sqrt(P * sigma_e^2 + d^2 * sigma_L^2)     forecast error + lead-time variability
    SS      = z * sigma_P,  z = inv_norm(service level)
    ROP     = sum of the daily forecast over P days + SS
    EOQ     = sqrt(2 D S / H),  H = unit cost * holding rate
    Q*      = min(EOQ, demand sellable within shelf life, MAX_COVER_DAYS of demand), case-rounded
    order   = (ROP + Q*) - inventory position, when inventory position <= ROP
"""
import math

from . import config
from .stats import expected_shortage, inv_norm, norm_loss, prob_exceed


def eoq(annual_demand, order_cost, holding_cost):
    """Economic order quantity sqrt(2DS/H) (0 when there is no demand)."""
    if annual_demand <= 0 or holding_cost <= 0:
        return 0.0
    return math.sqrt(2.0 * annual_demand * order_cost / holding_cost)


def safety_stock(z, sigma_e, days, d_avg=0.0, lead_sd=0.0):
    """(SS, sigma over the protection interval) for daily forecast-error sigma_e."""
    sigma_p = math.sqrt(max(days, 0) * sigma_e ** 2 + (d_avg * lead_sd) ** 2)
    return z * sigma_p, sigma_p


def reorder_point(protection_demand, ss):
    return protection_demand + ss


def ceil_pack(q, pack):
    pack = max(1, int(pack))
    return int(math.ceil(max(0.0, q) / pack - 1e-9)) * pack


def floor_pack(q, pack):
    pack = max(1, int(pack))
    return int(math.floor(max(0.0, q) / pack + 1e-9)) * pack


def window_sum(fc, start, days):
    """Sum of forecast over [start, start+days), extrapolating with the mean beyond the horizon."""
    avg = sum(fc) / len(fc) if fc else 0.0
    total = 0.0
    for i in range(start, start + days):
        total += fc[i] if i < len(fc) else avg
    return total


def policy(item, fc, sigma_e, service=None):
    """Policy numbers for one SKU given its daily forecast (fc[0] = today) and error sigma."""
    service = config.SERVICE_LEVEL if service is None else service
    z = inv_norm(service)
    L = max(1, int(item["lead_time"]))
    P = L + config.REVIEW_DAYS
    d_avg = sum(fc) / len(fc) if fc else 0.0
    lead_demand = window_sum(fc, 0, L)
    prot_demand = window_sum(fc, 0, P)
    ss, sigma_p = safety_stock(z, sigma_e, P, d_avg, item.get("lead_sd", 0.0))
    _, sigma_l = safety_stock(z, sigma_e, L, d_avg, item.get("lead_sd", 0.0))
    rop = reorder_point(prot_demand, ss)
    annual = d_avg * 365.0
    h_cost = item["cost"] * config.HOLDING_RATE
    q_eoq = eoq(annual, config.ORDER_COST, h_cost)
    perishable = item["shelf_life"] <= config.PERISHABLE_DAYS
    usable = max(1, int(item["shelf_life"] * config.SELLABLE_FRACTION))
    shelf_cap = window_sum(fc, L, usable)
    cover_cap = d_avg * config.MAX_COVER_DAYS
    q, binding = q_eoq, "EOQ"
    if perishable and shelf_cap < q:
        q, binding = shelf_cap, "shelf life"
    if cover_cap < q:
        q, binding = cover_cap, "%d-day cover cap" % config.MAX_COVER_DAYS
    pack = item.get("pack", 1)
    q_star = max(pack, ceil_pack(q, pack) if binding == "EOQ" else floor_pack(q, pack))
    return {
        "z": z, "service": service, "lead_time": L, "protection_days": P, "d_avg": d_avg,
        "lead_demand": lead_demand, "prot_demand": prot_demand, "sigma_e": sigma_e,
        "sigma_p": sigma_p, "sigma_l": sigma_l, "ss": ss, "rop": rop,
        "annual_demand": annual, "holding_cost_unit": h_cost, "order_cost": config.ORDER_COST, "eoq": q_eoq,
        "q_star": q_star, "q_binding": binding, "perishable": perishable,
        "usable_days": usable, "shelf_cap": shelf_cap,
    }


def order_quantity(p, ip, pack):
    """Order up to ROP + Q* when the inventory position is at or below the reorder point."""
    if ip > p["rop"]:
        return 0
    qty = ceil_pack(p["rop"] + p["q_star"] - ip, pack)
    if p["perishable"]:
        # leftover at delivery + this order must sell within the usable shelf life (+ safety stock)
        cap = p["shelf_cap"] + p["ss"] - max(0.0, ip - p["lead_demand"])
        qty = min(qty, max(pack, floor_pack(cap, pack)))
    return max(qty, pack)


def plan_item(item, fc, sigma_e, on_hand, on_order=0, service=None, model_name=""):
    """One row of today's reorder list with risk, rupee impact and a plain-English reason."""
    p = policy(item, fc, sigma_e, service)
    pack = item.get("pack", 1)
    ip = on_hand + on_order
    qty = order_quantity(p, ip, pack)
    # Skip today -> stock must last the whole protection interval.
    risk_skip = prob_exceed(ip, p["prot_demand"], p["sigma_p"])
    short_skip = expected_shortage(ip, p["prot_demand"], p["sigma_p"])
    # Order today -> exposed only until the delivery arrives (L days).
    if qty:
        risk_order = prob_exceed(ip, p["lead_demand"], p["sigma_l"])
        short_order = min(short_skip, expected_shortage(ip, p["lead_demand"], p["sigma_l"]))
    else:
        risk_order, short_order = risk_skip, short_skip
    price, cost = item["price"], item["cost"]
    days_cover = ip / p["d_avg"] if p["d_avg"] > 0 else None
    if qty:
        status = "urgent" if on_hand < p["lead_demand"] else "order"
    elif ip > p["rop"] + 2 * p["q_star"] and (days_cover or 0) > 21:
        status = "overstock"
    else:
        status = "ok"
    excess_units = max(0.0, ip - (p["rop"] + p["q_star"])) if status == "overstock" else 0.0
    return {
        "sku": item["sku"], "name": item.get("name", item["sku"]), "category": item.get("category", ""),
        "status": status, "on_hand": on_hand, "on_order": on_order,
        "lead_time": p["lead_time"], "protection_days": p["protection_days"],
        "lead_demand": round(p["lead_demand"], 1), "prot_demand": round(p["prot_demand"], 1),
        "ss": round(p["ss"], 1), "rop": round(p["rop"], 1),
        "eoq": round(p["eoq"], 1), "q_star": p["q_star"], "q_binding": p["q_binding"], "pack": pack,
        "order_qty": qty, "order_value": round(qty * cost, 2),
        "days_cover": round(days_cover, 1) if days_cover is not None else None,
        "risk_skip": round(risk_skip, 4), "risk_order": round(risk_order, 4),
        "lost_units_skip": round(short_skip, 2),
        "sales_at_risk": round(short_skip * price, 2),
        "sales_saved": round((short_skip - short_order) * price, 2),
        "margin_saved": round((short_skip - short_order) * (price - cost), 2),
        "excess_value": round(excess_units * cost, 2),
        "z": round(p["z"], 3), "sigma_e": round(p["sigma_e"], 2), "sigma_p": round(p["sigma_p"], 2),
        "d_avg": round(p["d_avg"], 2), "perishable": p["perishable"], "shelf_life": item["shelf_life"],
        "reason": explain(item, p, ip, qty, status, model_name),
    }


def _q(v):
    """Readable quantity: one decimal for small numbers, whole units otherwise."""
    return "%.1f" % v if abs(v) < 10 else "%.0f" % v


def explain(item, p, ip, qty, status, model_name):
    P = p["protection_days"]
    parts = ["Forecast demand %s over the next %d days (lead time %d + 1 review day, %s)"
             % (_q(p["prot_demand"]), P, p["lead_time"], model_name or "forecast"),
             "+ safety stock %s (z %.2f x sigma %.1f)" % (_q(p["ss"]), p["z"], p["sigma_p"]),
             "= reorder point %s." % _q(p["rop"])]
    if qty:
        parts.append("Stock %d is at or below it, so order %d (up to ROP + Q*, Q* = %d set by %s, case of %d)."
                     % (ip, qty, p["q_star"], p["q_binding"], item.get("pack", 1)))
        if p["perishable"]:
            parts.append("Perishable: capped to what sells within %d of %d shelf-life days."
                         % (p["usable_days"], item["shelf_life"]))
        if status == "urgent":
            parts.append("Stock will not last the %d-day lead time - consider a same-day pickup." % p["lead_time"])
    elif status == "overstock":
        parts.append("Stock %d is far above ROP + Q* (%s): pause orders, consider a promotion."
                     % (ip, _q(p["rop"] + p["q_star"])))
    else:
        parts.append("Stock %d is above it - no order needed today." % ip)
    return " ".join(parts)


def tradeoff(items_fc, levels=None):
    """Yearly cost of safety stock vs expected stock-outs across service levels.

    items_fc: list of (item, forecast, sigma_e). Expected lost units per year
    = (D / Q*) order cycles x sigma_P x G(z); cost = lost units x unit margin.
    """
    levels = levels or config.SERVICE_GRID
    out = []
    for s in levels:
        hold = lost_cost = lost_units = demand = ss_value = 0.0
        for item, fc, sig in items_fc:
            p = policy(item, fc, sig, s)
            cycles = p["annual_demand"] / p["q_star"] if p["q_star"] else 0.0
            lu = cycles * p["sigma_p"] * norm_loss(p["z"])
            hold += p["ss"] * p["holding_cost_unit"]
            lost_units += lu
            lost_cost += lu * (item["price"] - item["cost"])
            demand += p["annual_demand"]
            ss_value += p["ss"] * item["cost"]
        out.append({"service": s, "holding_cost": round(hold, 0), "stockout_cost": round(lost_cost, 0),
                    "total_cost": round(hold + lost_cost, 0),
                    "fill_rate": round(1 - lost_units / demand, 5) if demand else 1.0,
                    "lost_units": round(lost_units, 1), "ss_value": round(ss_value, 0)})
    best = min(out, key=lambda r: r["total_cost"])
    return {"points": out, "optimum": best["service"]}


def optimal_service(item, q_star, annual_demand):
    """Cost-optimal cycle service level with lost sales: 1 - H*Q / (H*Q + D*margin)."""
    h = item["cost"] * config.HOLDING_RATE
    m = item["price"] - item["cost"]
    if annual_demand <= 0 or m <= 0:
        return config.SERVICE_LEVEL
    p_out = h * q_star / (h * q_star + annual_demand * m)
    return max(0.5, min(0.999, 1.0 - p_out))
