# Phase 6 – Scheduling, tests, CI, Docker

## Weekly schedule (launchd, macOS)
`scripts/run_weekly.sh` runs the pipeline:
scrape ×3 → simulate VoltMarkt → extract → match → weekly analysis (batch).
Each step is logged to `logs/weekly-YYYY-MM-DD.log`, and a failing step doesn't stop later ones.

```bash
scripts/install_schedule.sh            # Sundays 22:00 (runs on next wake if asleep)
launchctl kickstart gui/$(id -u)/com.pricescout.weekly   # run now
scripts/install_schedule.sh --remove
```
Why launchd instead of cron: it's the macOS-native scheduler and catches up after sleep.
History only accumulates if this runs every week, which is why it was pulled forward.

## Tests & CI
- `pytest`: parsers (synthetic fixtures, never real scraped HTML), robots matching, GTIN
  check digits, idempotent storage, views, simulation determinism, extraction, pricing rules
  and LLM guardrails. No network, no LLM, no GPU needed.
- GitHub Actions (`.github/workflows/ci.yml`) runs `ruff` + `pytest` on every push.
- Lint config documents *why* rules are ignored (e.g. broad `except` in batch jobs).

## Docker
`Dockerfile` packages the dashboard and CPU scripts; Ollama is reached on the host via
`OLLAMA_BASE_URL`. MLX fine-tuning stays on the host (Apple Silicon only).
**Not yet verified:** Docker wasn't installed when this was written.

## Not done yet
- LLM tracing (Langfuse/LangSmith) for inspecting agent runs.
- Retraining the matcher on a schedule (it's applied weekly, trained by hand).
