"""Phase 10: feedback excludes or lowers shoes, and notes become constraints for the next run."""

import json
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from app.agent.feedback import FeedbackConstraints, derive_constraints, merge_filters
from app.agent.recommender import run_recommendation
from app.db.models import Feedback, Shoe, User
from app.retrieval.hybrid import ShoeFilters
from tests.agent_script import agent_pick, scripted_agent, tool_result

TEMPLATE = Path("data/sample_scans/expected.template.json")


def fake_chain(result: FeedbackConstraints, seen: list):
    return RunnableLambda(lambda messages: seen.append(messages) or result)


def test_merge_tightens_filters():
    agent = ShoeFilters(toe_box=["medium", "roomy"], width="standard", max_drop_mm=10)
    learned = FeedbackConstraints(toe_box=["roomy"], width="wide", max_drop_mm=8, heel_lock=True)
    merged = merge_filters(agent, learned)
    assert merged.toe_box == ["roomy"]
    assert merged.width == "wide"
    assert merged.max_drop_mm == 8
    assert merged.heel_lock is True
    assert merge_filters(agent, None) == agent


def test_merge_feedback_wins_on_disagreement():
    merged = merge_filters(ShoeFilters(toe_box=["narrow"]), FeedbackConstraints(toe_box=["roomy"]))
    assert merged.toe_box == ["roomy"]


def test_violations_use_known_specs_only():
    c = FeedbackConstraints(toe_box=["roomy"], width="wide", heel_lock=True, max_drop_mm=8)
    narrow = Shoe(toe_box="narrow", widths_available=["standard"], heel_lock=False, drop_mm=10)
    assert c.violations(narrow) == [
        "toe box is narrow, need roomy",
        "not made in wide or wider",
        "no locked-in heel",
        "drop 10 mm > 8 mm",
    ]
    unknown = Shoe(toe_box=None, widths_available=None, heel_lock=None, drop_mm=None)
    assert c.violations(unknown) == []
    extra_wide = Shoe(widths_available=["standard", "extra-wide"])
    assert FeedbackConstraints(width="wide").violations(extra_wide) == []


@pytest.fixture
def runner(db_session) -> User:
    user = User(foot_profile=json.loads(TEMPLATE.read_text()), questionnaire={})
    db_session.add(user)
    db_session.commit()
    return user


@pytest.mark.db
def test_no_notes_means_no_model_call(catalog, db_session, runner):
    db_session.add(Feedback(user_id=runner.id, shoe_id=catalog["Plush"], us_size=9,
                            width="wide", rating=4, notes=None))  # fmt: skip
    db_session.commit()
    seen = []
    assert derive_constraints(db_session, runner, fake_chain(FeedbackConstraints(), seen)) is None
    assert seen == []


@pytest.mark.db
def test_negative_feedback_shapes_next_recommendation(indexed, db_session, store, runner):
    ids = indexed
    db_session.add_all(
        [
            Feedback(user_id=runner.id, shoe_id=ids["Plush"], us_size=9, width="wide",
                     rating=2, notes="toe box too narrow, toes went numb after 10k"),
            Feedback(user_id=runner.id, shoe_id=ids["Daily"], us_size=9, width="wide",
                     rating=3, notes=None),
        ]
    )  # fmt: skip
    db_session.commit()

    chain_inputs = []
    learned = FeedbackConstraints(toe_box=["roomy"], other=[])
    seen = {}

    def final(messages):
        seen["profile"] = tool_result(messages, "get_profile")
        seen["search"] = [c["name"] for c in tool_result(messages, "search_shoes")]
        return {
            "summary": "Needs more toe room than the Plush gave.",
            "picks": [
                agent_pick(ids["Plush"]),  # rated 2 -> excluded
                agent_pick(ids["Narrow"]),  # narrow toe box -> conflicts with feedback
                agent_pick(ids["Roomy"]),
                agent_pick(ids["Daily"]),
                agent_pick(ids["Tempo"]),  # toe box unknown -> allowed
            ],
        }

    rec = run_recommendation(
        db_session,
        runner.id,
        store,
        model=scripted_agent(final),
        constraint_chain=fake_chain(learned, chain_inputs),
    )

    # The chain saw the note with the shoe's specs, so "too narrow" can become "roomy".
    note_items = json.loads(chain_inputs[0][1].content)
    assert note_items == [
        {
            "shoe": "Acme Plush 3",
            "rating": 2,
            "size_worn": "9 wide",
            "specs": {
                "toe_box": "medium",
                "upper_volume": "high",
                "widths_available": ["standard", "wide", "extra-wide"],
                "heel_lock": True,
                "drop_mm": 8.0,
                "stack_heel_mm": 30.0,
            },
            "note": "toe box too narrow, toes went numb after 10k",
        }
    ]

    # The agent was told, and its searches were narrowed automatically.
    assert seen["profile"]["feedback_constraints"]["toe_box"] == ["roomy"]
    assert seen["profile"]["excluded_shoe_ids"] == [ids["Plush"]]
    assert seen["profile"]["deprioritized_shoe_ids"] == [ids["Daily"]]
    assert set(seen["search"]) == {"Acme Roomy 1", "Bolt Daily 5", "Bolt Tempo 4"}

    # And the final answer excludes the shoe and respects the constraint.
    assert [p.model for p in rec.picks] == ["Roomy", "Daily", "Tempo"]
    assert "dropped excluded shoe Acme Plush 3" in rec.flags
    assert (
        "dropped Acme Narrow 2: conflicts with your feedback (toe box is narrow, need roomy)"
        in rec.flags
    )


@pytest.mark.db
def test_width_from_feedback_raises_order_width(indexed, db_session, store, runner):
    tight = Feedback(user_id=runner.id, shoe_id=indexed["Roomy"], us_size=9, width="wide",
                     rating=2, notes="still too tight everywhere")  # fmt: skip
    db_session.add(tight)
    db_session.commit()

    def final(_):
        return {"summary": "s", "picks": [agent_pick(indexed["Plush"])]}

    rec = run_recommendation(
        db_session,
        runner.id,
        store,
        model=scripted_agent(final),
        constraint_chain=fake_chain(FeedbackConstraints(width="extra-wide"), []),
    )
    size = rec.picks[0].size
    assert size.width == "extra-wide"  # the scan alone says wide (right foot, E)
    assert "Width raised to extra-wide from your feedback." in size.basis
    assert rec.picks[0].offers  # Plush is sold in extra-wide
