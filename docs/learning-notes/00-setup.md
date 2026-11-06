# Phase 0 – Setup

**Goal:** a reproducible environment where Python, a browser, and a local LLM all work, plus a repo
skeleton that matches the architecture.

## What we built
| Piece | Why |
|---|---|
| `conda` env `pricescout` (Python 3.12) | Isolated dependencies; 3.12 is well supported by every library we use. |
| `pyproject.toml` + `pip install -e ".[dev]"` | One place for dependencies. `-e` ("editable") means edits in `src/` take effect without reinstalling. |
| `src/` layout (`src/pricescout/...`) | Stops you from accidentally importing the local folder instead of the installed package, which catches packaging bugs early. |
| `config.py` with `pydantic-settings` | Typed settings read from `.env`. One `settings` object instead of `os.getenv` calls scattered across the code. |
| `.gitignore` excluding `data/`, models, `.env` | Scraped data must never be published (retailer ToS and copyright); model weights are large; `.env` can hold secrets. |
| Ollama + `qwen3:8b` | Runs an open-source LLM locally: free, private, no API key. An 8B model fits comfortably in Apple-Silicon RAM. |
| Playwright Chromium | A real headless browser for retailer sites that render prices with JavaScript. |
| `scripts/check_setup.py` | A single command that tells you whether everything works. Run it whenever something seems off. |

## Key concepts
- **Local LLM serving:** Ollama runs a server at `localhost:11434`. LangChain's `ChatOllama`
  talks to it like any chat model, so swapping to a cloud model later only changes one line.
- **Qwen3 "thinking" mode:** Qwen3 can emit a `<think>` reasoning section before it answers.
  We pass `reasoning=False` where we only want the answer, which is faster and easier to parse.
- **Package layout mirrors the architecture:** `scrapers/ → db/ → matching/ → agents/ → kpis/`.

## Commands
```bash
conda activate pricescout
brew services start ollama      # keeps Ollama running in the background
python scripts/check_setup.py
```

## Next: Phase 1
Polite scrapers and the data model: the DuckDB schema for products, offers and weekly price snapshots.
