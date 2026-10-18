"""The agent's six tools.

Each is a plain function over a DB session (and the fit-note store) so it can be tested
directly; `build_tools` wraps them as LangChain tools for one agent run.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

from langchain_core.tools import BaseTool, tool
from langchain_core.vectorstores import VectorStore
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import sizing
from app.db.models import Feedback, FitNote, Offer, Shoe, User
from app.retrieval.hybrid import ShoeCandidate, ShoeFilters, search_shoes
from app.schemas.recommendation import OfferLink

OFFER_MAX_AGE = timedelta(hours=48)
UNVERIFIED_SOURCE = "draft-unverified"


def _normalize(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def resolve_shoe_names(session: Session, names: list[str]) -> dict[str, int]:
    """Map runner-written names ("Novablast 4", "Brooks Ghost 17") to catalog shoe ids."""
    shoes = list(session.scalars(select(Shoe)))
    resolved = {}
    for name in names:
        normalized = _normalize(name)
        for shoe in sorted(shoes, key=lambda s: -len(s.model)):
            if _normalize(f"{shoe.model} {shoe.version}") in normalized:
                resolved[name] = shoe.id
                break
    return resolved


def excluded_shoe_ids(session: Session, user: User) -> set[int]:
    """Shoes the runner disliked in the questionnaire or rated 2 or lower."""
    disliked = [s["model"] for s in (user.questionnaire or {}).get("disliked_shoes", [])]
    ids = set(resolve_shoe_names(session, disliked).values())
    ids |= set(
        session.scalars(
            select(Feedback.shoe_id).where(Feedback.user_id == user.id, Feedback.rating <= 2)
        )
    )
    return ids


def get_profile(session: Session, user_id: uuid.UUID) -> dict:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError(f"unknown user {user_id}")
    feedback = session.execute(
        select(Feedback, Shoe)
        .join(Shoe, Feedback.shoe_id == Shoe.id)
        .where(Feedback.user_id == user_id)
        .order_by(Feedback.created_at)
    ).all()
    loved = [s["model"] for s in (user.questionnaire or {}).get("loved_shoes", [])]
    return {
        "foot_profile": user.foot_profile,
        "questionnaire": user.questionnaire,
        "loved_shoe_ids": resolve_shoe_names(session, loved),
        "excluded_shoe_ids": sorted(excluded_shoe_ids(session, user)),
        "feedback": [
            {
                "shoe_id": shoe.id,
                "shoe": f"{shoe.brand} {shoe.model} {shoe.version}",
                "us_size": float(fb.us_size),
                "width": fb.width,
                "rating": fb.rating,
                "notes": fb.notes,
            }
            for fb, shoe in feedback
        ],
    }


def get_fit_notes(store: VectorStore, shoe_id: int, question: str, k: int = 4) -> list[dict]:
    hits = store.similarity_search_with_relevance_scores(question, k=k, filter={"shoe_id": shoe_id})
    return [
        {
            "fit_note_id": doc.metadata["fit_note_id"],
            "text": doc.page_content,
            "source": doc.metadata["source"],
            "verified": doc.metadata["source"] != UNVERIFIED_SOURCE,
            "relevance": round(score, 4),
        }
        for doc, score in hits
    ]


def similar_to(
    session: Session, store: VectorStore, shoe_id: int, limit: int = 5
) -> list[ShoeCandidate]:
    """Shoes whose fit notes read like this shoe's, with a small boost for the same category."""
    shoe = session.get(Shoe, shoe_id)
    if shoe is None:
        raise ValueError(f"unknown shoe {shoe_id}")
    notes = session.scalars(select(FitNote.text).where(FitNote.shoe_id == shoe_id)).all()
    query = " ".join(notes) or f"{shoe.category} running shoe"
    found = search_shoes(session, store, ShoeFilters(exclude_shoe_ids=[shoe_id]), query)
    same_category = {c.shoe_id for c in found if c.specs.get("category") == shoe.category}
    found.sort(key=lambda c: -(c.score + (0.1 if c.shoe_id in same_category else 0)))
    return found[:limit]


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


def build_tools(session: Session, store: VectorStore) -> list[BaseTool]:
    @tool("get_profile")
    def get_profile_tool(user_id: str) -> dict:
        """Get the runner's foot profile, questionnaire, past feedback, loved shoes matched
        to catalog ids, and shoe ids to exclude (disliked or rated 2 or lower)."""
        return get_profile(session, uuid.UUID(user_id))

    @tool("search_shoes")
    def search_shoes_tool(filters: ShoeFilters, vibe: str) -> list[dict]:
        """Hybrid search: spec filters on the catalog plus similarity of fit notes to `vibe`,
        a short description of the fit and feel wanted (e.g. "roomy toe box, snug low-volume
        upper, secure heel"). Returns up to 20 candidates with scores. Specs not yet known
        pass the filters and are listed in `unknown_specs`."""
        found = search_shoes(session, store, filters, vibe)
        return [c.model_dump() for c in found]

    @tool("get_fit_notes")
    def get_fit_notes_tool(shoe_id: int, question: str) -> list[dict]:
        """Top fit notes for one shoe relevant to a question such as "how roomy is the toe
        box?". Notes with verified=false are unverified drafts: treat them as weak evidence."""
        return get_fit_notes(store, shoe_id, question)

    @tool("similar_to")
    def similar_to_tool(shoe_id: int) -> list[dict]:
        """Shoes with fit notes and category similar to one the runner loved."""
        return [c.model_dump() for c in similar_to(session, store, shoe_id)]

    @tool("pick_size")
    def pick_size_tool(brand: str, foot_us_size: float, width: str, sex_scale: str = "men") -> dict:
        """Size and width to order in a brand. Pass the LONGER foot's scanned US size and
        width letter (e.g. 8.3 and "E") and the report's sex_scale ("men" or "women")."""
        return sizing.pick_size(session, brand, foot_us_size, width, sex_scale).model_dump()

    @tool("get_offers")
    def get_offers_tool(shoe_id: int, us_size: float, width: str) -> list[dict]:
        """In-stock offers for that exact pair (shoe, US size, width: standard, wide or
        extra-wide), cheapest first. Links are added to the final answer automatically;
        never write URLs yourself."""
        return [o.model_dump(exclude={"url"}) for o in get_offers(session, shoe_id, us_size, width)]

    return [
        get_profile_tool,
        search_shoes_tool,
        get_fit_notes_tool,
        similar_to_tool,
        pick_size_tool,
        get_offers_tool,
    ]
