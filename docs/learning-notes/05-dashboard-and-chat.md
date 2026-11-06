# Phase 5 – KPI dashboard + chat analyst

`streamlit run app/dashboard.py`

## One definition of "comparable"
`kpis/queries.py` is shared by the agents and the dashboard, and everything reads the
`v_comparable` view (new goods, first-party, not unavailable). The report and the dashboard
can never disagree.

## Grows with the data
Panels that need history show "⏳ appears from week 2 (weeks so far: N)" instead of an empty
or misleading chart: price changes, profit trend, and (once Phase 3 has run) matching stats.

## Design (Apple HIG-inspired + validated data colours)
- System font (SF Pro on macOS), Apple neutrals (`#f5f5f7` / black), Apple blue accent,
  rounded cards, large titles, minimal chart chrome (no axis lines, faint grid, rounded bars).
- **UI chrome and data colours are separate jobs.** Data uses a CVD-validated categorical
  palette (`validate_palette.js`: all checks pass in light and dark). Colour follows the
  entity (MediaMarkt is always blue), never the rank.
- Dark mode uses its **own** validated steps (via `st.context.theme`), not an automatic flip:
  the heatmap midpoint and scatter rings change with the theme.
- Price index heatmap is **diverging**: blue = we're cheaper, red = dearer, gray = 100.
- Every chart has a table next to it (accessibility + exact numbers).

## DuckDB concurrency gotcha
Only one process can hold the file while another writes. A dashboard keeping a connection
open would **block the weekly scrape**, so it opens read-only per render and closes at the end.

## Chat analyst (`kpis/chat.py`): text-to-SQL with guardrails
1. Read-only connection (DuckDB enforces it).
2. DuckDB's own parser checks for exactly one `SELECT` (blocks `DELETE`, `;DROP …`).
3. `LIMIT` on results.
4. The answer is written from the result rows.

**Seen in testing:** "Which TVs is Alternate cheaper on?" → the model wrote the price
difference with the wrong sign and confidently answered the opposite. That's why the UI
**always shows the SQL and the table** with the answer. Text-to-SQL is an assistant, not an
oracle.
