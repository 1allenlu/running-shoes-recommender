"""Choose the size and width to order in a brand from the scanned size and width letter.

The scan reports a fractional US size (e.g. 8.3), not a foot length. Rows in `size_charts`
under brand `REFERENCE_CHART` map scan sizes to foot length; the brand's own rows map foot
length to the size to order. Without both charts, the scan size is rounded up to the next
half size and the advice is marked not confident.
"""

import math
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SizeChart
from app.schemas.recommendation import SizeAdvice

REFERENCE_CHART = "Volumental"

# Shoe width categories by scale. Men's D / women's B are standard.
_WIDTHS = {
    "men": {"3A": "standard", "2A": "standard", "A": "standard", "B": "standard",
            "C": "standard", "D": "standard", "E": "wide", "2E": "wide", "3E": "extra-wide"},
    "women": {"3A": "standard", "2A": "standard", "A": "standard", "B": "standard",
              "C": "wide", "D": "wide", "E": "extra-wide", "2E": "extra-wide",
              "3E": "extra-wide"},
}  # fmt: skip


def shoe_width(width_letter: str, sex_scale: str = "men") -> str:
    return _WIDTHS[sex_scale][width_letter]


def _chart(session: Session, brand: str) -> list[SizeChart]:
    stmt = select(SizeChart).where(SizeChart.brand == brand).order_by(SizeChart.us_size)
    return list(session.scalars(stmt))


def _foot_length_mm(reference: list[SizeChart], scan_size: float) -> float | None:
    """Interpolate foot length between the midpoints of the reference rows around scan_size."""
    points = [(float(r.us_size), float(r.length_mm_min + r.length_mm_max) / 2) for r in reference]
    for (s0, l0), (s1, l1) in zip(points, points[1:], strict=False):
        if s0 <= scan_size <= s1:
            return l0 + (l1 - l0) * (scan_size - s0) / (s1 - s0)
    return None


def pick_size(
    session: Session, brand: str, foot_us_size: float, width_letter: str, sex_scale: str = "men"
) -> SizeAdvice:
    width = shoe_width(width_letter, sex_scale)
    brand_rows, reference = _chart(session, brand), _chart(session, REFERENCE_CHART)
    length = _foot_length_mm(reference, foot_us_size) if reference else None

    if brand_rows and length is not None:
        length_d = Decimal(str(round(length, 1)))
        fitting = [r for r in brand_rows if r.length_mm_max >= length_d]
        if fitting:
            row = fitting[0]
            return SizeAdvice(
                us_size=float(row.us_size),
                width=width,
                basis=f"{brand} size chart: foot length ~{length:.0f} mm from the scan",
                sizing_note=row.sizing_note,
                confident=True,
            )

    return SizeAdvice(
        us_size=math.ceil(foot_us_size * 2) / 2,
        width=width,
        basis=f"No usable {brand} size chart yet: scanned size {foot_us_size} rounded up to "
        "the next half size. Try on before buying.",
        sizing_note=None,
        confident=False,
    )
