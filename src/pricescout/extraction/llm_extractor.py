"""LLM extraction with LangChain structured output on the local Qwen model (via Ollama)."""

from __future__ import annotations

from functools import cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from pricescout.config import settings
from pricescout.extraction.schemas import SCHEMAS, Common

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     ("You extract product attributes from German electronics shop titles. "
     "Only use information explicitly present in the title. If a field is not stated, "
     "return null (never an empty string). Never guess or infer from model codes. "
     "Convert TB to GB (1 TB = 1024 GB). "
     "model_code is the manufacturer's alphanumeric part number (e.g. 'SM-S731B', "
     "'GQ55QN72FATXZG', '15ARP10'); marketing names like 'Galaxy S26 FE' or 'iPhone 18 Pro' "
     "go in product_line, not model_code. Category: {category}.")),
    ("human", "Title: {title}\nBrand (from the shop, may be empty): {brand}"),
])


@cache
def _chain(category: str):
    llm = ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url,
                     temperature=0, reasoning=False)
    # json_schema mode: Ollama constrains decoding to the Pydantic schema -> always valid JSON.
    return PROMPT | llm.with_structured_output(SCHEMAS[category], method="json_schema")


def extract(title: str, category: str, brand: str | None = None) -> Common:
    return _chain(category).invoke({"title": title, "category": category, "brand": brand or ""})
