"""Follow-up chat (Phase 8): tools call the pipeline; the model never ranks."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.api.main import app
from app.api.routes.chat import get_chat_model_factory
from app.chat_agent import build_tools
from app.db.models import Feedback, Scan, User
from tests.fakes import ScriptedChatModel

FIXTURE = json.loads(Path("data/sample_scans/expected_profile.json").read_text())

pytestmark = pytest.mark.db


@pytest.fixture
def runner(db_session, catalog) -> User:
    user = User()
    db_session.add(user)
    db_session.commit()
    db_session.add(Scan(user_id=user.id, parser_version="manual", confirmed_profile=FIXTURE))
    db_session.commit()
    return user


@pytest.fixture
def tools(db_session, runner):
    return {t.name: t for t in build_tools(db_session, runner.id)}


def picks(tools, **args) -> list[str]:
    msg = tools["rerank"].invoke({"type": "tool_call", "id": "1", "name": "rerank", "args": args})
    return [f"{p['model']}" for p in msg.artifact["picks"]], msg.artifact


def test_rerank_cheaper_respects_budget(tools):
    names, _ = picks(tools)
    assert "Roomy" in names  # $140
    cheap, _ = picks(tools, budget_usd=120)  # +10% allowed: up to $132
    assert cheap and set(cheap) <= {"Daily", "Narrow"}


def test_rerank_exclude_drops_that_shoe(tools):
    names, _ = picks(tools)
    first = names[0]
    after, _ = picks(tools, exclude=[f"acme {first.lower()} 1"])
    assert first not in after


def test_compare_two_shoes(tools):
    out = tools["compare"].invoke({"shoe_a": "Acme Roomy 1", "shoe_b": "Acme Narrow 2"})
    assert out["a"]["shoe"] == "Acme Roomy 1" and out["b"]["shoe"] == "Acme Narrow 2"
    assert "width_fit" in out["a"]["factors"] or out["a"]["excluded_because"]
    with pytest.raises(ValueError, match="Known shoes"):
        tools["compare"].invoke({"shoe_a": "Mystery 9", "shoe_b": "Acme Roomy 1"})


def test_record_feedback_saves(tools, db_session, runner, catalog):
    tools["record_feedback"].invoke(
        {"shoe": "Roomy 1", "us_size": 9.5, "width": "wide", "outcome": "loved", "kept": True}
    )
    row = db_session.scalars(select(Feedback).where(Feedback.user_id == runner.id)).one()
    assert (row.shoe_id, row.outcome, row.kept) == (catalog["Roomy"], "loved", True)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_chat_endpoint_streams_tool_picks_and_text(runner):
    model = ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "rerank", "args": {"budget_usd": 120}, "id": "c1", "type": "tool_call"}
                ],
            ),  # fmt: skip
            AIMessage(content="Here are cheaper options."),
        ]
    )
    app.dependency_overrides[get_chat_model_factory] = lambda: lambda: model
    try:
        client = TestClient(app)
        body = {"messages": [{"role": "user", "content": "something under $120"}]}
        response = client.post(f"/users/{runner.id}/chat", json=body)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "tool" and kinds[-1] == "done"
    picks_event = next(d for e, d in events if e == "picks")
    assert picks_event["picks"] and picks_event["ranker_version"]
    assert "".join(d["text"] for e, d in events if e == "token") == "Here are cheaper options."
    # The model saw the tool result before answering.
    assert any(m.type == "tool" for m in model.seen[-1])


def test_chat_needs_profile_and_model(db_session, monkeypatch):
    from app.config import get_settings

    user = User()
    db_session.add(user)
    db_session.commit()
    client = TestClient(app)
    body = {"messages": [{"role": "user", "content": "hi"}]}
    monkeypatch.setattr(get_settings(), "llm_provider", "google")
    monkeypatch.setattr(get_settings(), "google_api_key", None)
    assert client.post(f"/users/{user.id}/chat", json=body).status_code == 503
    app.dependency_overrides[get_chat_model_factory] = lambda: lambda: None
    try:
        assert client.post(f"/users/{user.id}/chat", json=body).status_code == 409
    finally:
        app.dependency_overrides.clear()
