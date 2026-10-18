"""Agent tools against the fake catalog. Search tests run on both Chroma and pgvector."""

import pytest

from app.agent.sizing import pick_size, shoe_width
from app.agent.tools import build_tools, get_fit_notes, get_profile, similar_to
from app.db.models import Feedback, User
from app.db.session import SessionLocal
from app.retrieval.hybrid import ShoeFilters, search_shoes
from app.retrieval.pgvector_store import PgFitNoteStore
from tests.fakes import KeywordEmbeddings

pytestmark = pytest.mark.db


def names(candidates) -> list[str]:
    return [c.name for c in candidates]


def test_search_ranks_by_fit_notes(indexed, db_session, store):
    found = search_shoes(db_session, store, ShoeFilters(), "roomy toe box")
    assert len(found) == 5
    assert found[0].name in {"Acme Roomy 1", "Bolt Daily 5"}
    assert found[0].score > found[-1].score
    assert "roomy" in found[0].best_fit_note


def test_search_filters_keep_unknown_specs(indexed, db_session, store):
    found = search_shoes(db_session, store, ShoeFilters(width="wide", toe_box=["roomy"]), "x")
    # Narrow is standard-only and Plush has a medium toe box; Bolt Tempo's specs are unknown.
    assert sorted(names(found)) == ["Acme Roomy 1", "Bolt Daily 5", "Bolt Tempo 4"]
    tempo = next(c for c in found if c.name == "Bolt Tempo 4")
    assert {"widths_available", "toe_box"} <= set(tempo.unknown_specs)


def test_search_budget_category_and_exclusions(indexed, db_session, store):
    filters = ShoeFilters(
        max_price_usd=145, categories=["daily"], exclude_shoe_ids=[indexed["Daily"]]
    )
    assert sorted(names(search_shoes(db_session, store, filters, "x"))) == [
        "Acme Narrow 2",
        "Acme Roomy 1",
    ]


def test_get_fit_notes_stays_on_one_shoe(indexed, store):
    notes = get_fit_notes(store, indexed["Plush"], "how roomy is the forefoot?")
    assert len(notes) == 3
    assert notes[0]["text"] == "roomy forefoot"
    assert all(n["verified"] for n in notes)  # source "test", not draft-unverified


def test_similar_to_excludes_itself(indexed, db_session, store):
    found = similar_to(db_session, store, indexed["Roomy"])
    assert "Acme Roomy 1" not in names(found)
    assert found[0].name == "Bolt Daily 5"  # shares "roomy toe box" and "secure heel"


def test_pgvector_store_rejects_multi_chunk_notes():
    store = PgFitNoteStore(KeywordEmbeddings(), SessionLocal)
    with pytest.raises(ValueError, match="one embedding per fit note"):
        store.add_texts(["a"], [{"fit_note_id": 1}], ids=["fit_note:1:1"])


def test_width_letters_map_by_scale():
    assert shoe_width("D") == "standard"
    assert shoe_width("2E") == "wide"
    assert shoe_width("3E") == "extra-wide"
    assert shoe_width("D", "women") == "wide"


def test_pick_size_uses_brand_chart(catalog, db_session):
    advice = pick_size(db_session, "Acme", 8.3, "E")
    # 8.3 -> ~260.9 mm on the reference chart; Acme runs small so 8.5 is too short.
    assert (advice.us_size, advice.width, advice.confident) == (9.0, "wide", True)
    assert advice.sizing_note == "runs small"


def test_pick_size_falls_back_without_chart(catalog, db_session):
    advice = pick_size(db_session, "Bolt", 8.3, "D")
    assert (advice.us_size, advice.width, advice.confident) == (8.5, "standard", False)
    assert pick_size(db_session, "Bolt", 9.0, "D").us_size == 9.0


def test_get_profile_resolves_loved_and_excluded(catalog, db_session):
    user = User(
        foot_profile={"sex_scale": "men"},
        questionnaire={
            "loved_shoes": [{"model": "Daily 5", "notes": "comfy"}],
            "disliked_shoes": [{"model": "Acme Narrow 2"}, {"model": "Not In Catalog 9"}],
        },
    )
    db_session.add(user)
    db_session.commit()
    db_session.add(
        Feedback(user_id=user.id, shoe_id=catalog["Plush"], us_size=9, width="wide", rating=2)
    )
    db_session.commit()

    profile = get_profile(db_session, user.id)
    assert profile["loved_shoe_ids"] == {"Daily 5": catalog["Daily"]}
    assert profile["excluded_shoe_ids"] == sorted([catalog["Narrow"], catalog["Plush"]])
    assert profile["feedback"][0]["rating"] == 2


def test_offer_tool_hides_urls(indexed, db_session, store):
    tools = {t.name: t for t in build_tools(db_session, store)}
    assert set(tools) == {
        "get_profile", "search_shoes", "get_fit_notes", "similar_to", "pick_size", "get_offers"
    }  # fmt: skip
    offers = tools["get_offers"].invoke(
        {"shoe_id": indexed["Roomy"], "us_size": 9.0, "width": "standard"}
    )
    assert offers and all("url" not in o for o in offers)
    found = tools["search_shoes"].invoke({"filters": {"width": "wide"}, "vibe": "roomy"})
    assert "Acme Narrow 2" not in [c["name"] for c in found]
