import asyncio
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import mcp_server
from app.db.models import Feedback, Scan, User
from app.mcp_server import find_shoes_impl, fit_check_impl, get_offers_impl, server
from app.schemas.preferences import Preferences

FIXTURE = json.loads(Path("data/sample_scans/expected_profile.json").read_text())


def test_server_lists_three_tools():
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {"find_shoes", "fit_check", "get_offers"}


@pytest.fixture
def runner(db_session, indexed) -> User:
    user = User()
    db_session.add(user)
    db_session.commit()
    db_session.add(Scan(user_id=user.id, parser_version="manual", confirmed_profile=FIXTURE))
    db_session.add(Feedback(user_id=user.id, shoe_id=indexed["Plush"], us_size=9, width="wide",
                            outcome="hated", issues=["too_much_volume"]))  # fmt: skip
    db_session.commit()
    return user


@pytest.mark.db
def test_find_shoes_for_user_uses_the_ranker(runner, db_session):
    result = find_shoes_impl(db_session, str(runner.id))
    names = [f"{p['brand']} {p['model']} {p['version']}" for p in result["picks"]]
    assert names[:2] == ["Acme Roomy 1", "Bolt Daily 5"]
    assert "Acme Plush 3" not in names
    assert any(e["name"] == "Acme Plush 3" for e in result["excluded"])
    assert all(p["contributions"] for p in result["picks"])
    assert result["disclosure"]


@pytest.mark.db
def test_find_shoes_for_raw_profile_with_preferences(indexed, db_session):
    result = find_shoes_impl(db_session, FIXTURE, Preferences(budget_usd=125))
    prices = {"Roomy": 140, "Narrow": 130, "Plush": 170, "Tempo": 150, "Daily": 120}
    assert all(prices[p["model"]] <= 125 * 1.1 for p in result["picks"])


@pytest.mark.db
def test_fit_check(runner, db_session, store):
    plush = fit_check_impl(db_session, store, str(runner.id), "Acme Plush 3")
    assert plush["excluded_because"] == "you rated this model hated"
    assert plush["fit"] is None
    assert plush["runner_history"][0]["rating"] == "hated"
    assert plush["fit_notes"]["toe_box"][0]["text"] == "roomy forefoot"

    roomy = fit_check_impl(db_session, store, str(runner.id), "Roomy 1")
    assert roomy["rank"] == 1 and roomy["fit"]["subscores"]["combo_fit"]["value"] == 1.0
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
    assert len(found["picks"]) == 3
    check = call("fit_check", {"user_id": str(runner.id), "shoe": "Bolt Daily 5"})
    assert check["shoe"] == "Bolt Daily 5"

    with pytest.raises(ToolError, match="width must be standard, wide or extra-wide"):
        asyncio.run(server.call_tool("get_offers", {"shoe": "Roomy 1", "size": 9, "width": "E"}))
    with pytest.raises(ToolError, match="no catalog shoe matches 'Zoom 9'"):
        asyncio.run(server.call_tool("get_offers", {"shoe": "Zoom 9", "size": 9, "width": "wide"}))
    with pytest.raises(ToolError, match="not a user id"):
        asyncio.run(server.call_tool("fit_check", {"user_id": "nobody", "shoe": "Roomy 1"}))
