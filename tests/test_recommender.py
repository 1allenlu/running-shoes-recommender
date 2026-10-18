import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent.recommender import run_recommendation, validate_links
from app.db.models import FitNote, Offer, User
from app.schemas.foot_profile import FootProfile
from app.schemas.recommendation import (
    AFFILIATE_DISCLOSURE,
    OfferLink,
    Pick,
    Recommendation,
    SizeAdvice,
)
from tests.agent_script import agent_pick, scripted_agent, tool_result

pytestmark = pytest.mark.db

TEMPLATE = Path("data/sample_scans/expected.template.json")


@pytest.fixture
def user(db_session) -> User:
    user = User(
        foot_profile=json.loads(TEMPLATE.read_text()),  # longer foot: right, 8.3 E
        questionnaire={"disliked_shoes": [{"model": "Acme Narrow 2", "notes": "too narrow"}]},
    )
    db_session.add(user)
    db_session.commit()
    return user


def note_id(session, shoe_id: int) -> int:
    return session.scalar(select(FitNote.id).where(FitNote.shoe_id == shoe_id).limit(1))


def test_run_enforces_guardrails(indexed, db_session, store, user):
    ids = indexed
    roomy_note, plush_note = note_id(db_session, ids["Roomy"]), note_id(db_session, ids["Plush"])
    seen = {}

    def final(messages):
        seen["profile"] = tool_result(messages, "get_profile")
        seen["notes"] = tool_result(messages, "get_fit_notes")
        return {
            "summary": "Wide forefoot, low instep.",
            "picks": [
                agent_pick(ids["Narrow"]),  # disliked -> dropped
                agent_pick(999),  # not in catalog -> dropped
                agent_pick(ids["Roomy"], [roomy_note, plush_note]),  # foreign citation removed
                agent_pick(ids["Roomy"]),  # duplicate -> skipped
                agent_pick(ids["Plush"]),
                agent_pick(ids["Daily"]),
                agent_pick(ids["Tempo"]),  # beyond top 3
            ],
        }

    rec = run_recommendation(db_session, user.id, store, model=scripted_agent(final))

    assert seen["profile"]["excluded_shoe_ids"] == [ids["Narrow"]]
    assert seen["notes"]  # the agent saw fit notes for its top search result
    assert [(p.rank, p.model) for p in rec.picks] == [(1, "Roomy"), (2, "Plush"), (3, "Daily")]
    assert rec.picks[0].cited_fit_note_ids == [roomy_note]
    assert sorted(rec.flags) == [
        "dropped excluded shoe Acme Narrow 2",
        "dropped unknown shoe id 999",
        f"removed fit-note citations that are not about shoe {ids['Roomy']}",
    ]

    acme, bolt = rec.picks[0].size, rec.picks[2].size
    assert (acme.us_size, acme.width, acme.confident) == (9.0, "wide", True)
    assert (bolt.us_size, bolt.width, bolt.confident) == (8.5, "wide", False)

    offer_urls = set(db_session.scalars(select(Offer.affiliate_url)))
    for pick in rec.picks:
        assert [o.retailer for o in pick.offers] == ["Store Y", "Store X"]  # cheapest first
        assert all(o.url in offer_urls for o in pick.offers)
        assert all(
            f"size={pick.size.us_size}&width={pick.size.width}" in o.url for o in pick.offers
        )
    assert rec.disclosure == AFFILIATE_DISCLOSURE


def test_fewer_than_three_valid_picks_is_flagged(indexed, db_session, store, user):
    final = lambda _: {"summary": "s", "picks": [agent_pick(indexed["Roomy"])]}  # noqa: E731
    rec = run_recommendation(db_session, user.id, store, model=scripted_agent(final))
    assert len(rec.picks) == 1
    assert rec.flags == ["only 1 valid pick(s)"]


def test_unknown_links_removed_and_flagged(catalog, db_session):
    real = db_session.scalars(select(Offer)).first()
    size = SizeAdvice(us_size=9, width="wide", basis="b", confident=True)
    offers = [
        OfferLink(offer_id=real.id, retailer=real.retailer, price_usd=1, url=real.affiliate_url),
        OfferLink(offer_id=0, retailer="Evil", price_usd=1, url="https://example.com/made-up"),
    ]
    pick = Pick(
        rank=1, shoe_id=real.shoe_id, brand="b", model="m", version="v", why_it_fits=[],
        cited_fit_note_ids=[], watch_for=[], size=size, offers=offers,
    )  # fmt: skip
    rec = validate_links(db_session, Recommendation(picks=[pick], summary="s", disclosure=None))
    assert [o.url for o in rec.picks[0].offers] == [real.affiliate_url]
    assert rec.flags == ["removed 1 unknown link(s) from pick 1"]
    assert rec.disclosure == AFFILIATE_DISCLOSURE

    pick.offers = offers[1:]
    rec = validate_links(db_session, Recommendation(picks=[pick], summary="s", disclosure=None))
    assert rec.picks[0].offers == [] and rec.disclosure is None


def test_requires_confirmed_profile(catalog, db_session, store):
    user = User()
    db_session.add(user)
    db_session.commit()
    with pytest.raises(ValueError, match="no confirmed foot profile"):
        run_recommendation(db_session, user.id, store, model=scripted_agent(lambda _: {}))


def test_longer_foot_drives_size():
    profile = FootProfile.model_validate_json(TEMPLATE.read_text())
    assert (profile.longer_foot.us_size, profile.longer_foot.width) == (8.3, "E")
