"""Phase 4 check with the real model: 5 hand-written profiles -> 3 valid picks with sizes,
every link in `offers`. Runs on the real seed catalog and sample feed. Calls the Anthropic API.
"""

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent.recommender import run_recommendation
from app.agent.tools import resolve_shoe_names
from app.db.models import Offer, User
from app.ingest.embed_fit_notes import embed_fit_notes
from app.ingest.load_catalog import DEFAULT_SEED_DIR, load_catalog
from app.ingest.load_offers import DEFAULT_FEED, load_offers
from app.llm import llm_ready
from app.retrieval.store import get_store

PROFILES = json.loads(Path("evals/datasets/agent_profiles.json").read_text())

pytestmark = [pytest.mark.db, pytest.mark.llm]


@pytest.fixture
def real_catalog(db_session, tmp_path):
    # Chroma only: the search backend doesn't change the model's work, and each profile costs
    # ~10-20 model requests, which matters on free tiers.
    ready, reason = llm_ready()
    if not ready:
        pytest.skip(reason)
    shutil.copytree(DEFAULT_SEED_DIR, tmp_path / "seed")
    load_catalog(db_session, tmp_path / "seed")
    load_offers(db_session, DEFAULT_FEED)
    store = get_store(persist_directory=str(tmp_path / "chroma"))
    embed_fit_notes(db_session, store)
    return store


@pytest.mark.parametrize("case", PROFILES, ids=[p["name"] for p in PROFILES])
def test_agent_returns_three_valid_picks(case, real_catalog, db_session):
    user = User(foot_profile=case["foot_profile"], questionnaire=case["questionnaire"])
    db_session.add(user)
    db_session.commit()

    rec = run_recommendation(db_session, user.id, real_catalog)

    assert len(rec.picks) == 3, rec.flags
    assert all(p.size.us_size > 0 for p in rec.picks)
    assert not [f for f in rec.flags if "link" in f]
    offer_urls = set(db_session.scalars(select(Offer.affiliate_url)))
    assert all(o.url in offer_urls for p in rec.picks for o in p.offers)
    disliked = [s["model"] for s in case["questionnaire"]["disliked_shoes"]]
    excluded = set(resolve_shoe_names(db_session, disliked).values())
    assert not excluded & {p.shoe_id for p in rec.picks}


def test_constraint_chain_reads_relative_complaints():
    """Real model: "toe box too narrow" on a medium toe box should require a roomy one."""
    ready, reason = llm_ready()
    if not ready:
        pytest.skip(reason)
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agent.feedback import CONSTRAINT_SYSTEM, build_constraint_chain

    item = {
        "shoe": "Acme Plush 3",
        "rating": 2,
        "size_worn": "9 wide",
        "specs": {"toe_box": "medium", "upper_volume": "high", "heel_lock": True},
        "note": "toe box too narrow, and my heel slipped on downhills",
    }
    result = build_constraint_chain().invoke(
        [SystemMessage(CONSTRAINT_SYSTEM), HumanMessage(json.dumps([item]))]
    )
    assert result.toe_box == ["roomy"]
    assert result.heel_lock is True
