import shutil
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.agent.tools import get_offers
from app.db.models import Offer
from app.ingest.load_catalog import DEFAULT_SEED_DIR, load_catalog
from app.ingest.load_offers import DEFAULT_FEED, load_offers

pytestmark = pytest.mark.db


def offer_count(session, **where) -> int:
    stmt = select(func.count()).select_from(Offer).filter_by(**where)
    return session.scalar(stmt)


def test_reload_is_idempotent_and_refreshes_updated_at(catalog, db_session, tmp_path):
    total = offer_count(db_session)
    later = datetime.now(UTC) + timedelta(hours=1)
    report = load_offers(db_session, tmp_path / "feed.csv", now=later)
    assert report.upserted == total == offer_count(db_session)
    assert report.marked_out_of_stock == 0
    oldest = db_session.scalar(select(func.min(Offer.updated_at)))
    assert oldest == later


def test_missing_items_marked_out_of_stock(catalog, db_session, tmp_path):
    feed = tmp_path / "feed.csv"
    lines = feed.read_text().splitlines()
    dropped = [ln for ln in lines if "acme-roomy-1-9.0-standard" in ln]
    feed.write_text("\n".join(ln for ln in lines if ln not in dropped) + "\n")

    report = load_offers(db_session, feed)
    assert report.marked_out_of_stock == len(dropped) == 2  # Store X and Store Y
    assert get_offers(db_session, catalog["Roomy"], 9.0, "standard") == []


def test_unmatched_products_reported(catalog, db_session, tmp_path):
    feed = tmp_path / "feed.csv"
    feed.write_text(
        feed.read_text()
        + "Store X,x-1,Acme,Acme Roomy 7 Running Shoe,9.0,standard,1,true,https://example.com/a\n"
        + "Store X,x-2,Zeta,Zeta Fly 1,9.0,standard,1,true,https://example.com/b\n"
        + "Store X,x-3,Acme,Acme Roomy 1,9.0,narrow,1,true,https://example.com/c\n"
    )
    report = load_offers(db_session, feed)
    assert [u.split(" (")[0] for u in report.unmatched] == [
        "Store X: Acme Roomy 7 Running Shoe",
        "Store X: Zeta Fly 1",
        "Store X: Acme Roomy 1",
    ]


def test_get_offers_cheapest_first_and_excludes_stale(catalog, db_session):
    offers = get_offers(db_session, catalog["Roomy"], 9.0, "standard")
    assert [(o.retailer, o.price_usd) for o in offers] == [("Store Y", 99.0), ("Store X", 140.0)]

    in_49h = datetime.now(UTC) + timedelta(hours=49)
    assert get_offers(db_session, catalog["Roomy"], 9.0, "standard", now=in_49h) == []


def test_sample_feed_matches_real_catalog(db_session, tmp_path):
    shutil.copytree(DEFAULT_SEED_DIR, tmp_path / "seed")
    load_catalog(db_session, tmp_path / "seed")
    report = load_offers(db_session, DEFAULT_FEED)
    assert report.upserted > 500
    assert sorted(u.split(": ")[1].split(" (")[0] for u in report.unmatched) == [
        "Brooks Ghost 99 Men's Running Shoe",
        "Mizuno Wave Rider 28 Men's Running Shoe",
    ]
    urls = db_session.scalars(select(Offer.affiliate_url)).all()
    assert all(u.startswith("https://example.com/") for u in urls)
