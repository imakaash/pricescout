"""Phase 0 sanity check: is the environment ready for PriceScout?

Run:  python scripts/check_setup.py
Each check prints OK / FAIL with a hint. Exit code is non-zero if anything failed.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

from rich.console import Console

console = Console()
results: list[bool] = []


def check(name: str, fn: Callable[[], str]) -> None:
    """Run one check; fn returns a detail string or raises with a helpful message."""
    try:
        detail = fn()
        console.print(f"[green]  OK [/green] {name}  [dim]{detail}[/dim]")
        results.append(True)
    except Exception as exc:  # noqa: BLE001 - we want to report any failure
        console.print(f"[red]FAIL[/red] {name}  [yellow]{exc}[/yellow]")
        results.append(False)


def python_version() -> str:
    if sys.version_info < (3, 12):
        raise RuntimeError(f"Python {sys.version.split()[0]} found, need >= 3.12")
    return sys.version.split()[0]


def packages() -> str:
    names = ["langchain", "langchain_ollama", "langgraph", "playwright", "httpx",
             "selectolax", "duckdb", "polars", "pydantic_settings", "streamlit", "plotly"]
    missing = []
    for n in names:
        try:
            importlib.import_module(n)
        except ImportError:
            missing.append(n)
    if missing:
        raise RuntimeError(f"missing {missing} -> pip install -e '.[dev]'")
    return f"{len(names)} packages importable"


def settings() -> str:
    from pricescout.config import settings as s

    return f"model={s.llm_model}, db={s.db_path}, delay={s.scraper_min_delay_seconds}s"


def playwright_browser() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        version = browser.version
        browser.close()
    return f"chromium {version}"


def ollama_server() -> str:
    import httpx

    from pricescout.config import settings as s

    try:
        r = httpx.get(f"{s.ollama_base_url}/api/tags", timeout=5)
    except httpx.ConnectError as exc:
        raise RuntimeError("Ollama not reachable -> run `brew services start ollama`") from exc
    models = [m["name"] for m in r.json().get("models", [])]
    if s.llm_model not in models:
        raise RuntimeError(f"{s.llm_model} not pulled (have {models}) -> ollama pull {s.llm_model}")
    return f"{len(models)} model(s), {s.llm_model} present"


def llm_roundtrip() -> str:
    from langchain_ollama import ChatOllama

    from pricescout.config import settings as s

    llm = ChatOllama(model=s.llm_model, base_url=s.ollama_base_url, temperature=0,
                     reasoning=False)
    reply = llm.invoke("Reply with exactly one word: ready").content.strip()
    return f"LLM said: {reply[:40]!r}"


def duckdb_works() -> str:
    import duckdb

    return f"duckdb {duckdb.__version__}, SELECT 1 -> {duckdb.connect().execute('SELECT 1').fetchall()[0][0]}"


if __name__ == "__main__":
    console.rule("PriceScout setup check")
    check("Python version", python_version)
    check("Python packages", packages)
    check("Settings / .env", settings)
    check("DuckDB", duckdb_works)
    check("Playwright Chromium", playwright_browser)
    check("Ollama server + model", ollama_server)
    if results[-1]:
        check("LLM round-trip (LangChain -> Ollama)", llm_roundtrip)
    console.rule()
    ok = all(results)
    console.print("[bold green]All good![/bold green]" if ok else "[bold red]Fix the FAILs above.[/bold red]")
    sys.exit(0 if ok else 1)
