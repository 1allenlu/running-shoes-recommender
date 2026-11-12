"""Runner preferences and shoe history: the ranker's inputs besides the foot profile.

Mirrors CLAUDE_CODE_PROMPT.md sections 1 and 4. History is training data for stages 2 and 3,
so issues are fixed tags, never free text.
"""

from typing import Literal

from pydantic import BaseModel, Field

Rating = Literal["loved", "fine", "hated"]
IssueTag = Literal[
    "toe_pressure",
    "heel_slip",
    "too_narrow",
    "too_much_volume",
    "arch_discomfort",
    "too_soft",
    "too_firm",
]


class Preferences(BaseModel):
    weekly_km: float | None = Field(default=None, ge=0)
    goals: list[str] = []
    surface: Literal["road", "trail", "mixed"] | None = None
    feel: Literal["soft", "balanced", "firm"] | None = None
    budget_usd: float | None = Field(default=None, gt=0)


class HistoryEntry(BaseModel):
    shoe_id: int | None = Field(
        default=None, description="Null when the model isn't in our catalog"
    )
    raw_name: str = Field(description='The shoe as the runner named it, e.g. "Pegasus 40"')
    us_size: float | None = None
    width: str | None = None
    rating: Rating
    issues: list[IssueTag] = []
