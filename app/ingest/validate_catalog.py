"""Report catalog gaps: shoes missing specs or fit notes, unverified notes, missing size charts.

    uv run python -m app.ingest.validate_catalog

Exits 1 if any gap is found, so it can gate a release.
"""

import sys
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.sizing import REFERENCE_CHART
from app.db.models import FitNote, Shoe, SizeChart

SPEC_FIELDS = (
    "drop_mm",
    "stack_heel_mm",
    "stack_forefoot_mm",
    "weight_g",
    "widths_available",
    "toe_box",
    "upper_volume",
    "heel_lock",
    "price_usd",
)
MIN_FIT_NOTES = 3
UNVERIFIED_SOURCE = "draft-unverified"


def find_gaps(session: Session) -> list[str]:
    gaps = []
    notes = session.scalars(select(FitNote)).all()
    note_counts = Counter(n.shoe_id for n in notes)
    unverified = Counter(n.shoe_id for n in notes if n.source == UNVERIFIED_SOURCE)
    chart_brands = set(session.scalars(select(SizeChart.brand).distinct()))

    shoes = session.scalars(select(Shoe).order_by(Shoe.brand, Shoe.model)).all()
    for shoe in shoes:
        name = f"{shoe.brand} {shoe.model} {shoe.version}"
        missing = [field for field in SPEC_FIELDS if getattr(shoe, field) is None]
        if missing:
            gaps.append(f"{name}: missing specs: {', '.join(missing)}")
        if note_counts[shoe.id] < MIN_FIT_NOTES:
            gaps.append(f"{name}: {note_counts[shoe.id]} fit notes (need {MIN_FIT_NOTES})")
        if unverified[shoe.id]:
            gaps.append(f"{name}: {unverified[shoe.id]} fit notes still {UNVERIFIED_SOURCE}")

    if REFERENCE_CHART not in chart_brands:
        gaps.append(f"{REFERENCE_CHART}: no reference size chart (scan size -> foot length)")
    for brand in sorted({s.brand for s in shoes} - chart_brands):
        gaps.append(f"{brand}: no size chart rows loaded")
    return gaps


def main() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        gaps = find_gaps(session)
    for gap in gaps:
        print(gap)
    print(f"\n{len(gaps)} gaps found." if gaps else "Catalog complete.")
    sys.exit(1 if gaps else 0)


if __name__ == "__main__":
    main()
