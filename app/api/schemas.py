"""Request and response models for the API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.foot_profile import FootProfile
from app.schemas.questionnaire import Questionnaire
from app.schemas.recommendation import Recommendation


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    foot_profile: FootProfile | None
    questionnaire: Questionnaire | None
    created_at: datetime


class ScanOut(BaseModel):
    scan_id: int
    parser_version: str
    parsed_profile: FootProfile = Field(
        description="Check this, then confirm or correct it with PUT /users/{id}/profile"
    )


class TaskOut(BaseModel):
    task_id: uuid.UUID
    status: Literal["queued", "running", "done", "failed"]
    result: Recommendation | None = None
    error: str | None = None


class FeedbackIn(BaseModel):
    shoe_id: int
    us_size: float
    width: Literal["standard", "wide", "extra-wide"]
    rating: int = Field(ge=1, le=5)
    notes: str | None = None


class FeedbackOut(FeedbackIn):
    id: int
    created_at: datetime
