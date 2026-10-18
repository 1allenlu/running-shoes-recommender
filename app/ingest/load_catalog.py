"""Load seed CSV/JSONL files into Postgres. Safe to re-run.

    uv run python -m app.ingest.load_catalog [seed_dir]

Cells containing `TODO` are stored as NULL. Size chart rows with TODO lengths are skipped
until filled in; `validate_catalog` reports them.
"""

import csv
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import FitNote, Shoe, SizeChart

DEFAULT_SEED_DIR = Path("data/seed")
TODO = "TODO"

ShoeKey = tuple[str, str, str]  # brand, model, version


def _value(cell: str) -> str | None:
    cell = cell.strip()
    return None if cell == "" or cell.upper().startswith(TODO) else cell


def _decimal(cell: str) -> Decimal | None:
    value = _value(cell)
    return None if value is None else Decimal(value)


def _bool(cell: str) -> bool | None:
    value = _value(cell)
    if value is None:
        return None
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    raise ValueError(f"not a boolean: {cell!r}")


def parse_shoes(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            widths = _value(row["widths_available"])
            weight = _value(row["weight_g"])
            rows.append(
                {
                    "brand": row["brand"].strip(),
                    "model": row["model"].strip(),
                    "version": row["version"].strip(),
                    "category": row["category"].strip(),
                    "drop_mm": _decimal(row["drop_mm"]),
                    "stack_heel_mm": _decimal(row["stack_heel_mm"]),
                    "stack_forefoot_mm": _decimal(row["stack_forefoot_mm"]),
                    "weight_g": None if weight is None else int(weight),
                    "widths_available": None if widths is None else widths.split("|"),
                    "toe_box": _value(row["toe_box"]),
                    "upper_volume": _value(row["upper_volume"]),
                    "heel_lock": _bool(row["heel_lock"]),
                    "price_usd": _decimal(row["price_usd"]),
                }
            )
    return rows


def parse_size_charts(path: Path) -> tuple[list[dict], int]:
    """Return complete rows, and how many rows were skipped for TODO lengths."""
    rows, skipped = [], 0
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            low, high = _decimal(row["length_mm_min"]), _decimal(row["length_mm_max"])
            if low is None or high is None:
                skipped += 1
                continue
            rows.append(
                {
                    "brand": row["brand"].strip(),
                    "us_size": Decimal(row["us_size"]),
                    "length_mm_min": low,
                    "length_mm_max": high,
                    "sizing_note": _value(row["sizing_note"]),
                }
            )
    return rows, skipped


def parse_fit_notes(path: Path) -> list[dict]:
    notes = []
    with path.open() as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            note = json.loads(line)
            missing = {"brand", "model", "version", "source", "text"} - note.keys()
            if missing:
                raise ValueError(f"{path}:{line_no} missing {sorted(missing)}")
            notes.append(note)
    return notes


@dataclass
class LoadReport:
    shoes: int = 0
    fit_notes_added: int = 0
    fit_notes_removed: int = 0
    size_chart_rows: int = 0
    size_chart_rows_skipped: int = 0


def load_catalog(session: Session, seed_dir: Path = DEFAULT_SEED_DIR) -> LoadReport:
    report = LoadReport()

    shoes = parse_shoes(seed_dir / "shoes.csv")
    for shoe in shoes:
        stmt = insert(Shoe).values(**shoe)
        update = {k: stmt.excluded[k] for k in shoe if k not in ("brand", "model", "version")}
        session.execute(
            stmt.on_conflict_do_update(constraint="uq_shoes_brand_model_version", set_=update)
        )
    report.shoes = len(shoes)

    shoe_ids: dict[ShoeKey, int] = {
        (s.brand, s.model, s.version): s.id for s in session.scalars(select(Shoe))
    }

    # Keep existing notes (and their embeddings); add new ones, drop ones no longer seeded.
    wanted: dict[int, set[tuple[str, str]]] = {}
    for note in parse_fit_notes(seed_dir / "fit_notes.jsonl"):
        key = (note["brand"], note["model"], note["version"])
        if key not in shoe_ids:
            raise ValueError(f"fit note for unknown shoe {key}")
        wanted.setdefault(shoe_ids[key], set()).add((note["source"], note["text"]))

    seeded_ids = {shoe_ids[(s["brand"], s["model"], s["version"])] for s in shoes}
    for existing in session.scalars(select(FitNote).where(FitNote.shoe_id.in_(seeded_ids))):
        pair = (existing.source, existing.text)
        if pair in wanted.get(existing.shoe_id, set()):
            wanted[existing.shoe_id].discard(pair)
        else:
            session.delete(existing)
            report.fit_notes_removed += 1
    for shoe_id, pairs in wanted.items():
        for source, text in sorted(pairs):
            session.add(FitNote(shoe_id=shoe_id, source=source, text=text))
            report.fit_notes_added += 1

    charts, report.size_chart_rows_skipped = parse_size_charts(seed_dir / "size_charts.csv")
    brands = {row["brand"] for row in charts}
    if brands:
        session.execute(delete(SizeChart).where(SizeChart.brand.in_(brands)))
        session.add_all(SizeChart(**row) for row in charts)
    report.size_chart_rows = len(charts)

    session.commit()
    return report


def main() -> None:
    from app.db.session import SessionLocal

    seed_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED_DIR
    with SessionLocal() as session:
        report = load_catalog(session, seed_dir)
    print(
        f"shoes: {report.shoes} upserted\n"
        f"fit notes: {report.fit_notes_added} added, {report.fit_notes_removed} removed\n"
        f"size charts: {report.size_chart_rows} rows loaded, "
        f"{report.size_chart_rows_skipped} skipped (TODO lengths)"
    )


if __name__ == "__main__":
    main()
