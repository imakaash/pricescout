# PriceScout 🔎

**Agentic competitive price intelligence for German consumer electronics.**
Tracks weekly prices for **TVs, laptops and smartphones** at MediaMarkt and its competitors
(Saturn, Amazon.de, Otto, Cyberport, notebooksbilliger, Galaxus, …), matches identical products
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
- [ ] **Phase 1** – Polite scrapers + data model
- [ ] **Phase 2** – LangChain: LLM attribute extraction with structured output
- [ ] **Phase 3** – Fine-tuning a product-matching model (LoRA / MLX)
- [ ] **Phase 4** – LangGraph multi-agent weekly analysis
- [ ] **Phase 5** – KPI dashboard + chat analyst
- [ ] **Phase 6** – Scheduling, tracing, tests, Docker

## Setup
```bash
conda create -n pricescout python=3.12 -y
conda activate pricescout
pip install -e ".[dev]"
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
