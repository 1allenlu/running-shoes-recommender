"""Buy links for "that exact pair" (shoe + US size + width), and the link guard.

Guardrail 2: links come only from the `offers` table. `validate_links` removes any URL that
isn't there and flags the run; it also sets the affiliate disclosure whenever links remain.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Offer
from app.schemas.recommendation import AFFILIATE_DISCLOSURE, OfferLink, Recommendation

OFFER_MAX_AGE = timedelta(hours=48)
log = logging.getLogger(__name__)


def get_offers(
    session: Session,
    shoe_id: int,
    us_size: float,
    width: str,
    limit: int = 3,
    now: datetime | None = None,
) -> list[OfferLink]:
    """In-stock, fresh (< 48h) offers for that exact pair, cheapest first."""
    cutoff = (now or datetime.now(UTC)) - OFFER_MAX_AGE
    offers = session.scalars(
        select(Offer)
        .where(
            Offer.shoe_id == shoe_id,
            Offer.us_size == us_size,
            Offer.width == width,
            Offer.in_stock.is_(True),
            Offer.updated_at >= cutoff,
        )
        .order_by(Offer.price_usd.asc().nulls_last(), Offer.retailer)
        .limit(limit)
    )
    return [
        OfferLink(
            offer_id=o.id,
            retailer=o.retailer,
            price_usd=None if o.price_usd is None else float(o.price_usd),
            url=o.affiliate_url,
        )
        for o in offers
    ]


def validate_links(session: Session, rec: Recommendation) -> Recommendation:
    urls = {o.url for p in rec.picks for o in p.offers}
    known = set(session.scalars(select(Offer.affiliate_url).where(Offer.affiliate_url.in_(urls))))
    for pick in rec.picks:
        kept = [o for o in pick.offers if o.url in known]
        if len(kept) != len(pick.offers):
            removed = len(pick.offers) - len(kept)
            rec.flags.append(f"removed {removed} unknown link(s) from pick {pick.rank}")
            log.warning("removed %d link(s) not in offers from pick %d", removed, pick.rank)
        pick.offers = kept
    rec.disclosure = AFFILIATE_DISCLOSURE if any(p.offers for p in rec.picks) else None
    return rec
