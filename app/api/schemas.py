"""Request and response models for the API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, IssueTag, Preferences, Rating
from app.schemas.recommendation import Recommendation


class HistoryOut(HistoryEntry):
    id: int


class UserOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    confirmed_profile: FootProfile | None = Field(description="From the latest confirmed scan")
    preferences: Preferences | None
    history: list[HistoryOut]


class ScanOut(BaseModel):
    scan_id: int
    parser_version: str | None
    parsed_profile: FootProfile | None = Field(
        description="Check this, then confirm or correct it with "
        "PUT /users/{id}/scans/{scan_id}/confirm"
    )
    confirmed_profile: FootProfile | None


class ShoeOut(BaseModel):
    shoe_id: int
    name: str
    brand: str
    model: str
    version: str


class TaskOut(BaseModel):
    task_id: uuid.UUID
    status: Literal["queued", "running", "done", "failed"]
    result: Recommendation | None = None
    error: str | None = None


class FeedbackIn(BaseModel):
    recommendation_id: uuid.UUID | None = None
    shoe_id: int
    us_size: float
    width: Literal["standard", "wide", "extra-wide"]
    outcome: Rating
    kept: bool | None = None
    issues: list[IssueTag] = []
    notes: str | None = None


class FeedbackOut(FeedbackIn):
    id: int
    created_at: datetime
