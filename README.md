# PriceScout 🔎

**Agentic competitive price intelligence for German consumer electronics.**
Built from the point of view of **VoltMarkt, a fictional retailer**: it tracks weekly prices for
**TVs, laptops and smartphones** at real competitors that allow polite automated access
(**MediaMarkt, Alternate, MEDIMAX**; see the
[competitor survey](docs/learning-notes/01-scrapers-and-data-model.md#7-choosing-a-competitor-a-reality-check-2026-11-06)
for why others are excluded). VoltMarkt's own costs, stock and sales are
[simulated](docs/learning-notes/01b-synthetic-internal-data.md) on top of the real market data,
so the agents can make margin- and stock-aware recommendations. It matches identical products
across retailers with a **fine-tuned open-source LLM**, and runs a **LangGraph multi-agent system**
that analyses the market and writes a weekly report. Results are reported on a KPI dashboard.

> 🎓 This is a learning project. Every phase has notes in [`docs/learning-notes/`](docs/learning-notes/).

## Architecture

```
Weekly scheduler
  └─▶ Polite scrapers (per retailer, robots.txt-aware) ──▶ raw store
        └─▶ Product matching (LoRA fine-tuned Qwen, served via Ollama)
              └─▶ Price DB (DuckDB)
                    ├─▶ LangGraph multi-agent analyst
                    │     ├─ Data-quality agent
                    │     ├─ Anomaly / promo detection agent
                    │     ├─ Pricing-recommendation agent (human-in-the-loop)
                    │     └─ Report-writer agent
                    ├─▶ Chat analyst (text-to-SQL)
                    └─▶ Streamlit KPI dashboard
```

## KPIs
Price index · price gap to cheapest/average · cheapest-share · assortment overlap & gaps ·
availability · promo frequency & depth · price-change velocity · week-over-week trends.

## Tech stack
LangChain · LangGraph · Ollama (Qwen3) · MLX-LM (LoRA fine-tuning on Apple Silicon) ·
Playwright · DuckDB · Polars · Streamlit · Plotly

## Roadmap
- [x] **Phase 0** – Setup: env, local LLM, repo skeleton
- [x] **Phase 1** – Polite scrapers (MediaMarkt, Alternate, MEDIMAX) + DuckDB data model + synthetic VoltMarkt
- [x] **Phase 2** – LangChain: attribute extraction (regex + local LLM, structured output)
- [x] **Phase 3** – LoRA fine-tuned product matcher (Qwen3-0.6B, MLX)
- [x] **Phase 4** – LangGraph weekly analysis with human-in-the-loop pricing
- [x] **Phase 5** – Streamlit KPI dashboard + text-to-SQL chat analyst
- [x] **Phase 6** – Weekly schedule (launchd), CI, Docker *(tracing: open)*

First versions of every phase run end to end; they get more useful as weekly history builds up.

## Weekly pipeline
```bash
scripts/run_weekly.sh                 # or install the schedule: scripts/install_schedule.sh
streamlit run app/dashboard.py        # dashboard
python scripts/weekly_analysis.py --review   # approve/reject recommendations in the terminal
```

## Setup
```bash
conda create -n pricescout python=3.12 -y
conda activate pricescout
pip install -e ".[dev,mlx]"   # mlx: Apple Silicon only (Phase 3)
playwright install chromium

brew install ollama
ollama serve &            # or: brew services start ollama
ollama pull qwen3:8b

cp .env.example .env
python scripts/check_setup.py
```

## Scraping ethics
This project scrapes **politely**: it honours `robots.txt`, identifies itself with an honest
User-Agent, waits several seconds between requests, scrapes a small product sample only once a week,
and **never publishes raw scraped data** (the `data/` folder is git-ignored). Check each retailer's
terms of service before running the scrapers yourself.
