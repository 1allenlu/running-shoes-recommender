"""Follow-up chat on the results screen (CLAUDE_CODE_PROMPT.md section 6).

A LangChain tool-calling agent. Every tool calls the ranking pipeline or the database, so the
LLM explains and asks; it never ranks (Guardrail 1) and only shares links a tool returned
(Guardrail 2).

    events = stream_chat(session, model, user_id, messages)   # SSE-ready dicts

Each event is {"event": "token" | "tool" | "picks" | "done" | "error", "data": {...}}:
`picks` carries a full `Recommendation` whenever the agent re-ranks, so the client can draw shoe
cards inside the reply.
"""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import asdict
from typing import Literal

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from sqlalchemy.orm import Session

from app.db.models import Feedback
from app.ranking.pipeline import Catalog, rank
from app.recommend import confirmed_profile, history, preferences, recommend_for
from app.retrieval.offers import get_offers as offers_for_pair
from app.schemas.preferences import HistoryEntry, IssueTag, Rating

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are LastFit's fitting assistant. The runner is looking at their top 3
running shoes, ranked by LastFit's fit model from their 3D foot scan.

Rules:
- Never rank or pick shoes yourself. To change the list (cheaper, softer, exclude a shoe), call
  `rerank` and present its picks in the order returned, with their fit scores.
- Only state facts that a tool returned. If a spec is unknown or unverified, say so.
- Only share buy links returned by `rerank` or `get_offers`, and mention that some links are
  affiliate links when you do.
- Before calling `record_feedback`, restate what you will save and get a clear yes.
- Recommend on fit and comfort only. No medical claims; suggest a professional for pain.
- Be brief: a few sentences or a short list. The app shows shoe cards for `rerank` results, so
  don't repeat every detail of them."""


def _profile_inputs(session: Session, user_id: uuid.UUID):
    profile = confirmed_profile(session, user_id)
    if profile is None:
        raise ValueError("this runner has no confirmed foot profile")
    return profile, preferences(session, user_id), history(session, user_id)


def _find(catalog: Catalog, name: str):
    """A catalog shoe from a runner-written name, or a ValueError listing the catalog."""
    entry = catalog.resolve([HistoryEntry(raw_name=name, rating="fine")])[0]
    if entry.shoe_id is None:
        known = ", ".join(s.name for s in catalog.shoes)
        raise ValueError(f"No catalog shoe matches {name!r}. Known shoes: {known}")
    return next(s for s in catalog.shoes if s.id == entry.shoe_id)


