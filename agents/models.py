from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, model_validator


class CompRecord(BaseModel):
    name: str
    sector: str
    stage: str
    valuation_usd: Optional[float]
    arr_usd: Optional[float]
    ebitda_usd: Optional[float]
    last_funding_round: str
    last_funding_amount_usd: Optional[float]
    lead_investors: list[str]

    @property
    def ev_to_arr(self) -> Optional[float]:
        if self.valuation_usd and self.arr_usd and self.arr_usd > 0:
            return round(self.valuation_usd / self.arr_usd, 2)
        return None

    @property
    def ev_to_ebitda(self) -> Optional[float]:
        if self.valuation_usd and self.ebitda_usd and self.ebitda_usd > 0:
            return round(self.valuation_usd / self.ebitda_usd, 2)
        return None


class ValuationRange(BaseModel):
    low: float
    mid: float
    high: float
    methodology: str


class Slide(BaseModel):
    title: str
    bullets: list[str]
    notes: Optional[str] = None


class DeckContent(BaseModel):
    company_name: str
    tagline: str
    slides: list[Slide]

    @model_validator(mode="after")
    def must_have_six_slides(self) -> "DeckContent":
        if len(self.slides) != 6:
            raise ValueError(f"DeckContent must have exactly 6 slides, got {len(self.slides)}")
        return self


class CellWrite(BaseModel):
    sheet: str
    cell: str
    value: str | float | int | None = None
    formula: Optional[str] = None
    bold: bool = False
    bg_color: Optional[str] = None
    number_format: Optional[str] = None


class ExcelInstructions(BaseModel):
    sheets: list[str]
    writes: list[CellWrite]
    column_widths: dict[str, dict[str, float]]
