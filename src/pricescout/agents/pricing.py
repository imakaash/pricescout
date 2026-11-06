"""Pricing recommendations: deterministic rules + demand model for the numbers.

The LLM never sets a price. It only explains the recommendation afterwards. Every
recommendation comes with an expected weekly profit impact from the same demand model the
simulation uses, and must respect the margin floor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from pricescout.internal.simulate import charm_price

SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    week             DATE NOT NULL,
    sku              VARCHAR NOT NULL,
    title            VARCHAR,
    action           VARCHAR NOT NULL,   -- lower | raise
    reason_code      VARCHAR NOT NULL,
    current_price    DECIMAL(10, 2),
    new_price        DECIMAL(10, 2),
    cheapest_comp    DECIMAL(10, 2),
    exp_units_now    DOUBLE,
    exp_units_new    DOUBLE,
    exp_profit_delta DOUBLE,             -- € per week, from the demand model
    rationale        VARCHAR,            -- LLM explanation
    status           VARCHAR NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    decided_at       TIMESTAMP,
    PRIMARY KEY (week, sku)
);
"""


@dataclass
class Recommendation:
    sku: str
    title: str
    action: str
    reason_code: str
    current_price: float
    new_price: float
    cheapest_comp: float
    exp_units_now: float
    exp_units_new: float
    exp_profit_delta: float
    rationale: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def expected_units(base: float, price: float, ref: float, elasticity: float) -> float:
    return base * (price / ref) ** (-elasticity)


def recommend(positions: pd.DataFrame, max_recs: int = 15) -> list[Recommendation]:
    recs = []
    for r in positions.itertuples():
        ref, price, cost = r.cheapest_competitor, r.our_price, r.cost
        if pd.isna(ref) or ref <= 0:
            continue
        floor = cost * (1 + r.min_margin_pct)
        gap = price / ref - 1
        target, code = None, None
        if r.strategic_role == "traffic_driver" and gap > 0.005:
            target, code = ref, "traffic_driver_not_cheapest"
        elif r.weeks_of_cover < 2 and gap < 0.03:
            target, code = ref * 1.05, "low_stock_raise"
        elif r.weeks_of_cover > 8 and gap > 0.03:
            target, code = ref * 1.01, "overstock_close_gap"
        elif gap > 0.08:
            target, code = ref * 1.04, "far_above_market"
        if target is None:
            continue
        new = max(charm_price(target), round(floor, 2))
        if abs(new - price) < 1:
            continue
        units_now = expected_units(r.base_demand, price, ref, r.elasticity)
        units_new = expected_units(r.base_demand, new, ref, r.elasticity)
        if code == "low_stock_raise":  # can't sell more than we have
            units_now = min(units_now, r.stock_end)
            units_new = min(units_new, r.stock_end)
        delta = units_new * (new - cost) - units_now * (price - cost)
        # Strategic rules may cost profit (that's the point of a traffic driver); others mustn't.
        if delta < 0 and code != "traffic_driver_not_cheapest":
            continue
        recs.append(Recommendation(
            r.sku, r.title, "lower" if new < price else "raise", code, price, new, ref,
            round(units_now, 2), round(units_new, 2), round(delta, 2)))
    recs.sort(key=lambda x: (x.reason_code != "traffic_driver_not_cheapest", -x.exp_profit_delta))
    return recs[:max_recs]
