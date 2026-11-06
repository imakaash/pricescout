"""Phase 4: run the LangGraph weekly analysis.

  python scripts/weekly_analysis.py            # batch: recommendations stay 'pending'
  python scripts/weekly_analysis.py --review   # interactive approve/reject in the terminal
"""

from __future__ import annotations

import argparse
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from pricescout.agents.graph import build
from pricescout.config import settings

console = Console()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--review", action="store_true", help="approve/reject recommendations now")
    ap.add_argument("--db", default=settings.db_path)
    args = ap.parse_args()

    graph = build(checkpointer=MemorySaver())  # checkpointer is required for interrupt()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = graph.invoke({"db_path": args.db, "interactive": args.review}, cfg)

    while "__interrupt__" in state:  # human-in-the-loop pause
        recs = state["__interrupt__"][0].value["recommendations"]
        decisions = {}
        for r in recs:
            console.print(f"\n[bold]{r['title'][:70]}[/bold]  ({r['reason_code']})")
            console.print(f"  €{r['current_price']} → [bold]€{r['new_price']}[/bold]  "
                          f"(cheapest competitor €{r['cheapest_comp']}, "
                          f"expected profit Δ €{r['exp_profit_delta']}/week)")
            if r.get("rationale"):
                console.print(f"  [dim]{r['rationale']}[/dim]")
            choice = Prompt.ask("  approve?", choices=["y", "n", "s"], default="s")
            if choice != "s":
                decisions[r["sku"]] = "approved" if choice == "y" else "rejected"
        state = graph.invoke(Command(resume=decisions), cfg)

    console.print(Markdown(state.get("report", "")))
    console.print(f"\n[dim]saved to {state.get('report_path')}[/dim]")


if __name__ == "__main__":
    main()
