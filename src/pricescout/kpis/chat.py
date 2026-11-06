"""Chat analyst: natural-language question -> SQL (local LLM) -> guarded, read-only execution.

Guardrails, because LLM-written SQL is untrusted input:
1. the connection is read-only (DuckDB enforces it),
2. only a single SELECT/WITH statement is accepted (checked via DuckDB's own parser),
3. results are capped with LIMIT,
4. the answer sentence is generated from the actual result rows, not from the question.
"""

from __future__ import annotations

import duckdb
import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from pricescout.config import settings

SCHEMA_DOC = """
Views/tables (DuckDB SQL):
- v_comparable(retailer, retailer_sku, week DATE, price, strike_price, strike_price_type
  ['RRP'=manufacturer list price/UVP, 'LOP'=lowest price last 30 days], category
  ['tv','laptop','smartphone'], title, brand (UPPERCASE), ean, availability_norm, list_rank)
  -- new goods sold by retailers 'mediamarkt','alternate','medimax'; use this for prices.
- v_offers: same columns as v_comparable plus is_marketplace, is_refurbished, seller
  (includes marketplace and refurbished offers).
- internal_products(sku, ean, category, brand, title, cost_price, min_margin_pct,
  strategic_role ['traffic_driver','standard','margin'])  -- VoltMarkt, our fictional shop
- internal_weekly(sku, week, our_price, market_ref [cheapest competitor price],
  units_sold, stock_end, restocked)  -- VoltMarkt's simulated weekly sales
- recommendations(week, sku, title, action, reason_code, current_price, new_price,
  cheapest_comp, exp_profit_delta, status ['pending','approved','rejected'])
Join VoltMarkt to competitors on ean. The latest week is (SELECT max(week) FROM v_comparable).
"""


class SQLAnswer(BaseModel):
    sql: str = Field(description="One DuckDB SELECT statement answering the question")


class Explanation(BaseModel):
    answer: str = Field(description="1-2 sentences answering the question from the rows")


def _llm() -> ChatOllama:
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url,
                      temperature=0, reasoning=False)


def validate_sql(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    """Raise ValueError unless `sql` is exactly one read-only SELECT statement."""
    statements = con.extract_statements(sql.strip().rstrip(";"))
    if len(statements) != 1:
        raise ValueError("exactly one SQL statement is allowed")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError(f"only SELECT queries are allowed, got {statements[0].type.name}")
    return sql.strip().rstrip(";")


def ask(db_path: str, question: str, limit: int = 200) -> tuple[str, pd.DataFrame, str]:
    con = duckdb.connect(db_path, read_only=True)
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Write one DuckDB SQL SELECT query for the question. " + SCHEMA_DOC),
            ("human", "{q}"),
        ])
        sql = (prompt | _llm().with_structured_output(SQLAnswer, method="json_schema")
               ).invoke({"q": question}).sql
        sql = validate_sql(con, sql)
        df = con.execute(f"SELECT * FROM ({sql}) LIMIT {int(limit)}").df()
    finally:
        con.close()
    explain = ChatPromptTemplate.from_messages([
        ("system", ("Answer the question in 1-2 sentences using ONLY the result rows. "
         "If the rows are empty, say no matching data was found.")),
        ("human", "Question: {q}\nRows (first 20):\n{rows}"),
    ])
    answer = (explain | _llm().with_structured_output(Explanation, method="json_schema")).invoke(
        {"q": question, "rows": df.head(20).to_csv(index=False)}).answer
    return sql, df, answer
