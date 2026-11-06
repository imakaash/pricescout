"""Phase 2: extract structured attributes from product titles.

  python scripts/extract_attributes.py                 # regex for all + up to 300 LLM titles
  python scripts/extract_attributes.py --llm-limit 0   # regex only
  python scripts/extract_attributes.py --report        # cross-shop consistency report only
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from pricescout.config import settings
from pricescout.db import store
from pricescout.extraction.pipeline import SCHEMA, consistency_report, run

console = Console()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--llm-limit", type=int, default=300)
    ap.add_argument("--report", action="store_true", help="only print the consistency report")
    ap.add_argument("--db", default=settings.db_path)
    args = ap.parse_args()

    con = store.connect(args.db)
    con.execute(SCHEMA)
    if not args.report:
        stats = run(con, args.llm_limit)
        console.print(f"extracted: {stats}")

    t = Table(title="Cross-shop consistency (same EAN → same attributes?)")
    for col in ["method", "field", "pairs", "agree %", "coverage %"]:
        t.add_column(col)
    for row in consistency_report(con):
        t.add_row(*[str(x) for x in row])
    console.print(t)
    con.close()


if __name__ == "__main__":
    main()