def build_tools(session: Session, user_id: uuid.UUID) -> list[BaseTool]:
    """The tools for one runner, bound to a DB session."""

    @tool
    def get_profile() -> dict:
        """The runner's confirmed foot profile, saved preferences and shoe history."""
        profile, prefs, past = _profile_inputs(session, user_id)
        return {
            "foot_profile": profile.model_dump(mode="json"),
            "preferences": prefs.model_dump(),
            "history": [h.model_dump() for h in past],
        }

    @tool(response_format="content_and_artifact")
    def rerank(
        budget_usd: float | None = None,
        feel: Literal["soft", "balanced", "firm"] | None = None,
        surface: Literal["road", "trail", "mixed"] | None = None,
        goals: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> tuple[dict, dict]:
        """Re-run LastFit's ranker with changed constraints and return the new top 3.

        Only pass what the runner asked to change: budget_usd for "under $130", feel for
        "something softer", exclude for shoe names they don't want ("I hated the Pegasus").
        Everything else stays as saved. Nothing is saved to their profile."""
        profile, prefs, past = _profile_inputs(session, user_id)
        changes = {
            k: v
            for k, v in {
                "budget_usd": budget_usd,
                "feel": feel,
                "surface": surface,
                "goals": goals,
            }.items()
            if v is not None
        }
        prefs = prefs.model_copy(update=changes)
        past = past + [HistoryEntry(raw_name=name, rating="hated") for name in exclude or []]
        rec, result = recommend_for(session, profile, prefs, past)
        summary = {
            "changed": changes | ({"exclude": exclude} if exclude else {}),
            "picks": [
                {
                    "rank": p.rank,
                    "shoe": f"{p.brand} {p.model} {p.version}",
                    "fit_score": p.fit_score,
                    "size": f"US {p.size.us_size} {p.size.width}",
                    "why_it_fits": p.why_it_fits,
                    "watch_for": p.watch_for,
                    "offers": [o.model_dump() for o in p.offers],
                }
                for p in rec.picks
            ],
            "excluded": [f"{e.name}: {e.reason}" for e in result.excluded][:10],
            "warnings": rec.flags,
            "disclosure": rec.disclosure,
        }
        return summary, rec.model_dump(mode="json")

    @tool
    def compare(shoe_a: str, shoe_b: str) -> dict:
        """Side by side: how two shoes (names like "Ghost 17", or "#1"/"#2" resolved by you from
        the current picks) score on each fit factor for this runner, plus their specs."""
        profile, prefs, past = _profile_inputs(session, user_id)
        catalog = Catalog.from_db(session)
        result = rank(profile, prefs, past, catalog, top_k=0)
        out = {"foot": result.foot}
        for key, name in (("a", shoe_a), ("b", shoe_b)):
            spec = _find(catalog, name)
            scored = next((c for c in result.candidates if c.shoe_id == spec.id), None)
            excluded = next((e.reason for e in result.excluded if e.shoe_id == spec.id), None)
            out[key] = {
                "shoe": spec.name,
                "rank": scored.rank if scored else None,
                "of": len(result.candidates),
                "fit_score": scored.fit_score if scored else None,
                "excluded_because": excluded,
                "factors": (
                    {n: s.model_dump() for n, s in scored.subscores.items() if s.status != "na"}
                    if scored
                    else {}
                ),
                "size": scored.size.model_dump() if scored else None,
                "specs": {k: v for k, v in asdict(spec).items() if k != "id"},
                "unverified_specs": spec.unknown_specs,
            }
        return out

    @tool
    def get_fit_notes(shoe: str, question: str) -> list[dict]:
        """Reviewer fit notes about one shoe that best answer a fit question, e.g. "is the toe
        box roomy?". Notes with verified=false are drafts; say so if you use them."""
        from app.retrieval.fit_notes import get_fit_notes as notes
        from app.retrieval.store import get_store

        spec = _find(Catalog.from_db(session), shoe)
        return notes(get_store(), spec.id, question, k=4)

    @tool
    def get_offers(
        shoe: str, us_size: float, width: Literal["standard", "wide", "extra-wide"]
    ) -> dict:
        """In-stock offers (fresh within 48h) for that exact pair, cheapest first."""
        spec = _find(Catalog.from_db(session), shoe)
        offers = offers_for_pair(session, spec.id, us_size, width)
        return {"shoe": spec.name, "offers": [o.model_dump() for o in offers]}

    @tool
    def record_feedback(
        shoe: str,
        us_size: float,
        width: Literal["standard", "wide", "extra-wide"],
        outcome: Rating,
        issues: list[IssueTag] | None = None,
        kept: bool | None = None,
    ) -> dict:
        """Save how a shoe worked out for the runner. Only call after they confirmed it."""
        spec = _find(Catalog.from_db(session), shoe)
        row = Feedback(
            user_id=user_id,
            shoe_id=spec.id,
            us_size=us_size,
            width=width,
            outcome=outcome,
            kept=kept,
            issues=issues or [],
        )
        session.add(row)
        session.commit()
        return {"saved": True, "shoe": spec.name, "outcome": outcome, "issues": issues or []}

    return [get_profile, rerank, compare, get_fit_notes, get_offers, record_feedback]


def to_messages(messages: list[dict]) -> list[AnyMessage]:
    """Client chat history ({role, content}) as LangChain messages."""
    out: list[AnyMessage] = []
    for m in messages:
        cls = HumanMessage if m["role"] == "user" else AIMessage
        out.append(cls(content=m["content"]))
    return out


def stream_chat(
    session: Session, model: BaseChatModel, user_id: uuid.UUID, messages: list[dict]
) -> Iterator[dict]:
    agent = create_agent(model, build_tools(session, user_id), system_prompt=SYSTEM_PROMPT)
    try:
        for mode, payload in agent.stream(
            {"messages": to_messages(messages)}, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                chunk, meta = payload
                if not isinstance(chunk, AIMessageChunk | AIMessage):
                    continue
                if meta.get("langgraph_node") != "model":
                    continue
                for call in getattr(chunk, "tool_call_chunks", None) or chunk.tool_calls or []:
                    if call.get("name"):
                        yield {"event": "tool", "data": {"name": call["name"]}}
                if chunk.text:
                    yield {"event": "token", "data": {"text": chunk.text}}
            else:
                for update in payload.values():
                    for msg in (update or {}).get("messages", []):
                        if isinstance(msg, ToolMessage) and msg.name == "rerank" and msg.artifact:
                            yield {"event": "picks", "data": msg.artifact}
    except Exception as e:  # surface to the client; the full trace goes to the log
        log.exception("chat failed for %s", user_id)
        yield {"event": "error", "data": {"message": f"{type(e).__name__}: {e}"}}
        return
    yield {"event": "done", "data": {}}
