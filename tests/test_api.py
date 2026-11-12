import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import deps
from app.api.main import app
from app.config import get_settings
from app.db.models import Offer, Recommendation
from app.schemas.foot_profile import FootProfile

FIXTURE = Path("data/sample_scans/expected_profile.json")


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_app_served(client):
    """The built Next.js app (web/out) is served at /, or a hint to build it."""
    from app.api.main import WEB_DIR

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    if not WEB_DIR.is_dir():
        assert "npm run build" in page.text
        return
    assert "Never guess on a shoe again." in page.text
    for route in ("/scan/", "/confirm/", "/preferences/", "/history/", "/results/"):
        assert client.get(route).status_code == 200, route
    assert client.get("/health").json() == {"status": "ok"}  # API routes win over the app


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


def test_docs_list_every_endpoint(client):
    """CLAUDE_CODE_PROMPT.md section 7."""
    paths = client.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in paths.items() for m in ops} >= {
        ("/users", "post"),
        ("/users/{user_id}/scans", "post"),
        ("/users/{user_id}/scans/{scan_id}/confirm", "put"),
        ("/users/{user_id}/preferences", "put"),
        ("/users/{user_id}/history", "post"),
        ("/shoes/search", "get"),
        ("/users/{user_id}/recommend", "post"),
        ("/tasks/{task_id}", "get"),
        ("/users/{user_id}/feedback", "post"),
        ("/users/{user_id}/chat", "post"),
        ("/health", "get"),
    }
    assert client.get("/docs").status_code == 200


@pytest.mark.db
def test_unreadable_scan_is_a_clear_error(client, db_session, tmp_path, monkeypatch):
    def broken(paths):
        raise RuntimeError("GOOGLE_API_KEY not set")

    app.dependency_overrides[deps.get_scan_parser] = lambda: broken
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    user_id = client.post("/users").json()["id"]
    response = client.post(f"/users/{user_id}/scans", files=[("files", ("a.png", b"x"))])
    assert response.status_code == 502
    assert "GOOGLE_API_KEY not set" in response.json()["detail"]


@pytest.mark.db
def test_shoe_search(client, catalog):
    names = [s["name"] for s in client.get("/shoes/search", params={"q": "acme roo"}).json()]
    assert names == ["Acme Roomy 1"]
    assert client.get("/shoes/search", params={"q": "nothing"}).json() == []


