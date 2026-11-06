"""Central settings, loaded from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    db_path: str = "data/pricescout.duckdb"

    # Our fictional retailer; its internal data (costs, stock, sales) is synthetic.
    own_company_name: str = "VoltMarkt"

    scraper_user_agent: str = "PriceScoutResearchBot/0.1 (educational project)"
    scraper_min_delay_seconds: float = 5.0
    # Listings are scraped in full; product pages (only needed for unknown EANs) are capped
    # per run, so EAN coverage grows week by week without hitting a shop hard.
    scraper_detail_budget: int = 300


settings = Settings()
