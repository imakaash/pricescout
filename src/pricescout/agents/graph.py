"""Phase 4: weekly analysis as a LangGraph state machine.

  data_quality -> promotions -> pricing -> human_review -> report_writer
        └── (no data) ─────────────────────────────────────┘

Deterministic nodes compute facts from the KPI queries; the local LLM only *writes*
(rationales and the report), grounded in those facts.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from pricescout.agents.pricing import SCHEMA as REC_SCHEMA
from pricescout.agents.pricing import recommend
from pricescout.config import settings
from pricescout.db import store
from pricescout.kpis import queries as q

log = logging.getLogger(__name__)
REPORTS = Path("reports")
TRACKED_COMPETITORS = 3  # honesty about coverage: Amazon, Otto, ... are not observed


class State(TypedDict, total=False):
    db_path: str
    week: str
    interactive: bool
    quality: dict[str, Any]
    promos: dict[str, Any]
    recs: list[dict]
    decisions: dict[str, str]
    report: str
    report_path: str


def _llm() -> ChatOllama:
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url,
                      temperature=0.2, reasoning=False)


def _con(state: State):
    return store.connect(state["db_path"])


# ── nodes ────────────────────────────────────────────────────────────────────────────────
def data_quality(state: State) -> State:
    con = _con(state)
    week = q.latest_week(con)
    if week is None:
        return {"week": "", "quality": {"ok": False, "issues": ["no data scraped yet"]}}
    cov = q.coverage(con, week)
    issues = []
    for r in cov.itertuples():
        if r.last_run != "ok":
            issues.append(f"{r.retailer}: last scrape run status '{r.last_run}'")
        if r.ean_pct < 80:
            issues.append(f"{r.retailer}: only {r.ean_pct}% of offers have an EAN yet")
    ws = q.weeks(con)
    if len(ws) >= 2:
        prev = q.coverage(con, ws[-2]).set_index("retailer")["offers"]
        for r in cov.itertuples():
            if r.retailer in prev and r.offers < 0.7 * prev[r.retailer]:
                issues.append(f"{r.retailer}: offers dropped {prev[r.retailer]} -> {r.offers}")
    missing = TRACKED_COMPETITORS - len(cov)
    if missing > 0:
        issues.append(f"{missing} tracked competitor(s) have no data this week")
    con.close()
    return {"week": str(week), "quality": {
        "ok": not any("status" in i or "no data" in i for i in issues),
        "weeks_of_history": len(ws), "coverage": cov.to_dict("records"), "issues": issues,
        "note": f"Prices compared against {TRACKED_COMPETITORS} tracked competitors only "
                "(MediaMarkt, Alternate, MEDIMAX); Amazon, Otto and others are not observed."}}


def promotions(state: State) -> State:
    con = _con(state)
    promos = q.promotions(con)
    changes = q.price_changes(con)
    lop = promos[promos.strike_price_type == "LOP"]
    out = {
        "promo_count_by_retailer": promos.groupby("retailer").size().to_dict(),
        "top_lop_promos": lop.head(8)[["retailer", "title", "price", "strike_price",
                                       "discount_pct"]].to_dict("records"),
        "price_changes": (changes.head(10).to_dict("records") if len(changes)
                          else "needs at least two weeks of data"),
    }
    con.close()
    return {"promos": out}


class Rationales(BaseModel):
    rationales: list[str]


def pricing(state: State) -> State:
    con = _con(state)
    con.execute(REC_SCHEMA)
    recs = recommend(q.voltmarkt_positions(con))
    if recs:
        facts = [{k: v for k, v in r.as_dict().items() if k != "rationale"} for r in recs]
        prompt = ChatPromptTemplate.from_messages([
            ("system", ("You are a pricing analyst at VoltMarkt, a German electronics retailer. "
             "For each recommendation write ONE short sentence (max 25 words) explaining it, "
             "using only the numbers given. reason codes: traffic_driver_not_cheapest = a key "
             "product we want to be cheapest on; low_stock_raise = little stock left, so "
             "earn more per unit; overstock_close_gap = too much stock and priced above "
             "market; far_above_market = price clearly above the cheapest competitor.")),
            ("human", "{facts}\nReturn exactly {n} rationales in the same order."),
        ])
        try:
            out = (prompt | _llm().with_structured_output(Rationales, method="json_schema")
                   ).invoke({"facts": json.dumps(facts, ensure_ascii=False), "n": len(recs)})
            for r, text in zip(recs, out.rationales, strict=False):
                r.rationale = text
        except Exception as exc:  # explanations are optional; the numbers are not
            log.warning("rationale generation failed: %s", exc)
    week = state["week"]
    con.execute("DELETE FROM recommendations WHERE week = ? AND status = 'pending'", [week])
    for r in recs:
        con.execute("""INSERT OR IGNORE INTO recommendations
            (week, sku, title, action, reason_code, current_price, new_price, cheapest_comp,
             exp_units_now, exp_units_new, exp_profit_delta, rationale)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [week, r.sku, r.title, r.action, r.reason_code, r.current_price, r.new_price,
             r.cheapest_comp, r.exp_units_now, r.exp_units_new, r.exp_profit_delta, r.rationale])
    con.close()
    return {"recs": [r.as_dict() for r in recs]}


