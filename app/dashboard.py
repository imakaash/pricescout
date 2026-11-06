"""PriceScout dashboard (Phase 5). Run: streamlit run app/dashboard.py

Panels switch on as data grows: trend charts appear from week 2, matching/extraction panels
once those phases have run. VoltMarkt is a fictional retailer; its internal data is simulated.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pricescout.config import settings
from pricescout.kpis import queries as q

st.set_page_config(page_title="PriceScout", page_icon="🔎", layout="wide")

# Fixed entity -> colour (validated categorical palette; colour follows the entity, never rank).
COLORS = {"mediamarkt": "#2a78d6", "alternate": "#eb6834", "medimax": "#1baf7a",
          "voltmarkt": "#6250d6"}
ROLE_COLORS = {"traffic_driver": "#2a78d6", "standard": "#eb6834", "margin": "#1baf7a"}
DARK = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
if DARK:  # dark mode uses its own validated steps, not an automatic flip
    COLORS = {"mediamarkt": "#3987e5", "alternate": "#d95926", "medimax": "#199e70",
              "voltmarkt": "#9085e9"}
    ROLE_COLORS = {"traffic_driver": "#3987e5", "standard": "#d95926", "margin": "#199e70"}
SURFACE = "#000000" if DARK else "#f5f5f7"
MIDPOINT = "#383835" if DARK else "#f0efec"
# cheaper (blue) <-> dearer (red), neutral gray at index 100
DIVERGING = [[0, COLORS["mediamarkt"]], [0.5, MIDPOINT], [1, "#e66767" if DARK else "#e34948"]]


SYSTEM_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial'

# Apple-style chrome: cards with soft shadows, quiet labels, large-title hierarchy.
# Colours use currentColor tints so the same CSS works in the light and dark theme.
st.markdown("""
<style>
  .block-container { padding-top: 2.2rem; max-width: 1280px; }
  h1, h2, h3 { letter-spacing: -0.02em; }
  [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
    border-radius: 18px;
  }
  [data-testid="stMetric"] {
    padding: 18px 20px;
    background: color-mix(in srgb, currentColor 4%, transparent);
    box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.04);
  }
  [data-testid="stMetricLabel"] p { font-size: .82rem; opacity: .7; font-weight: 500; }
  [data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -0.02em; }
  .ps-eyebrow { font-size: .78rem; text-transform: uppercase; letter-spacing: .06em;
    opacity: .6; font-weight: 600; margin-bottom: -6px; }
