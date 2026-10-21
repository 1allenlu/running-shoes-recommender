"""FootProfile: the scan parser's output. Mirrors ROADMAP.md section 5.

Fleet Feet / Volumental reports give a US size and width letter per foot; everything else is
an arrow on a population scale. Arrows can sit between bands, so each scale stores the nearest
band and a 0-1 position along the scale (0 = left end, 1 = right end).
"""

from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

Width = Literal["3A", "2A", "A", "B", "C", "D", "E", "2E", "3E"]
WIDTH_LETTERS = set(get_args(Width))


class _Scale(BaseModel):
    position: float = Field(description="Arrow position on the scale: 0 = left end, 1 = right end")

    @field_validator("position")
    @classmethod
    def _in_unit_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("position must be between 0 and 1")
        return value


class HeightScale(_Scale):
    band: Literal["low", "medium", "high"]


class HeelWidthScale(_Scale):
    band: Literal["narrow", "medium", "wide"]


class PressureScale(_Scale):
    band: Literal["medial", "centered", "lateral"]


class FlexibilityScale(_Scale):
    band: Literal["flexible", "moderate", "rigid"]


class Foot(BaseModel):
    us_size: float = Field(description="US size exactly as printed, e.g. 8.1")
    width: Width
    arch_height: HeightScale
    instep_height: HeightScale
    heel_width: HeelWidthScale
    # From the pressure plate; not every store has one.
    pressure: PressureScale | None = None
    arch_flexibility: FlexibilityScale | None = None


class FootProfile(BaseModel):
    sex_scale: Literal["men", "women"] = Field(
        description="Which size scale the report uses (men's or women's US sizes)"
    )
    left: Foot
    right: Foot

    @property
    def longer_foot(self) -> Foot:
        """Size and width are chosen from the longer foot (ROADMAP Phase 4, step 1)."""
        return self.left if self.left.us_size >= self.right.us_size else self.right
