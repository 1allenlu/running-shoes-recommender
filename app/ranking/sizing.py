"""Size and width to order in a brand (CLAUDE_CODE_PROMPT.md section 5, "Sizing").

1. Use the longer foot.
2. Scanned US size -> foot length, from the reference chart (brand `Volumental`).
3. Foot length -> the brand's size from its chart, plus that row's `size_offset`.
4. Add the running-shoe allowance (config, default +0.5) and round to the nearest size the
   brand's chart lists.

Without both charts, the scanned size plus the allowance is rounded to the nearest half size
and the advice is marked not confident.
"""

import math
from dataclasses import dataclass

from app.ranking.config import ScoringConfig
from app.ranking.features import FootFeatures
from app.schemas.recommendation import SizeAdvice

# Size chart rows under this brand map a scanned US size to foot length (mm).
REFERENCE_CHART = "Volumental"


@dataclass(frozen=True)
class ChartRow:
    us_size: float
    length_mm_min: float
    length_mm_max: float
    size_offset: float = 0.0
    note: str | None = None


def _half(x: float) -> float:
    """Nearest half size, halves rounding up (8.75 -> 9.0)."""
    return math.floor(x * 2 + 0.5) / 2


def foot_length_mm(reference: list[ChartRow], scan_size: float) -> float | None:
    points = sorted((r.us_size, (r.length_mm_min + r.length_mm_max) / 2) for r in reference)
    for (s0, l0), (s1, l1) in zip(points, points[1:], strict=False):
        if s0 <= scan_size <= s1:
            return l0 + (l1 - l0) * (scan_size - s0) / (s1 - s0)
    return None


def size_to_order(
    brand: str, foot: FootFeatures, charts: dict[str, list[ChartRow]], cfg: ScoringConfig
) -> SizeAdvice:
    allowance = cfg.sizing.running_allowance
    rows = sorted(charts.get(brand, []), key=lambda r: r.us_size)
    reference = charts.get(REFERENCE_CHART, [])
    length = foot_length_mm(reference, foot.us_size) if reference else None

    if rows and length is not None:
        fitting = [r for r in rows if r.length_mm_max >= length]
        if fitting:
            row = fitting[0]
            target = row.us_size + row.size_offset + allowance
            available = [r.us_size for r in rows]
            us_size = min(available, key=lambda s: (abs(s - target), -s))
            offset = ""
            if row.size_offset:
                runs = "small" if row.size_offset > 0 else "large"
                offset = f", {row.size_offset:+.1f} because it runs {runs}"
            return SizeAdvice(
                us_size=us_size,
                width=foot.shoe_width,
                basis=f"{brand} size chart: ~{length:.0f} mm foot is size {row.us_size:g}{offset}, "
                f"+{allowance:g} running room",
                sizing_note=row.note,
                confident=True,
            )

    return SizeAdvice(
        us_size=_half(foot.us_size + allowance),
        width=foot.shoe_width,
        basis=f"No {brand} size chart yet: scanned size {foot.us_size:g} +{allowance:g} running "
        "room, rounded to the nearest half size. Try on before buying.",
        sizing_note=None,
        confident=False,
    )