</style>
""", unsafe_allow_html=True)


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    """Minimal chart chrome: no axis lines, faint grid, rounded bar ends, system font."""
    fig.update_layout(height=height, margin=dict(l=4, r=4, t=28, b=4),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family=SYSTEM_FONT, size=13),
                      legend=dict(orientation="h", y=1.1, x=0, title=None),
                      hoverlabel=dict(namelength=-1, font_family=SYSTEM_FONT), bargap=0.4)
    fig.update_xaxes(showgrid=False, showline=False, ticks="", title_font_size=12)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False, showline=False,
                     ticks="", title_font_size=12)
    fig.update_traces(selector=dict(type="bar"), marker_line_width=0, marker_cornerradius=4)
    return fig


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="ps-eyebrow">{text}</div>', unsafe_allow_html=True)


def con():
    """Read-only connection for one page render, closed at the end of the script.

    DuckDB allows one process to hold the file while another writes, so a dashboard that kept
    a connection open would block the weekly scrape. Open late, close early.
    """
    try:
        return duckdb.connect(settings.db_path, read_only=True)
    except duckdb.IOException:
        st.error("The database is locked by a running job (scrape/simulation). "
                 "Refresh in a few minutes.")
        st.stop()


def tbl(df: pd.DataFrame, **kw):
    pretty = df.rename(columns=lambda c: c.replace("_pct", " %").replace("_", " ").capitalize())
    st.dataframe(pretty, hide_index=True, width="stretch", **kw)


def need_weeks(n: int, have: int, what: str) -> bool:
    if have < n:
        st.info(f"⏳ {what} appears from week {n} (weeks of data so far: {have}).")
        return False
    return True


c = con()
if q.latest_week(c) is None:
    c.close()
    st.warning("No data yet. Run `python scripts/scrape.py --retailer mediamarkt` first.")
    st.stop()

all_weeks = q.weeks(c)
with st.sidebar:
    st.markdown("### PriceScout")
    week = st.selectbox("Week", list(reversed(all_weeks)), format_func=lambda w: f"{w:%Y-%m-%d}")
    st.caption(f"{len(all_weeks)} week(s) of data · competitors tracked: MediaMarkt, "
               "Alternate, MEDIMAX")
    st.caption("**VoltMarkt is fictional**: its costs, stock and sales are simulated on top of "
               "real competitor prices. Amazon, Otto & others are not observed.")

tabs = st.tabs(["Overview", "Price position", "Promotions", "Assortment", "VoltMarkt",
                "Recommendations", "Data quality", "Ask the data"])

# ── Overview ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    eyebrow(f"Week of {week:%d %B %Y}")
    st.title("Market overview")
    cheapest = q.cheapest_share(c, week)
    perf = q.voltmarkt_performance(c)
    cov = q.coverage(c, week)
    k = st.columns(4)
    k[0].metric("Comparable competitor offers", f"{int(cov.comparable.sum()):,}")
    if len(cheapest) and "voltmarkt" in set(cheapest.retailer):
        vm = cheapest.set_index("retailer").loc["voltmarkt"]
        k[1].metric("VoltMarkt cheapest on", f"{vm.cheapest_pct}%",
                    help=f"{vm.cheapest} of {vm.shared_products} products also sold elsewhere")
        k[2].metric("VoltMarkt median vs cheapest", f"+{vm.median_pct_above_cheapest}%")
    if len(perf):
        wk = perf[perf.week == perf.week.max()]
        prev = perf[perf.week < perf.week.max()]
        delta = None
        if len(prev):
            last = prev[prev.week == prev.week.max()].gross_profit.sum()
            delta = f"{100 * (wk.gross_profit.sum() / last - 1):+.1f}% vs last week"
        k[3].metric("VoltMarkt gross profit (week)", f"€{wk.gross_profit.sum():,.0f}", delta)

    st.subheader("Who is cheapest on shared products?")
    if len(cheapest):
        fig = px.bar(cheapest, x="retailer", y="cheapest_pct", color="retailer",
                     color_discrete_map=COLORS, text="cheapest_pct",
                     hover_data=["shared_products", "cheapest", "median_pct_above_cheapest"],
                     labels={"cheapest_pct": "cheapest on (% of shared products)"})
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        st.plotly_chart(style(fig).update_layout(showlegend=False), width="stretch")
        tbl(cheapest)

# ── Price position ───────────────────────────────────────────────────────────────────────
with tabs[1]:
    idx = q.price_index(c, week)
    st.subheader("VoltMarkt price index by competitor (100 = same price, >100 = we're dearer)")
    if len(idx):
        piv = idx.pivot(index="retailer", columns="category", values="price_index")
        rng = max(abs(piv.values - 100).max(), 1)
        fig = go.Figure(go.Heatmap(
            z=piv.values, x=piv.columns, y=piv.index, colorscale=DIVERGING,
            zmin=100 - rng, zmax=100 + rng, text=piv.values, texttemplate="%{text:.1f}",
            hovertemplate="%{y} · %{x}: index %{z:.1f}<extra></extra>", xgap=2, ygap=2))
        st.plotly_chart(style(fig, 300), width="stretch")
        tbl(idx)
    pos = q.voltmarkt_positions(c)
    if len(pos):
        st.subheader("Every VoltMarkt product: price gap vs margin")
        fig = px.scatter(pos, x="vs_cheapest_pct", y="margin_pct", color="strategic_role",
                         color_discrete_map=ROLE_COLORS, hover_name="title",
                         hover_data=["our_price", "cheapest_competitor", "weeks_of_cover"],
                         labels={"vs_cheapest_pct": "% above cheapest competitor",
                                 "margin_pct": "gross margin %"})
        fig.update_traces(marker=dict(size=9, line=dict(width=2, color=SURFACE)))
        fig.add_vline(x=0, line_width=1, line_color="#888")
        st.plotly_chart(style(fig, 420), width="stretch")
        tbl(pos[["title", "category", "strategic_role", "our_price", "cheapest_competitor",
                 "vs_cheapest_pct", "margin_pct", "units_sold", "weeks_of_cover"]])

# ── Promotions ───────────────────────────────────────────────────────────────────────────
with tabs[2]:
    promos = q.promotions(c, week)
    st.subheader("Promotions this week")
    st.caption("LOP = 'lowest price in the last 30 days' (legally required reference, the honest "
               "promo signal). RRP/UVP discounts are often permanent, so only ≥15% are shown.")
    if len(promos):
        counts = promos.groupby(["retailer", "strike_price_type"]).size().reset_index(name="n")
        fig = px.bar(counts, x="retailer", y="n", color="retailer", pattern_shape="strike_price_type",
                     color_discrete_map=COLORS, barmode="group",
                     labels={"n": "promotions", "strike_price_type": "type"})
        st.plotly_chart(style(fig, 300), width="stretch")
        tbl(promos)
    st.subheader("Week-over-week price changes (≥5%)")
    if need_weeks(2, len(all_weeks), "Price-change tracking"):
        tbl(q.price_changes(c))

# ── Assortment ───────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Products ≥2 competitors sell that VoltMarkt doesn't")
    gaps = q.assortment_gaps(c, week)
    tbl(gaps) if len(gaps) else st.info("No gaps found (or VoltMarkt data not generated yet).")
    overlap = c.execute("""
        SELECT category, n_shops, count(*) AS products FROM (
          SELECT ean, any_value(category) AS category, count(DISTINCT retailer) AS n_shops
          FROM v_comparable WHERE week = ? AND ean IS NOT NULL GROUP BY ean) GROUP BY ALL
        ORDER BY 1, 2""", [week]).df()
    st.subheader("How many shops sell each product (by EAN)?")
    overlap["n_shops"] = overlap.n_shops.astype(str) + " shop(s)"
    fig = px.bar(overlap, x="category", y="products", color="n_shops", barmode="group",
                 color_discrete_sequence=list(COLORS.values())[:3])
    st.plotly_chart(style(fig, 320), width="stretch")

# ── VoltMarkt ────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("VoltMarkt (simulated) performance")
    if len(perf):
        if need_weeks(2, perf.week.nunique(), "The trend chart"):
            fig = px.line(perf, x="week", y="gross_profit", color="category", markers=True)
            fig.update_traces(line_width=2, marker_size=8)
            st.plotly_chart(style(fig), width="stretch")
        tbl(perf)
        if len(pos):
            st.subheader("Stock cover (weeks)")
            fig = px.histogram(pos, x="weeks_of_cover", color="category", nbins=20,
                               color_discrete_sequence=list(COLORS.values())[:3])
            st.plotly_chart(style(fig, 280), width="stretch")
    else:
        st.info("Run `python scripts/generate_internal_data.py` to create VoltMarkt's data.")

# ── Recommendations (human-in-the-loop) ──────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Pricing recommendations awaiting a decision")
    st.caption("Numbers come from rules + the demand model; the text is written by the local "
               "LLM. Approved prices are applied in next week's VoltMarkt simulation.")
    if q.has_table(c, "recommendations"):
        recs = c.execute("SELECT * FROM recommendations ORDER BY week DESC, "
                         "exp_profit_delta DESC").df()
        pending = recs[recs.status == "pending"]
        for r in pending.itertuples():
            with st.container(border=True):
                a, b = st.columns([4, 1])
                a.markdown(f"**{r.title[:80]}**  \n`{r.reason_code}` · €{r.current_price} → "
                           f"**€{r.new_price}** (cheapest competitor €{r.cheapest_comp}) · "
                           f"expected profit Δ **€{r.exp_profit_delta:+.0f}/week**")
                if r.rationale:
                    a.caption(r.rationale)
                choice = b.radio("decision", ["–", "approve", "reject"], key=f"d-{r.week}-{r.sku}",
                                 horizontal=False, label_visibility="collapsed")
                if choice != "–" and b.button("save", key=f"s-{r.week}-{r.sku}"):
                    c.close()  # same process can't hold read-only and read-write connections
                    try:
                        w = duckdb.connect(settings.db_path)
                        w.execute("UPDATE recommendations SET status = ?, decided_at = ? "
                                  "WHERE week = ? AND sku = ?",
                                  ["approved" if choice == "approve" else "rejected",
                                   datetime.now(), r.week, r.sku])
                        w.close()
                        st.rerun()
                    except duckdb.IOException:
                        st.error("Database busy (a job is running); try again shortly.")
        if not len(pending):
            st.success("No pending recommendations.")
        with st.expander("History"):
            tbl(recs[recs.status != "pending"])
    else:
        st.info("Run `python scripts/weekly_analysis.py` to generate recommendations.")

# ── Data quality ─────────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Coverage this week")
    tbl(cov)
    st.subheader("Scrape runs")
    tbl(c.execute("SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 30").df())
    m = q.matches_summary(c)
    st.subheader("Product matching (Phase 3)")
    tbl(m) if len(m) else st.info("Run `python scripts/train_matcher.py all` to match products.")
    if q.has_table(c, "product_attributes"):
        st.subheader("Attribute extraction (Phase 2)")
        tbl(c.execute("SELECT method, count(*) AS products FROM product_attributes "
                      "GROUP BY method").df())

# ── Ask the data ─────────────────────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("Ask the data (local LLM → SQL)")
    st.caption("The model writes SQL; it runs read-only and only SELECT is allowed. "
               "**Always check the SQL**: models can get a sign or a join wrong.")
    question = st.text_input("Question", placeholder="Which TVs is Alternate cheaper on than "
                             "MediaMarkt this week?")
    if question:
        from pricescout.kpis.chat import ask
        c.close()  # ask() opens its own read-only connection
        with st.spinner("Thinking…"):
            try:
                sql, df, answer = ask(settings.db_path, question)
                st.markdown(f"**Answer:** {answer}")
                st.code(sql, language="sql")
                tbl(df)
            except Exception as exc:
                st.error(f"Could not answer: {exc}")

try:
    c.close()
except duckdb.ConnectionException:
    pass  # already closed by the chat or approval handler
