"""MCP server: LastFit's ranking for Claude Desktop (or any MCP client).

    uv run python -m app.mcp_server        # stdio transport

Every tool runs the same ranking pipeline as the API; the client LLM explains the results but
never ranks (Guardrail 1), and only shares links that `get_offers` / `find_shoes` return.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from langchain_core.vectorstores import VectorStore
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Shoe, User
from app.ranking.pipeline import Catalog, rank
from app.recommend import (
    MissingProfile,
    confirmed_profile,
    history,
    preferences,
    recommend_for,
    resolve_shoe_id,
)
from app.retrieval.fit_notes import get_fit_notes
from app.retrieval.offers import get_offers as offers_for_pair
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import Preferences
from app.schemas.recommendation import AFFILIATE_DISCLOSURE

FIT_QUESTIONS = {
    "toe_box": "how roomy is the toe box and forefoot?",
    "width": "is it available or suitable for wide feet?",
    "upper_volume": "how much volume does the upper have over the instep?",
    "heel": "how secure is the heel hold?",
}


def _user_inputs(session: Session, user_id: str):
    try:
        uid = uuid.UUID(user_id)
    except ValueError as e:
        raise ValueError(f"not a user id: {user_id!r}") from e
    if session.get(User, uid) is None:
        raise ValueError(f"unknown user {user_id}")
    profile = confirmed_profile(session, uid)
    if profile is None:
        raise MissingProfile("user has no confirmed foot profile")
    return profile, preferences(session, uid), history(session, uid)


def _shoe(session: Session, name: str) -> Shoe:
    shoe_id = resolve_shoe_id(session, name)
    if shoe_id is None:
        known = session.scalars(select(Shoe).order_by(Shoe.brand, Shoe.model)).all()
        listing = ", ".join(f"{s.brand} {s.model} {s.version}" for s in known)
        raise ValueError(f"no catalog shoe matches {name!r}; known shoes: {listing}")
    return session.get(Shoe, shoe_id)


def find_shoes_impl(
    session: Session, profile_or_user_id: str | dict, prefs: Preferences | None = None
) -> dict:
    if isinstance(profile_or_user_id, str):
        profile, saved, past = _user_inputs(session, profile_or_user_id)
        prefs = prefs or saved
    else:
        profile, past = FootProfile.model_validate(profile_or_user_id), []
    rec, result = recommend_for(session, profile, prefs or Preferences(), past)
    return {
        **rec.model_dump(mode="json"),
        "excluded": [e.model_dump() for e in result.excluded],
        "note": "Order and fit scores come from LastFit's ranker; don't reorder them. Sizes "
        "with confident=false come from rounding the scan, not a brand chart.",
    }


def fit_check_impl(session: Session, store: VectorStore, user_id: str, shoe: str) -> dict:
    profile, prefs, past = _user_inputs(session, user_id)
    found = _shoe(session, shoe)
    result = rank(profile, prefs, past, Catalog.from_db(session), top_k=0)
    scored = next((c for c in result.candidates if c.shoe_id == found.id), None)
    excluded = next((e.reason for e in result.excluded if e.shoe_id == found.id), None)
    return {
        "shoe": f"{found.brand} {found.model} {found.version}",
        "foot": result.foot,
        "excluded_because": excluded,
        "rank": None if scored is None else scored.rank,
        "of": len(result.candidates),
        "fit": None if scored is None else scored.model_dump(mode="json"),
        "fit_notes": {
            topic: get_fit_notes(store, found.id, question, k=2)
            for topic, question in FIT_QUESTIONS.items()
        },
        "runner_history": [h.model_dump() for h in past if h.shoe_id == found.id],
    }


def get_offers_impl(session: Session, shoe: str, size: float, width: str) -> dict:
    if width not in ("standard", "wide", "extra-wide"):
        raise ValueError("width must be standard, wide or extra-wide")
    found = _shoe(session, shoe)
    offers = offers_for_pair(session, found.id, size, width)
    return {
        "shoe": f"{found.brand} {found.model} {found.version}",
        "us_size": size,
        "width": width,
        "offers": [o.model_dump() for o in offers],
        "disclosure": AFFILIATE_DISCLOSURE if offers else None,
    }


# --- MCP wiring ---

server = MCPServer(
    name="lastfit",
    instructions=(
        "Running-shoe fit tools backed by LastFit's own ranker, a shoe catalog, fit notes and "
        "Fleet Feet foot scans. Present shoes in the order the tools return; don't rank them "
        "yourself. Recommend on fit and comfort only; make no medical claims. Only share buy "
        "links returned by these tools, and include the disclosure when you do."
    ),
)


@lru_cache
def _store() -> VectorStore:
    from app.retrieval.store import get_store

    return get_store()


@contextmanager
def _session() -> Iterator[Session]:
    """DB session for one tool call; bad input becomes a ToolError the client can read."""
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        try:
            yield session
        except ValueError as e:
            raise ToolError(str(e)) from e


@server.tool()
def find_shoes(profile_or_user_id: str | dict, preferences: Preferences | None = None) -> dict:
    """Top 3 shoes for a foot, ranked by LastFit. Pass a user id (uses their confirmed scan,
    preferences and shoe history) or a FootProfile object. Each pick has a fit score, the
    per-feature contributions behind it, reasons, a caveat, the size to order and buy links."""
    with _session() as session:
        return find_shoes_impl(session, profile_or_user_id, preferences)


@server.tool()
def fit_check(user_id: str, shoe: str) -> dict:
    """How one shoe (e.g. "Ghost 17") fits a user: its rank and fit score with every
    sub-score, why it was excluded if it was, the size to order, fit notes on toe box, width,
    volume and heel, and the user's own history with it."""
    with _session() as session:
        return fit_check_impl(session, _store(), user_id, shoe)


@server.tool()
def get_offers(shoe: str, size: float, width: str) -> dict:
    """In-stock offers for that exact pair (shoe name, US size, width: standard, wide or
    extra-wide), cheapest first, with buy links and the affiliate disclosure."""
    with _session() as session:
        return get_offers_impl(session, shoe, size, width)


if __name__ == "__main__":
    server.run()
