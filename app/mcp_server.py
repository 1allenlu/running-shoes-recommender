"""MCP server: exposes the recommender's tools to Claude Desktop (or any MCP client).

    uv run python -m app.mcp_server        # stdio transport

The client is itself the LLM, so these tools make no model calls: `find_shoes` builds the
search from the scan in code, and the client reasons over the results.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Literal

from langchain_core.vectorstores import VectorStore
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import sizing
from app.agent.tools import (
    excluded_shoe_ids,
    get_fit_notes,
    resolve_shoe_names,
)
from app.agent.tools import (
    get_offers as offers_for_pair,
)
from app.db.models import Feedback, Shoe, User
from app.retrieval.hybrid import ShoeFilters, candidate, search_shoes
from app.schemas.foot_profile import FootProfile
from app.schemas.recommendation import AFFILIATE_DISCLOSURE

FIT_QUESTIONS = {
    "toe_box": "how roomy is the toe box and forefoot?",
    "width": "is it available or suitable for wide feet?",
    "upper_volume": "how much volume does the upper have over the instep?",
    "heel": "how secure is the heel hold?",
}


class Preferences(BaseModel):
    looking_for: str | None = Field(
        default=None, description='Fit and feel wanted, e.g. "soft, roomy toe box, snug heel"'
    )
    feel: Literal["soft", "balanced", "firm"] | None = None
    budget_usd: float | None = None
    categories: list[Literal["daily", "tempo", "race", "stability", "max-cushion"]] | None = None
    toe_box: list[Literal["narrow", "medium", "roomy"]] | None = None
    upper_volume: list[Literal["low", "medium", "high"]] | None = None
    exclude: list[str] = Field(default=[], description="Shoe names to leave out")


def vibe_from_profile(profile: FootProfile, feel: str | None) -> str:
    """A "feel" query from the scan, for when the user didn't describe one."""
    foot = profile.longer_foot
    parts = []
    if sizing.shoe_width(foot.width, profile.sex_scale) != "standard":
        parts.append("roomy toe box, wide forefoot")
    parts.append(
        {
            "low": "snug low-volume upper",
            "medium": "medium-volume upper",
            "high": "high-volume upper with room over the instep",
        }[foot.instep_height.band]
    )
    if foot.heel_width.band == "narrow" or foot.instep_height.band == "low":
        parts.append("secure heel lock")
    if feel:
        parts.append({"soft": "soft cushioning", "balanced": "balanced cushioning",
                      "firm": "firm responsive ride"}[feel])  # fmt: skip
    return ", ".join(parts)


def _user(session: Session, user_id: str) -> User:
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise ValueError(f"unknown user {user_id}")
    return user


def _shoe(session: Session, name: str) -> Shoe:
    found = resolve_shoe_names(session, [name])
    if name not in found:
        known = session.scalars(select(Shoe).order_by(Shoe.brand, Shoe.model)).all()
        listing = ", ".join(f"{s.brand} {s.model} {s.version}" for s in known)
        raise ValueError(f"no catalog shoe matches {name!r}; known shoes: {listing}")
    return session.get(Shoe, found[name])


def find_shoes_impl(
    session: Session,
    store: VectorStore,
    profile_or_user_id: str | dict,
    preferences: Preferences | None = None,
    limit: int = 8,
) -> dict:
    prefs = preferences or Preferences()
    excluded: set[int] = set(resolve_shoe_names(session, prefs.exclude).values())
    if isinstance(profile_or_user_id, str):
        user = _user(session, profile_or_user_id)
        if user.foot_profile is None:
            raise ValueError("user has no confirmed foot profile")
        profile = FootProfile.model_validate(user.foot_profile)
        excluded |= excluded_shoe_ids(session, user)
        questionnaire = user.questionnaire or {}
    else:
        profile = FootProfile.model_validate(profile_or_user_id)
        questionnaire = {}

    foot = profile.longer_foot
    width = sizing.shoe_width(foot.width, profile.sex_scale)
    feel = prefs.feel or questionnaire.get("feel")
    filters = ShoeFilters(
        width=width,
        toe_box=prefs.toe_box,
        upper_volume=prefs.upper_volume,
        categories=prefs.categories,
        max_price_usd=prefs.budget_usd or questionnaire.get("budget_usd"),
        exclude_shoe_ids=sorted(excluded),
    )
    vibe = prefs.looking_for or vibe_from_profile(profile, feel)
    found = search_shoes(session, store, filters, vibe, limit=limit)
    return {
        "fit_basis": {
            "us_size": foot.us_size,
            "width_letter": foot.width,
            "shoe_width": width,
            "sex_scale": profile.sex_scale,
        },  # fmt: skip
        "searched_for": vibe,
        "filters": filters.model_dump(exclude_defaults=True),
        "candidates": [
            {
                **c.model_dump(),
                "size": sizing.pick_size(
                    session, c.name.split()[0], foot.us_size, foot.width, profile.sex_scale
                ).model_dump(),
            }
            for c in found
        ],
        "note": "Specs in unknown_specs are not confirmed. Sizes marked confident=false come "
        "from rounding the scan, not a brand chart.",
    }


def fit_check_impl(session: Session, store: VectorStore, user_id: str, shoe: str) -> dict:
    user = _user(session, user_id)
    if user.foot_profile is None:
        raise ValueError("user has no confirmed foot profile")
    profile = FootProfile.model_validate(user.foot_profile)
    foot = profile.longer_foot
    found = _shoe(session, shoe)
    feedback = session.scalars(
        select(Feedback).where(Feedback.user_id == user.id, Feedback.shoe_id == found.id)
    ).all()
    return {
        "shoe": candidate(found, None, None).model_dump(exclude={"score", "best_fit_note"}),
        "excluded_for_this_runner": found.id in excluded_shoe_ids(session, user),
        "fit_basis": {
            "us_size": foot.us_size,
            "width_letter": foot.width,
            "shoe_width": sizing.shoe_width(foot.width, profile.sex_scale),
            "arch_height": foot.arch_height.band,
            "instep_height": foot.instep_height.band,
            "heel_width": foot.heel_width.band,
        },
        "size": sizing.pick_size(
            session, found.brand, foot.us_size, foot.width, profile.sex_scale
        ).model_dump(),
        "fit_notes": {
            topic: get_fit_notes(store, found.id, question, k=2)
            for topic, question in FIT_QUESTIONS.items()
        },
        "runner_feedback": [
            {"rating": f.rating, "us_size": float(f.us_size), "width": f.width, "notes": f.notes}
            for f in feedback
        ],
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
    name="shoe-recommender",
    instructions=(
        "Running-shoe fit tools backed by a catalog, fit notes and Fleet Feet foot scans. "
        "Recommend on fit and comfort only; make no medical claims. Only share buy links "
        "returned by get_offers, and include its disclosure when you do."
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
    """Search the catalog for shoes that fit a foot. Pass a user id (uses their confirmed scan,
    questionnaire and exclusions) or a FootProfile object. Returns candidates ranked by fit-note
    similarity, each with the size and width to order."""
    with _session() as session:
        return find_shoes_impl(session, _store(), profile_or_user_id, preferences)


@server.tool()
def fit_check(user_id: str, shoe: str) -> dict:
    """Check how one shoe (e.g. "Ghost 17") fits a user's scan: specs, fit notes on toe box,
    width, volume and heel, the size to order, and the user's own feedback on it."""
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
