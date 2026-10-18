"""Runner questionnaire. Mirrors ROADMAP.md section 5."""

from typing import Literal

from pydantic import BaseModel, Field


class ShoeOpinion(BaseModel):
    model: str = Field(description='Shoe name as the runner wrote it, e.g. "Novablast 4"')
    notes: str | None = None


class Questionnaire(BaseModel):
    weekly_km: float | None = Field(default=None, ge=0)
    goals: list[str] = []
    surface: str | None = None
    feel: Literal["soft", "balanced", "firm"] | None = None
    budget_usd: float | None = Field(default=None, gt=0)
    loved_shoes: list[ShoeOpinion] = []
    disliked_shoes: list[ShoeOpinion] = []
