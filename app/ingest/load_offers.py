"""Load an affiliate product feed (CSV) into `offers`. Safe to run nightly.

    uv run python -m app.ingest.load_offers [feed.csv]

Feed columns: retailer, sku, brand, title, us_size, width, price_usd, in_stock, url.
Each product is matched to a catalog shoe by brand plus "<model> <version>" in its title.
Seen offers get `updated_at` refreshed; offers from the same retailers that are missing from
the feed are marked out of stock. Products that match no shoe are listed in the report.
"""

import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import SHOE_WIDTHS, Offer, Shoe

DEFAULT_FEED = Path("data/seed/sample_offers_feed.csv")

OfferKey = tuple[int, str, Decimal, str]  # shoe_id, retailer, us_size, width


def _normalize(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


class ShoeMatcher:
    def __init__(self, shoes: list[Shoe]):
        self._by_brand: dict[str, list[tuple[str, int]]] = {}
        for shoe in shoes:
            key = _normalize(f"{shoe.model} {shoe.version}")
            self._by_brand.setdefault(shoe.brand.lower(), []).append((key, shoe.id))
        for keys in self._by_brand.values():
            keys.sort(key=lambda k: len(k[0]), reverse=True)  # longest model name wins

    def match(self, brand: str, title: str) -> int | None:
        normalized = _normalize(title)
        for key, shoe_id in self._by_brand.get(brand.lower(), []):
            if key in normalized:
                return shoe_id
        return None


@dataclass
class OfferLoadReport:
    upserted: int = 0
    marked_out_of_stock: int = 0
    unmatched: list[str] = field(default_factory=list)


def load_offers(
    session: Session, feed_path: Path = DEFAULT_FEED, now: datetime | None = None
) -> OfferLoadReport:
    now = now or datetime.now(UTC)
    report = OfferLoadReport()
    matcher = ShoeMatcher(list(session.scalars(select(Shoe))))

    rows: dict[OfferKey, dict] = {}
    with feed_path.open(newline="") as f:
        for row in csv.DictReader(f):
            shoe_id = matcher.match(row["brand"], row["title"])
            if shoe_id is None or row["width"] not in SHOE_WIDTHS:
                report.unmatched.append(f"{row['retailer']}: {row['title']} ({row['sku']})")
                continue
            key = (shoe_id, row["retailer"], Decimal(row["us_size"]), row["width"])
            price = row["price_usd"].strip()
            rows[key] = {
                "shoe_id": shoe_id,
                "retailer": row["retailer"],
                "us_size": key[2],
                "width": row["width"],
                "price_usd": Decimal(price) if price else None,
                "in_stock": row["in_stock"].strip().lower() == "true",
                "affiliate_url": row["url"].strip(),
                "updated_at": now,
            }

    for values in rows.values():
        stmt = insert(Offer).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_offers_shoe_retailer_size_width",
                set_={
                    k: stmt.excluded[k]
                    for k in ("price_usd", "in_stock", "affiliate_url", "updated_at")
                },
            )
        )
    report.upserted = len(rows)

    retailers = {key[1] for key in rows}
    if retailers:
        missing = (
            update(Offer)
            .where(
                Offer.retailer.in_(retailers),
                Offer.in_stock.is_(True),
                tuple_(Offer.shoe_id, Offer.retailer, Offer.us_size, Offer.width).not_in(
                    list(rows)
                ),
            )
            .values(in_stock=False, updated_at=Offer.updated_at)
        )
        report.marked_out_of_stock = session.execute(missing).rowcount

    session.commit()
    return report


def main() -> None:
    from app.db.session import SessionLocal

    feed = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FEED
    with SessionLocal() as session:
        report = load_offers(session, feed)
    print(f"offers upserted: {report.upserted}")
    print(f"marked out of stock (missing from feed): {report.marked_out_of_stock}")
    print(f"unmatched feed products: {len(report.unmatched)}")
    for line in report.unmatched:
        print(f"  {line}")


if __name__ == "__main__":
    main()
