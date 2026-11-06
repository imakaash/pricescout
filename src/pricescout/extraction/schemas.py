"""What we want to know about each product, per category.

Field descriptions double as instructions for the LLM (LangChain passes the JSON schema).
All fields are optional: "not stated in the title" must be None, never a guess.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Common(BaseModel):
    brand: str | None = Field(None, description="Manufacturer, e.g. 'Samsung', 'Apple', 'LG'")
    model_code: str | None = Field(
        None, description="Manufacturer model number as written, e.g. 'GU55M70HAUXZG', "
        "'55PQS8611/12', 'FA808UM-S8060W'. Not the marketing name.")
    product_line: str | None = Field(
        None, description="Marketing name/series without size or storage, e.g. 'Galaxy S26 FE', "
        "'MacBook Air', 'TUF Gaming A18', 'The Frame'")


class TVAttributes(Common):
    screen_inches: int | None = Field(None, description="Diagonal in inches (Zoll), e.g. 55")
    panel: Literal["LED", "QLED", "Mini LED", "OLED", "QD-OLED", "Micro LED", "NanoCell",
                   "QNED", "Other"] | None = Field(None, description="Display technology")
    resolution: Literal["HD", "Full HD", "4K", "8K"] | None = None
    refresh_hz: int | None = Field(None, description="Refresh rate in Hz if stated, e.g. 100, 144")


class LaptopAttributes(Common):
    screen_inches: float | None = Field(None, description="Display diagonal in inches, e.g. 15.6")
    cpu: str | None = Field(None, description="Processor, e.g. 'Intel Core Ultra 7 258V', "
                            "'AMD Ryzen 7 260', 'Apple M5'")
    ram_gb: int | None = Field(None, description="RAM (Arbeitsspeicher) in GB")
    storage_gb: int | None = Field(None, description="SSD/storage in GB (1 TB = 1024)")
    gpu: str | None = Field(None, description="Dedicated GPU if stated, e.g. 'RTX 5060'")


class SmartphoneAttributes(Common):
    storage_gb: int | None = Field(None, description="Internal storage in GB (1 TB = 1024)")
    ram_gb: int | None = Field(None, description="RAM in GB if stated")
    color: str | None = Field(None, description="Colour as written, e.g. 'Navy', 'Schwarz'")
    is_5g: bool | None = Field(None, description="True if the title says 5G")


SCHEMAS: dict[str, type[Common]] = {
    "tv": TVAttributes,
    "laptop": LaptopAttributes,
    "smartphone": SmartphoneAttributes,
}
