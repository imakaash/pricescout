import pandas as pd

from pricescout.agents.graph import grounded, summary_bullets
from pricescout.agents.pricing import recommend

FACTS = [
    ("voltmarkt is cheapest on 38 of 150 shared products (25.3%), rank 4 of 4; median 3.6% above "
    "the cheapest price."),
    "VoltMarkt laptops are on average 3.8% more expensive than mediamarkt (24 shared products).",
    "VoltMarkt tvs are on average 10.7% cheaper than medimax (22 shared products).",
    ("15 price recommendations await a human decision (15× far_above_market); expected weekly "
    "gross profit change if all were applied: €305."),
]


def test_grounded_drops_sentences_with_invented_numbers():
    text = "We rank 4 of 4. Laptops are 3.8% dearer than MediaMarkt. Margins rose 12%."
    assert grounded(text, FACTS) == "We rank 4 of 4. Laptops are 3.8% dearer than MediaMarkt."


def test_summary_is_deterministic_and_factual():
    bullets = summary_bullets(FACTS)
    assert bullets[0].startswith("voltmarkt is cheapest")
    assert "3.8% more expensive" in bullets[1]
    assert "recommendations await" in bullets[2]


def _pos(**kw):
    row = dict(sku="VM-1", title="TV", strategic_role="standard", cost=400.0, min_margin_pct=0.06,
               elasticity=6.0, base_demand=10.0, our_price=560.0, cheapest_competitor=500.0,
               stock_end=50, weeks_of_cover=5.0)
    row.update(kw)
    return pd.DataFrame([row])


def test_far_above_market_lowers_price_and_gains_profit():
    [r] = recommend(_pos())
    assert r.reason_code == "far_above_market" and r.action == "lower"
    assert r.new_price < 560 and r.exp_profit_delta > 0


def test_traffic_driver_matches_cheapest_even_at_a_profit_cost():
    [r] = recommend(_pos(strategic_role="traffic_driver", our_price=510.0))
    assert r.reason_code == "traffic_driver_not_cheapest" and r.new_price <= 500


def test_never_below_margin_floor():
    # cheapest competitor below our floor (400 * 1.06 = 424) -> we stop at the floor
    recs = recommend(_pos(strategic_role="traffic_driver", our_price=450.0,
                          cheapest_competitor=410.0))
    assert all(r.new_price >= 424 for r in recs)


def test_no_change_when_competitive():
    assert recommend(_pos(our_price=505.0)) == []
