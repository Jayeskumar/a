"""Replay the last 90 days of demand under two ordering policies and compare outcomes.

Daily loop (same mechanics for both policies, so the comparison is fair):
  morning : deliveries arrive (each delivery is a batch with its own expiry date)
            review stock -> maybe place an order (arrives after the supplier lead time)
  day     : customers buy, oldest batch first (FIFO); unmet demand is a lost sale
  evening : batches past their shelf life are thrown away; holding cost on what is left

Policies
  gut-feel   : fixed standing order sized from recent average demand +10% - weekly on Monday
               (daily for items with <= 7 days shelf life); skipped if the shelf still holds
               at least one order's worth. Never adapts to trend, festivals or variability.
  StockSense : daily review with forecast-driven reorder point, safety stock, EOQ and
               shelf-life cap; forecasts refreshed weekly using only data known at the time.
Actual supplier lead times wobble around the nominal value (same random draws for both).
"""
import math
import random
from collections import deque

from . import config
from .inventory import ceil_pack, order_quantity, policy


def actual_lead_time(item, t):
    if item.get("lead_sd", 0) <= 0:
        return max(1, int(item["lead_time"]))
    rng = random.Random("%s-%d" % (item["sku"], t))
    u1, u2 = max(rng.random(), 1e-12), rng.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return max(1, int(round(item["lead_time"] + item["lead_sd"] * z)))


def gut_quantity(item, pre_demand):
    avg = sum(pre_demand) / len(pre_demand) if pre_demand else 0.0
    daily = item["shelf_life"] <= 7
    days = 1 if daily else 7
    return max(item.get("pack", 1), ceil_pack(avg * days * config.GUT_BUFFER, item.get("pack", 1))), daily


def run(item, demand, weekdays, kind, warmup, forecasts=None, sigma=0.0, service=None,
        gut_qty=0, gut_daily=False, init_stock=0):
    shelf = max(1, int(item["shelf_life"]))
    pack = item.get("pack", 1)
    price, cost = item["price"], item["cost"]
    batches = deque()            # [qty, last_sellable_day]
    if init_stock > 0:
        batches.append([init_stock, shelf - 1])
    pipeline = []                # [arrive_day, qty]
    refits = sorted(forecasts) if forecasts else []
    m = dict(stockout_days=0, lost_units=0, lost_sales=0.0, lost_margin=0.0, expired_units=0,
             waste_cost=0.0, holding_cost=0.0, orders=0, ordering_cost=0.0, demand=0, served=0,
             inv_value_sum=0.0)
    traj = {"on_hand": [], "order": [], "lost": [], "expired": [], "demand": []}
    h_daily = cost * config.HOLDING_RATE / 365.0
    for t, d in enumerate(demand):
        measure = t >= warmup
        # morning: deliveries
        arrived = [p for p in pipeline if p[0] == t]
        for p in arrived:
            batches.append([p[1], t + shelf - 1])
        pipeline = [p for p in pipeline if p[0] != t]
        on_hand = sum(b[0] for b in batches)
        ip = on_hand + sum(p[1] for p in pipeline)
        qty = 0
        if kind == "gut":
            if (gut_daily or weekdays[t] == 0) and on_hand < gut_qty:
                qty = gut_qty
        else:
            r = max(x for x in refits if x <= t)
            fc = forecasts[r][t - r:]
            pol = policy(item, fc, sigma, service)
            qty = order_quantity(pol, ip, pack)
        if qty:
            pipeline.append([t + actual_lead_time(item, t), qty])
        # day: FIFO sales
        need, served = d, 0
        while need > 0 and batches:
            take = min(need, batches[0][0])
            batches[0][0] -= take
            need -= take
            served += take
            if batches[0][0] == 0:
                batches.popleft()
        # evening: expiry
        expired = sum(b[0] for b in batches if b[1] <= t)
        if expired:
            batches = deque(b for b in batches if b[1] > t)
        end_stock = sum(b[0] for b in batches)
        if measure:
            m["demand"] += d
            m["served"] += served
            if need > 0:
                m["stockout_days"] += 1
                m["lost_units"] += need
                m["lost_sales"] += need * price
                m["lost_margin"] += need * (price - cost)
            m["expired_units"] += expired
            m["waste_cost"] += expired * cost
            m["holding_cost"] += end_stock * h_daily
            m["inv_value_sum"] += end_stock * cost
            if qty:
                m["orders"] += 1
                m["ordering_cost"] += config.ORDER_COST
            traj["on_hand"].append(end_stock)
            traj["order"].append(qty)
            traj["lost"].append(need)
            traj["expired"].append(expired)
            traj["demand"].append(d)
    days = max(1, len(demand) - warmup)
    m["avg_inventory_value"] = m.pop("inv_value_sum") / days
    m["fill_rate"] = m["served"] / m["demand"] if m["demand"] else 1.0
    m["total_cost"] = m["holding_cost"] + m["ordering_cost"] + m["waste_cost"] + m["lost_margin"]
    return m, traj


SUM_KEYS = ("stockout_days", "lost_units", "lost_sales", "lost_margin", "expired_units", "waste_cost",
            "holding_cost", "orders", "ordering_cost", "demand", "served", "avg_inventory_value", "total_cost")


def aggregate(results):
    tot = {k: 0.0 for k in SUM_KEYS}
    for r in results:
        for k in SUM_KEYS:
            tot[k] += r[k]
    tot["fill_rate"] = tot["served"] / tot["demand"] if tot["demand"] else 1.0
    return {k: (round(v, 4) if k == "fill_rate" else round(v, 2)) for k, v in tot.items()}
