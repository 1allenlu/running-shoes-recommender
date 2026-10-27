import asyncio
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import mcp_server
from app.db.models import Feedback, User
from app.mcp_server import (
    Preferences,
    find_shoes_impl,
    fit_check_impl,
    get_offers_impl,
    server,
    vibe_from_profile,
)
from app.schemas.foot_profile import FootProfile

TEMPLATE = json.loads(Path("data/sample_scans/expected.template.json").read_text())


def test_vibe_from_scan():
    # Template: longer foot is men's E (wide), low instep.
    vibe = vibe_from_profile(FootProfile.model_validate(TEMPLATE), "soft")
    assert vibe == "roomy toe box, wide forefoot, snug low-volume upper, secure heel lock, " \
        "soft cushioning"  # fmt: skip


def test_server_lists_three_tools():
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {"find_shoes", "fit_check", "get_offers"}


@pytest.fixture
def runner(db_session, indexed) -> User:
    user = User(
        foot_profile=TEMPLATE,
        questionnaire={"feel": "soft", "disliked_shoes": [{"model": "Narrow 2"}]},
    )
    db_session.add(user)
    db_session.commit()
    db_session.add(Feedback(user_id=user.id, shoe_id=indexed["Plush"], us_size=9, width="wide",
                            rating=2, notes="toe box too narrow"))  # fmt: skip
    db_session.commit()
    return user


@pytest.mark.db
def test_find_shoes_for_user(runner, db_session, store):
    result = find_shoes_impl(db_session, store, str(runner.id))
    names = [c["name"] for c in result["candidates"]]
    assert "Acme Narrow 2" not in names  # disliked; also not made in wide
    assert "Acme Plush 3" not in names  # rated 2
    assert result["filters"]["width"] == "wide"
    roomy = next(c for c in result["candidates"] if c["name"] == "Acme Roomy 1")
    assert (roomy["size"]["us_size"], roomy["size"]["confident"]) == (9.0, True)


@pytest.mark.db
def test_find_shoes_for_raw_profile_with_preferences(indexed, db_session, store):
    prefs = Preferences(looking_for="plush soft max cushion", budget_usd=200, exclude=["Roomy 1"])
    result = find_shoes_impl(db_session, store, TEMPLATE, prefs)
    names = [c["name"] for c in result["candidates"]]
    assert names[0] == "Acme Plush 3"
    assert "Acme Roomy 1" not in names
    assert result["searched_for"] == "plush soft max cushion"


@pytest.mark.db
def test_fit_check(runner, db_session, store):
    result = fit_check_impl(db_session, store, str(runner.id), "Acme Plush 3")
    assert result["shoe"]["name"] == "Acme Plush 3"
    assert result["excluded_for_this_runner"] is True
    assert result["runner_feedback"][0]["notes"] == "toe box too narrow"
    assert result["fit_notes"]["toe_box"][0]["text"] == "roomy forefoot"
    with pytest.raises(ValueError, match="no catalog shoe matches 'Zoom 9'"):
        fit_check_impl(db_session, store, str(runner.id), "Zoom 9")


@pytest.mark.db
def test_get_offers_has_links_and_disclosure(indexed, db_session):
    result = get_offers_impl(db_session, "Roomy 1", 9.0, "wide")
    assert [o["retailer"] for o in result["offers"]] == ["Store Y", "Store X"]
    assert all(o["url"].startswith("https://example.com/") for o in result["offers"])
    assert result["disclosure"]
    assert get_offers_impl(db_session, "Roomy 1", 15.0, "wide") == {
        "shoe": "Acme Roomy 1", "us_size": 15.0, "width": "wide", "offers": [],
        "disclosure": None,
    }  # fmt: skip


@pytest.mark.db
def test_tools_through_the_mcp_server(runner, store, monkeypatch):
    """What Claude Desktop does: call tools by name with JSON arguments."""
    monkeypatch.setattr(mcp_server, "_store", lambda: store)

    def call(name, args):
        result = asyncio.run(server.call_tool(name, args))
        assert not result.is_error, result
        return json.loads(result.content[0].text)

    offers = call("get_offers", {"shoe": "Roomy 1", "size": 9.0, "width": "wide"})
    assert len(offers["offers"]) == 2
    found = call("find_shoes", {"profile_or_user_id": str(runner.id)})
    assert found["candidates"]
    check = call("fit_check", {"user_id": str(runner.id), "shoe": "Bolt Daily 5"})
    assert check["shoe"]["name"] == "Bolt Daily 5"

    with pytest.raises(ToolError, match="width must be standard, wide or extra-wide"):
        asyncio.run(server.call_tool("get_offers", {"shoe": "Roomy 1", "size": 9, "width": "E"}))
    with pytest.raises(ToolError, match="no catalog shoe matches 'Zoom 9'"):
        asyncio.run(server.call_tool("get_offers", {"shoe": "Zoom 9", "size": 9, "width": "wide"}))
