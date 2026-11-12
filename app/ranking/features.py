"""Features the ranker works on: what the foot needs, and what each shoe offers.

`FootFeatures` summarizes a confirmed `FootProfile`. `ShoeSpec` is a plain, DB-free copy of a
catalog row, so the scorer can be tested and run from the seed CSV. `shoe_vector` turns a
shoe's known specs into centered numbers for the history similarity in `fit_scorer`.
"""

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Literal

from app.schemas.foot_profile import Foot, FootProfile

WIDTH_ORDER = ("3A", "2A", "A", "B", "C", "D", "E", "2E", "3E")
# Shoe width category for each width letter, by size scale. Men's D / women's B are standard.
_SHOE_WIDTHS = {
    "men": {"3A": "standard", "2A": "standard", "A": "standard", "B": "standard",
            "C": "standard", "D": "standard", "E": "wide", "2E": "wide", "3E": "extra-wide"},
    "women": {"3A": "standard", "2A": "standard", "A": "standard", "B": "standard",
              "C": "wide", "D": "wide", "E": "extra-wide", "2E": "extra-wide",
              "3E": "extra-wide"},
}  # fmt: skip
_BANDS = {
    "instep_height": ("low", "medium", "high"),
    "arch_height": ("low", "medium", "high"),
    "heel_width": ("narrow", "medium", "wide"),
}


def shoe_width(width_letter: str, sex_scale: str = "men") -> str:
    return _SHOE_WIDTHS[sex_scale][width_letter]


def article(word: str) -> str:
    """ "a medium", "an E", "an A", "a 2E"."""
    return f"{'an' if word[:1].upper() in 'AEIOU' else 'a'} {word}"


def width_at_least(letter: str, minimum: str) -> bool:
    return WIDTH_ORDER.index(letter) >= WIDTH_ORDER.index(minimum)


def _combined_band(left: Foot, right: Foot, scale: str) -> tuple[str, float]:
    """Both feet's band when they agree; otherwise the band of the mean position."""
    a, b = getattr(left, scale), getattr(right, scale)
    position = (a.position + b.position) / 2
    if a.band == b.band:
        return a.band, position
    bands = _BANDS[scale]
    return bands[min(int(position * len(bands)), len(bands) - 1)], position


@dataclass(frozen=True)
class FootFeatures:
    sex_scale: Literal["men", "women"]
    us_size: float  # longer foot
    width_letter: str  # longer foot
    shoe_width: str  # standard / wide / extra-wide for that letter on this scale
    wide_forefoot: bool
    instep_band: str
    instep_position: float
    heel_band: str
    heel_position: float
    arch_band: str
    pressure: tuple[str | None, str | None]  # context only, never scored

    @classmethod
    def from_profile(cls, profile: FootProfile) -> "FootFeatures":
        longer = profile.longer_foot
        width = shoe_width(longer.width, profile.sex_scale)
        instep, instep_pos = _combined_band(profile.left, profile.right, "instep_height")
        heel, heel_pos = _combined_band(profile.left, profile.right, "heel_width")
        arch, _ = _combined_band(profile.left, profile.right, "arch_height")
        return cls(
            sex_scale=profile.sex_scale,
            us_size=longer.us_size,
            width_letter=longer.width,
            shoe_width=width,
            wide_forefoot=width != "standard",
            instep_band=instep,
            instep_position=instep_pos,
            heel_band=heel,
            heel_position=heel_pos,
            arch_band=arch,
            pressure=tuple(
                f.pressure.band if f.pressure else None for f in (profile.left, profile.right)
            ),
        )

    def describe(self) -> str:
        forefoot = f"{self.width_letter} width ({'wide' if self.wide_forefoot else 'standard'})"
        return f"{forefoot} forefoot, {self.instep_band} instep, {self.heel_band} heel"


@dataclass(frozen=True)
class ShoeSpec:
    id: int
    brand: str
    model: str
    version: str
    category: str
    drop_mm: float | None = None
    stack_heel_mm: float | None = None
    stack_forefoot_mm: float | None = None
    weight_g: float | None = None
    price_usd: float | None = None
    widths_available: tuple[str, ...] | None = None
    toe_box: str | None = None
    upper_volume: str | None = None
    heel_lock: bool | None = None
    toebox_width_mm: float | None = None
    toebox_width_bigtoe_mm: float | None = None
    forefoot_width_mm: float | None = None
    heel_width_mm: float | None = None
    upper_stretch: str | None = None
    heel_counter: str | None = None
    midsole_softness: str | None = None
    stability_features: bool | None = None

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model} {self.version}"

    @property
    def offers_wide(self) -> bool | None:
        if self.widths_available is None:
            return None
        return any(w != "standard" for w in self.widths_available)

    @property
    def verified_fraction(self) -> float:
        total = len(fields(self)) - 5  # id, brand, model, version, category
        return 1 - len(self.unknown_specs) / total

    @property
    def unknown_specs(self) -> list[str]:
        skip = {"id", "brand", "model", "version", "category"}
        return [
            f.name for f in fields(self) if f.name not in skip and getattr(self, f.name) is None
        ]

    @classmethod
    def from_mapping(cls, shoe_id: int, row) -> "ShoeSpec":
        """Build from a `Shoe` ORM row or a parsed seed dict (Decimals become floats)."""
        get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
        values = {}
        for f in fields(cls):
            if f.name == "id":
                continue
            value = get(f.name)
            if isinstance(value, Decimal):
                value = float(value)
            if f.name == "widths_available" and value is not None:
                value = tuple(value)
            values[f.name] = value
        return cls(id=shoe_id, **values)


# Centered encodings so cosine similarity means "alike", not just "both positive".
_LEVELS = {"low": -1.0, "medium": 0.0, "high": 1.0}
_SOFTNESS = {"soft": -1.0, "balanced": 0.0, "firm": 1.0}
_COUNTER = {"soft": -1.0, "medium": 0.0, "firm": 1.0}
_TOE_BOX = {"narrow": -1.0, "medium": 0.0, "roomy": 1.0}
_NUMERIC = {  # spec: (center, scale)
    "toebox_width_mm": (98.0, 6.0),
    "drop_mm": (8.0, 4.0),
    "stack_heel_mm": (35.0, 6.0),
    "weight_g": (260.0, 40.0),
}


def shoe_vector(shoe: ShoeSpec) -> dict[str, float]:
    """Known specs only, as centered values; unknown specs are left out, not guessed."""
    vec: dict[str, float] = {}
    for name, table in (
        ("toe_box", _TOE_BOX),
        ("upper_volume", _LEVELS),
        ("upper_stretch", _LEVELS),
        ("heel_counter", _COUNTER),
        ("midsole_softness", _SOFTNESS),
    ):
        value = getattr(shoe, name)
        if value is not None:
            vec[name] = table[value]
    if shoe.heel_lock is not None:
        vec["heel_lock"] = 1.0 if shoe.heel_lock else -1.0
    if shoe.offers_wide is not None:
        vec["offers_wide"] = 1.0 if shoe.offers_wide else -1.0
    for name, (center, scale) in _NUMERIC.items():
        value = getattr(shoe, name)
        if value is not None:
            vec[name] = (value - center) / scale
    return vec
