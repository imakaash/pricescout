"""Central settings, loaded from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    db_path: str = "data/pricescout.duckdb"

    scraper_user_agent: str = "PriceScoutResearchBot/0.1 (educational project)"
    scraper_min_delay_seconds: float = 5.0
    scraper_max_products_per_retailer: int = 300


settings = Settings()