@pytest.mark.db
def test_full_flow_scan_to_recommendation(client, catalog, db_session, tmp_path, monkeypatch):
    """Upload -> confirm -> preferences -> history -> recommend -> result -> feedback."""
    ids = catalog
    parsed = FootProfile.model_validate_json(FIXTURE.read_text())
    app.dependency_overrides[deps.get_scan_parser] = lambda: lambda paths: parsed
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))

    user_id = client.post("/users").json()["id"]
    assert client.post(f"/users/{user_id}/recommend").status_code == 409  # no profile yet

    bad = client.post(f"/users/{user_id}/scans", files=[("files", ("a.docx", b"x"))])
    assert bad.status_code == 422

    scan = client.post(
        f"/users/{user_id}/scans",
        files=[("files", ("page1.png", b"\x89PNG")), ("files", ("page2.png", b"\x89PNG"))],
    ).json()
    assert scan["parsed_profile"] == json.loads(parsed.model_dump_json())
    assert client.get(f"/users/{user_id}").json()["confirmed_profile"] is None
    assert client.post(f"/users/{user_id}/recommend").status_code == 409  # parsed != confirmed

    corrected = parsed.model_copy(deep=True)
    corrected.right.width = "2E"
    confirmed = client.put(
        f"/users/{user_id}/scans/{scan['scan_id']}/confirm", json=corrected.model_dump(mode="json")
    )
    assert confirmed.json()["confirmed_profile"]["right"]["width"] == "2E"

    prefs = {"weekly_km": 30, "goals": ["Daily training"], "feel": "balanced", "budget_usd": 160}
    assert client.put(f"/users/{user_id}/preferences", json=prefs).status_code == 200
    history = client.post(
        f"/users/{user_id}/history",
        json=[{"raw_name": "acme narrow 2", "rating": "hated", "issues": ["toe_pressure"]}],
    )
    assert history.status_code == 201
    assert history.json()[0]["shoe_id"] == ids["Narrow"]  # resolved from the name
    user = client.get(f"/users/{user_id}").json()
    assert user["preferences"]["budget_usd"] == 160 and len(user["history"]) == 1

    started = client.post(f"/users/{user_id}/recommend")
    assert started.status_code == 202
    task = client.get(f"/tasks/{started.json()['task_id']}").json()
    assert task["status"] == "done", task["error"]

    result = task["result"]
    models = [p["model"] for p in result["picks"]]
    assert models[:2] == ["Roomy", "Daily"]  # roomy toe box, low/medium volume, heel lock
    assert "Narrow" not in models  # hated
    assert all(p["size"]["width"] == "wide" for p in result["picks"])  # 2E -> wide
    assert all(p["why_it_fits"] and 0 <= p["fit_score"] <= 100 for p in result["picks"])
    factors = [f["factor"] for f in result["picks"][0]["breakdown"]]
    assert factors[0] == "width_fit" and set(factors) <= set(result["picks"][0]["contributions"])
    offer_urls = set(db_session.scalars(select(Offer.affiliate_url)))
    links = [o["url"] for p in result["picks"] for o in p["offers"]]
    assert links and set(links) <= offer_urls
    assert result["disclosure"]

    row = db_session.get(Recommendation, started.json()["task_id"])
    assert row.ranker_version == result["ranker_version"]
    assert len(row.candidates) >= len(result["picks"])

    feedback = client.post(
        f"/users/{user_id}/feedback",
        json={"recommendation_id": started.json()["task_id"], "shoe_id": ids["Roomy"],
              "us_size": 9.5, "width": "wide", "outcome": "hated", "kept": False,
              "issues": ["heel_slip"], "notes": "heel slipped"},
    )  # fmt: skip
    assert feedback.status_code == 201
    bad_tag = {"shoe_id": ids["Roomy"], "us_size": 9.5, "width": "wide", "outcome": "fine",
               "issues": ["blisters"]}  # fmt: skip
    assert client.post(f"/users/{user_id}/feedback", json=bad_tag).status_code == 422

    # Feedback feeds the next ranking: a hated pick is excluded.
    again = client.post(f"/users/{user_id}/recommend").json()["task_id"]
    picks = client.get(f"/tasks/{again}").json()["result"]["picks"]
    assert "Roomy" not in [p["model"] for p in picks]


@pytest.mark.db
def test_manual_entry_and_history_replace(client, catalog):
    user_id = client.post("/users").json()["id"]
    profile = json.loads(FIXTURE.read_text())
    scan = client.post(f"/users/{user_id}/scans/manual", json=profile)
    assert scan.status_code == 201 and scan.json()["parser_version"] == "manual"
    assert client.get(f"/users/{user_id}").json()["confirmed_profile"] == profile

    client.post(f"/users/{user_id}/history", json=[{"raw_name": "Bolt Daily 5", "rating": "fine"}])
    replaced = client.put(
        f"/users/{user_id}/history", json=[{"raw_name": "Mystery 9", "rating": "loved"}]
    ).json()
    assert [(h["raw_name"], h["shoe_id"]) for h in replaced] == [("Mystery 9", None)]
    assert len(client.get(f"/users/{user_id}").json()["history"]) == 1


@pytest.mark.db
def test_failed_task_reports_error(client, catalog, monkeypatch):
    def boom(session, user_id):
        raise RuntimeError("ranker exploded")

    monkeypatch.setattr("app.api.routes.recommend.build_recommendation", boom)
    user_id = client.post("/users").json()["id"]
    client.post(f"/users/{user_id}/scans/manual", json=json.loads(FIXTURE.read_text()))

    task_id = client.post(f"/users/{user_id}/recommend").json()["task_id"]
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "failed"
    assert task["error"] == "RuntimeError: ranker exploded"
    assert client.get("/tasks/00000000-0000-0000-0000-000000000000").status_code == 404
