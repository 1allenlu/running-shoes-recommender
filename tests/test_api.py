import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.recommender import run_recommendation
from app.api import deps
from app.api.main import app
from app.config import get_settings
from app.db.models import Offer
from app.schemas.foot_profile import FootProfile
from tests.agent_script import agent_pick, scripted_agent

TEMPLATE = Path("data/sample_scans/expected.template.json")


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_app_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Never guess on a shoe again." in page.text
    for asset in ("/app.js", "/styles.css"):
        assert client.get(asset).status_code == 200


def test_status_reports_llm_readiness(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "google")
    monkeypatch.setattr(get_settings(), "google_api_key", None)
    monkeypatch.setattr(get_settings(), "llm_model", "")
    body = client.get("/status").json()
    assert body == {
        "llm_ready": False,
        "reason": "GOOGLE_API_KEY not set",
        "provider": "google",
        "model": "gemini-3.5-flash-lite",
    }


def test_unreadable_scan_is_a_clear_error(client, tmp_path, monkeypatch):
    def broken(paths):
        raise RuntimeError("GOOGLE_API_KEY not set")

    app.dependency_overrides[deps.get_scan_parser] = lambda: broken
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    user_id = client.post("/users").json()["id"]
    response = client.post(f"/users/{user_id}/scans", files=[("files", ("a.png", b"x"))])
    assert response.status_code == 502
    assert "GOOGLE_API_KEY not set" in response.json()["detail"]


def test_docs_list_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in paths.items() for m in ops} >= {
        ("/users", "post"),
        ("/users/{user_id}/scans", "post"),
        ("/users/{user_id}/profile", "put"),
        ("/users/{user_id}/questionnaire", "put"),
        ("/users/{user_id}/recommend", "post"),
        ("/tasks/{task_id}", "get"),
        ("/users/{user_id}/feedback", "post"),
        ("/health", "get"),
        ("/status", "get"),
    }
    assert client.get("/docs").status_code == 200


@pytest.mark.db
def test_full_flow_scan_to_recommendation(
    client, indexed, store, db_session, tmp_path, monkeypatch
):
    """Scan upload -> confirm profile -> questionnaire -> recommend -> task result -> feedback."""
    ids = indexed
    parsed = FootProfile.model_validate_json(TEMPLATE.read_text())
    final = lambda _: {  # noqa: E731
        "summary": "Wide forefoot, low instep.",
        "picks": [agent_pick(ids["Roomy"]), agent_pick(ids["Plush"]), agent_pick(ids["Daily"])],
    }
    app.dependency_overrides[deps.get_scan_parser] = lambda: lambda paths: parsed
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_recommender] = lambda: (
        lambda session, user_id, st: run_recommendation(
            session, user_id, st, model=scripted_agent(final)
        )
    )
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))

    user_id = client.post("/users").json()["id"]

    # Recommending before a confirmed profile is refused.
    assert client.post(f"/users/{user_id}/recommend").status_code == 409

    bad = client.post(f"/users/{user_id}/scans", files=[("files", ("a.docx", b"x"))])
    assert bad.status_code == 422

    scan = client.post(
        f"/users/{user_id}/scans",
        files=[("files", ("page1.png", b"\x89PNG")), ("files", ("page2.png", b"\x89PNG"))],
    )
    assert scan.status_code == 201
    assert scan.json()["parsed_profile"] == json.loads(parsed.model_dump_json())
    assert client.get(f"/users/{user_id}").json()["foot_profile"] is None  # not yet confirmed

    corrected = parsed.model_copy(deep=True)
    corrected.right.width = "2E"
    profile = client.put(f"/users/{user_id}/profile", json=corrected.model_dump(mode="json"))
    assert profile.json()["foot_profile"]["right"]["width"] == "2E"

    questionnaire = {"weekly_km": 30, "feel": "balanced", "budget_usd": 160}
    assert client.put(f"/users/{user_id}/questionnaire", json=questionnaire).status_code == 200

    started = client.post(f"/users/{user_id}/recommend")
    assert started.status_code == 202
    task = client.get(f"/tasks/{started.json()['task_id']}").json()
    assert task["status"] == "done", task["error"]

    result = task["result"]
    assert [p["model"] for p in result["picks"]] == ["Roomy", "Plush", "Daily"]
    assert all(p["size"]["width"] == "wide" for p in result["picks"])  # 2E -> wide
    offer_urls = set(db_session.scalars(select(Offer.affiliate_url)))
    links = [o["url"] for p in result["picks"] for o in p["offers"]]
    assert links and set(links) <= offer_urls
    assert result["disclosure"]

    feedback = client.post(
        f"/users/{user_id}/feedback",
        json={"shoe_id": ids["Roomy"], "us_size": 9.0, "width": "wide", "rating": 2,
              "notes": "toe box too narrow"},
    )  # fmt: skip
    assert feedback.status_code == 201
    bad_rating = {"shoe_id": ids["Roomy"], "us_size": 9.0, "width": "wide", "rating": 6}
    assert client.post(f"/users/{user_id}/feedback", json=bad_rating).status_code == 422


@pytest.mark.db
def test_failed_task_reports_error(client, indexed, store):
    def boom(session, user_id, st):
        raise RuntimeError("agent exploded")

    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_recommender] = lambda: boom
    user_id = client.post("/users").json()["id"]
    profile = json.loads(TEMPLATE.read_text())
    client.put(f"/users/{user_id}/profile", json=profile)

    task_id = client.post(f"/users/{user_id}/recommend").json()["task_id"]
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "failed"
    assert task["error"] == "RuntimeError: agent exploded"
    assert client.get("/tasks/00000000-0000-0000-0000-000000000000").status_code == 404