def human_review(state: State) -> State:
    if not state.get("interactive") or not state.get("recs"):
        return {"decisions": {}}  # batch mode: stay 'pending' for the dashboard
    decisions = interrupt({"recommendations": state["recs"]})  # pauses the graph
    con = _con(state)
    for sku, status in decisions.items():
        con.execute("UPDATE recommendations SET status = ?, decided_at = ? "
                    "WHERE week = ? AND sku = ?", [status, datetime.now(), state["week"], sku])
    con.close()
    return {"decisions": decisions}


class Narrative(BaseModel):
    """The only part of the report the LLM writes. Code renders all numbers and tables."""
    summary: list[str]       # exactly 3 bullets
    data_quality: str        # 1-2 sentences
    market: str              # 1-2 sentences
    price_position: str      # 1-2 sentences
    recommendations: str     # 1-2 sentences, describe, never decide


def _md_table(df, cols: list[str] | None = None, n: int = 10) -> str:
    if df is None or len(df) == 0:
        return "_no data yet_"
    df = df[cols] if cols else df
    df = df.head(n)
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(v)[:60] for v in row) + " |"
                            for row in df.itertuples(index=False))


def report_writer(state: State) -> State:
    con = _con(state)
    has_week = bool(state.get("week"))
    cov = q.coverage(con) if has_week else None
    cheapest = q.cheapest_share(con) if has_week else None
    index = q.price_index(con)
    perf = q.voltmarkt_performance(con)
    gaps = q.assortment_gaps(con)
    con.close()
    quality, promos, recs = state.get("quality", {}), state.get("promos", {}), state.get("recs", [])
    decisions = state.get("decisions", {})

    facts = key_facts(quality, promos, recs, cheapest, index)
    prompt = ChatPromptTemplate.from_messages([
        ("system", ("You are a pricing analyst writing commentary for VoltMarkt's weekly report "
         "(VoltMarkt is fictional; its internal figures are simulated). Use ONLY the facts "
         "given and never invent numbers. Price index: 100 = same price as that competitor, "
         ">100 = VoltMarkt is more expensive. Only 3 competitors are tracked (MediaMarkt, "
         "Alternate, MEDIMAX). Do NOT tell the reader to approve or reject anything: "
         "never use superlatives (most, least, best) unless a fact states the rank; "
         "humans decide. No greetings, no offers of further help.")),
        ("human", ("Facts (already verified, each one is true):\n{facts}\n\nWrite: summary = "
         "exactly 3 short bullets; each other field 1-2 sentences. Only restate these facts; "
         "do not combine numbers into new claims.")),
    ])
    try:
        n = (prompt | _llm().with_structured_output(Narrative, method="json_schema")).invoke(
            {"facts": "\n".join(f"- {f}" for f in facts)})
    except Exception:
        n = Narrative(summary=["(commentary unavailable: LLM not reachable)"], data_quality="",
                      market="", price_position="", recommendations="")

    recs_df = None
    if recs:
        import pandas as pd
        recs_df = pd.DataFrame(recs)
        recs_df["decision"] = recs_df["sku"].map(decisions).fillna("pending")
    sections = [
        f"# VoltMarkt weekly pricing report: week of {state.get('week') or 'n/a'}",
        ("_VoltMarkt is a fictional retailer; its costs, stock and sales are simulated. "
        "Competitor prices are real, from MediaMarkt, Alternate and MEDIMAX only._"),
        "## Summary\n" + "\n".join(f"- {b}" for b in summary_bullets(facts)),
        "## Data quality & coverage\n" + grounded(n.data_quality, facts) + "\n\n"
        + _md_table(cov) + "\n\n" + "\n".join(f"- ⚠️ {i}" for i in quality.get("issues", [])),
        "## Market & promotions\n" + grounded(n.market, facts)
        + "\n\n**Who is cheapest (shared products)**\n\n"
        + _md_table(cheapest) + "\n\n**Promotions (LOP = lowest price of the last 30 days)**\n\n"
        + _md_table(pd_or_none(promos.get("top_lop_promos"))),
        "## Our price position\n" + grounded(n.price_position, facts) + "\n\n" + _md_table(index)
        + "\n\n" + _md_table(perf.tail(3) if len(perf) else perf),
        "## Assortment gaps (sold by ≥2 competitors, not by us)\n" + _md_table(
            gaps, ["category", "brand", "title", "shops", "cheapest"], n=8),
        "## Recommendations (pending human decision)\n" + grounded(n.recommendations, facts)
        + "\n\n" + _md_table(
            recs_df, ["title", "reason_code", "current_price", "new_price", "cheapest_comp",
                      "exp_profit_delta", "decision"], n=20),
    ]
    report = "\n\n".join(sections) + "\n"
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"weekly-report-{state.get('week') or 'no-data'}.md"
    path.write_text(report)
    return {"report": report, "report_path": str(path)}


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def grounded(text: str, facts: list[str]) -> str:
    """Guardrail: drop any sentence containing a number that doesn't appear in the facts."""
    allowed = set(_NUM.findall(" ".join(facts)))
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(s for s in sentences if set(_NUM.findall(s)) <= allowed)


