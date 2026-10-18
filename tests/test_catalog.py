import shutil
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import FitNote, Shoe, SizeChart
from app.ingest.load_catalog import (
    DEFAULT_SEED_DIR,
    load_catalog,
    parse_fit_notes,
    parse_shoes,
    parse_size_charts,
)
from app.ingest.validate_catalog import find_gaps


def test_parse_shoes_maps_todo_to_none(seed_dir):
    glide, zoom = parse_shoes(seed_dir / "shoes.csv")
    assert glide["widths_available"] == ["standard", "wide"]
    assert glide["heel_lock"] is True
    assert glide["drop_mm"] == Decimal("8")
    assert zoom["drop_mm"] is None
    assert zoom["widths_available"] is None


def test_parse_size_charts_skips_todo_rows(seed_dir):
    rows, skipped = parse_size_charts(seed_dir / "size_charts.csv")
    assert len(rows) == 1 and skipped == 1


def test_real_seed_files_parse():
    shoes = parse_shoes(DEFAULT_SEED_DIR / "shoes.csv")
    keys = {(s["brand"], s["model"], s["version"]) for s in shoes}
    assert len(shoes) == len(keys) >= 20
    notes = parse_fit_notes(DEFAULT_SEED_DIR / "fit_notes.jsonl")
    assert {(n["brand"], n["model"], n["version"]) for n in notes} == keys
    assert sum(1 for s in shoes if s["widths_available"] and "wide" in s["widths_available"]) >= 3


@pytest.mark.db
def test_load_is_idempotent(db_session, seed_dir):
    load_catalog(db_session, seed_dir)
    glide_id = db_session.scalar(select(Shoe.id).where(Shoe.model == "Glide"))
    note_ids = set(db_session.scalars(select(FitNote.id)))

    report = load_catalog(db_session, seed_dir)
    assert report.fit_notes_added == report.fit_notes_removed == 0
    assert db_session.scalar(select(func.count()).select_from(Shoe)) == 2
    assert db_session.scalar(select(Shoe.id).where(Shoe.model == "Glide")) == glide_id
    assert set(db_session.scalars(select(FitNote.id))) == note_ids
    assert db_session.scalar(select(func.count()).select_from(SizeChart)) == 1


@pytest.mark.db
def test_reload_applies_edits(db_session, seed_dir):
    load_catalog(db_session, seed_dir)
    shoes = seed_dir / "shoes.csv"
    shoes.write_text(shoes.read_text().replace(",140\n", ",150\n"))
    notes = seed_dir / "fit_notes.jsonl"
    notes.write_text(notes.read_text().replace('"soft"', '"plush"'))

    report = load_catalog(db_session, seed_dir)
    assert (report.fit_notes_added, report.fit_notes_removed) == (1, 1)
    glide = db_session.scalar(select(Shoe).where(Shoe.model == "Glide"))
    db_session.refresh(glide)
    assert glide.price_usd == Decimal("150")
    texts = set(db_session.scalars(select(FitNote.text)))
    assert texts == {"roomy", "plush", "secure"}


@pytest.mark.db
def test_validation_reports_gaps(db_session, seed_dir):
    load_catalog(db_session, seed_dir)
    gaps = find_gaps(db_session)
    assert not any(g.startswith("Acme Glide") for g in gaps)
    assert any(g.startswith("Acme Zoom 1: missing specs: drop_mm") for g in gaps)
    assert "Acme Zoom 1: 0 fit notes (need 3)" in gaps


@pytest.mark.db
def test_real_seed_loads(db_session, tmp_path):
    shutil.copytree(DEFAULT_SEED_DIR, tmp_path / "seed")
    report = load_catalog(db_session, tmp_path / "seed")
    assert report.shoes >= 20
    assert report.fit_notes_added >= 3 * report.shoes
