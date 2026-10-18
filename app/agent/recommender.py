"""Build and run the recommendation agent, then post-process its answer.

`finalize` is where the guardrails are enforced in code: it drops excluded or unknown shoes,
computes sizes, attaches offers from the database, removes any link that is not in `offers`
(flagging the run), and adds the affiliate disclosure whenever links are present.
"""

import uuid

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.vectorstores import VectorStore
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import sizing
from app.agent.prompts import RECOMMENDER_SYSTEM, recommend_request
from app.agent.tools import build_tools, excluded_shoe_ids, get_offers
from app.config import get_settings
from app.db.models import FitNote, Offer, Shoe, User
from app.schemas.foot_profile import FootProfile
from app.schemas.recommendation import (
    AFFILIATE_DISCLOSURE,
    AgentRecommendation,
    Pick,
    Recommendation,
)

TOP_N = 3


def default_model() -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    return ChatAnthropic(
        model=settings.llm_model, api_key=settings.anthropic_api_key, max_tokens=16000
    )


def build_agent(session: Session, store: VectorStore, model: BaseChatModel | None = None):
    # ProviderStrategy = Claude's native structured output. ToolStrategy would force a tool
    # call, which current Claude models reject.
    return create_agent(
        model or default_model(),
        build_tools(session, store),
        system_prompt=RECOMMENDER_SYSTEM,
        response_format=ProviderStrategy(AgentRecommendation),
    )


def validate_links(session: Session, rec: Recommendation) -> Recommendation:
    """Guardrail 1: every URL must exist in `offers`; others are removed and flagged."""
    urls = {o.url for p in rec.picks for o in p.offers}
    known = set(session.scalars(select(Offer.affiliate_url).where(Offer.affiliate_url.in_(urls))))
    for pick in rec.picks:
        kept = [o for o in pick.offers if o.url in known]
        if len(kept) != len(pick.offers):
            rec.flags.append(
                f"removed {len(pick.offers) - len(kept)} unknown link(s) from pick {pick.rank}"
            )
        pick.offers = kept
    has_links = any(p.offers for p in rec.picks)
    rec.disclosure = AFFILIATE_DISCLOSURE if has_links else None
    return rec


def finalize(session: Session, user: User, answer: AgentRecommendation) -> Recommendation:
    profile = FootProfile.model_validate(user.foot_profile)
    foot = profile.longer_foot
    excluded = excluded_shoe_ids(session, user)
    flags: list[str] = []
    picks: list[Pick] = []
    seen: set[int] = set()

    for agent_pick in answer.picks:
        shoe = session.get(Shoe, agent_pick.shoe_id)
        if shoe is None:
            flags.append(f"dropped unknown shoe id {agent_pick.shoe_id}")
            continue
        if shoe.id in excluded:
            flags.append(f"dropped excluded shoe {shoe.brand} {shoe.model} {shoe.version}")
            continue
        if shoe.id in seen:
            continue
        seen.add(shoe.id)

        note_ids = set(session.scalars(select(FitNote.id).where(FitNote.shoe_id == shoe.id)))
        cited = [n for n in agent_pick.cited_fit_note_ids if n in note_ids]
        if len(cited) != len(agent_pick.cited_fit_note_ids):
            flags.append(f"removed fit-note citations that are not about shoe {shoe.id}")

        size = sizing.pick_size(session, shoe.brand, foot.us_size, foot.width, profile.sex_scale)
        picks.append(
            Pick(
                rank=len(picks) + 1,
                shoe_id=shoe.id,
                brand=shoe.brand,
                model=shoe.model,
                version=shoe.version,
                why_it_fits=agent_pick.why_it_fits,
                cited_fit_note_ids=cited,
                watch_for=agent_pick.watch_for,
                size=size,
                offers=get_offers(session, shoe.id, size.us_size, size.width),
            )
        )
        if len(picks) == TOP_N:
            break

    if len(picks) < TOP_N:
        flags.append(f"only {len(picks)} valid pick(s)")
    rec = Recommendation(picks=picks, summary=answer.summary, disclosure=None, flags=flags)
    return validate_links(session, rec)


def run_recommendation(
    session: Session,
    user_id: uuid.UUID,
    store: VectorStore,
    model: BaseChatModel | None = None,
) -> Recommendation:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError(f"unknown user {user_id}")
    if user.foot_profile is None:
        raise ValueError("user has no confirmed foot profile")
    agent = build_agent(session, store, model)
    result = agent.invoke(
        {"messages": [HumanMessage(recommend_request(str(user_id)))]},
        config={"run_name": "recommend", "recursion_limit": 50},
    )
    return finalize(session, user, result["structured_response"])