def summary_bullets(facts: list[str]) -> list[str]:
    """Deterministic summary: VoltMarkt's rank, the largest price gap, and pending decisions."""
    ours = [f for f in facts if f.startswith("voltmarkt is cheapest")]
    gaps = [f for f in facts if f.startswith("VoltMarkt ") and "% more expensive" in f]
    gaps.sort(key=lambda f: -float(_NUM.findall(f.split("%")[0])[-1]))
    recs = [f for f in facts if "recommendations await" in f]
    issues = [f for f in facts if f.startswith("Data issue")]
    return (ours + gaps[:1] + (recs or issues))[:3]


def key_facts(quality, promos, recs, cheapest, index) -> list[str]:
    """Turn KPI tables into plain, verified sentences. Small LLMs misread raw tables
    (ours claimed VoltMarkt was 'cheapest everywhere' while it ranked last), so code does
    the reading and comparing, and the LLM only rephrases."""
    out = [(f"Weeks of history: {quality.get('weeks_of_history', 0)} "
           "(trends need at least 2).")]
    out += [f"Data issue: {i}" for i in quality.get("issues", [])] or ["No data-quality issues."]
    if cheapest is not None and len(cheapest):
        ranked = cheapest.sort_values("cheapest_pct", ascending=False)
        for pos, r in enumerate(ranked.itertuples(), 1):
            out.append(f"{r.retailer} is cheapest on {r.cheapest} of {r.shared_products} shared "
                       f"products ({r.cheapest_pct}%), rank {pos} of {len(ranked)}; median "
                       f"{r.median_pct_above_cheapest}% above the cheapest price.")
    for r in index.itertuples() if len(index) else []:
        diff = round(r.price_index - 100, 1)
        word = "more expensive than" if diff > 0 else "cheaper than" if diff < 0 else "level with"
        out.append(f"VoltMarkt {r.category}s are on average {abs(diff)}% {word} {r.retailer} "
                   f"({r.shared_products} shared products).")
    counts = promos.get("promo_count_by_retailer") or {}
    out += [f"{k} shows {v} promotions with a strike price this week." for k, v in counts.items()]
    if isinstance(promos.get("price_changes"), str):
        out.append("Week-over-week price changes: not available yet (needs 2 weeks of data).")
    if recs:
        by_code: dict[str, int] = {}
        for r in recs:
            by_code[r["reason_code"]] = by_code.get(r["reason_code"], 0) + 1
        out.append(f"{len(recs)} price recommendations await a human decision "
                   f"({', '.join(f'{v}× {k}' for k, v in by_code.items())}); expected weekly "
                   f"gross profit change if all were applied: "
                   f"€{round(sum(r['exp_profit_delta'] for r in recs))}.")
    return out


def pd_or_none(records):
    import pandas as pd
    return pd.DataFrame(records) if records else None


# ── graph ────────────────────────────────────────────────────────────────────────────────
def build(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("data_quality", data_quality), ("promotions", promotions),
                     ("pricing", pricing), ("human_review", human_review),
                     ("report_writer", report_writer)]:
        g.add_node(name, fn)
    g.add_edge(START, "data_quality")
    g.add_conditional_edges("data_quality",
                            lambda s: "promotions" if s.get("week") else "report_writer")
    g.add_edge("promotions", "pricing")
    g.add_edge("pricing", "human_review")
    g.add_edge("human_review", "report_writer")
    g.add_edge("report_writer", END)
    return g.compile(checkpointer=checkpointer)
