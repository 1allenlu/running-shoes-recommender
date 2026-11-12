"""Load `config/scoring.yaml`, the stage 1 scorer's weights and tables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "scoring.yaml"

Level = Literal["low", "medium", "high"]


class WidthConfig(BaseModel):
    target_toebox_mm: dict[str, float]
    narrow_tolerance_mm: float
    wide_tolerance_mm: float
    wide_version_extra_mm: float
    toe_box_scores: dict[Literal["wide_foot", "standard_foot"], dict[str, float]]
    wide_version_score: float
    no_wide_version_score: float


class VolumeConfig(BaseModel):
    low: dict[str, float]
    medium: dict[str, float]
    high: dict[str, float]
    heel_lock_bonus_low_instep: float


class HeelConfig(BaseModel):
    counter_scores: dict[str, float]
    lock_scores: dict[bool, float]
    no_special_need: float


class ComboConfig(BaseModel):
    roomy_width_fit: float
    wide_version_penalty: float


class RideConfig(BaseModel):
    feel_scores: dict[str, dict[str, float]]
    stack_by_goal: dict[str, Literal["high", "low"]]
    high_stack_min_mm: float
    low_stack_max_mm: float
    stack_mismatch_score: float


class BudgetConfig(BaseModel):
    over_budget_allowance: float
    full_reward_under_fraction: float


class FilterConfig(BaseModel):
    wide_min_letter: str
    wide_toebox_min_mm: float
    categories_by_goal: dict[str, list[str]]
    recurring_issue_excludes: dict[str, dict[str, list[str]]]


class HistoryConfig(BaseModel):
    min_shared_dims: int


class SizingConfig(BaseModel):
    running_allowance: float


class ScoringConfig(BaseModel):
    version: str
    weights: dict[str, float]
    unknown_score: float
    issue_weight_boosts: dict[str, dict[str, float]]
    width: WidthConfig
    volume: VolumeConfig
    heel: HeelConfig
    combo: ComboConfig
    ride: RideConfig
    budget: BudgetConfig
    filters: FilterConfig
    history: HistoryConfig
    sizing: SizingConfig


def load_config(path: Path | str = DEFAULT_PATH) -> ScoringConfig:
    return ScoringConfig.model_validate(yaml.safe_load(Path(path).read_text()))


@lru_cache
def default_config() -> ScoringConfig:
    return load_config()
