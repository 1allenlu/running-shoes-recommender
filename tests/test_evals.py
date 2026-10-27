import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import User
from evals.run_evals import (
    TABLE_END,
    TABLE_START,
    comparison_table,
    load_cases,
    run_local,
    save_table,
)
from evals.scoring import hit_rate, link_validity, parser_accuracy, size_accuracy
from tests.agent_script import agent_pick, scripted_agent

TEMPLATE_PROFILE = json.loads(Path("data/sample_scans/expected.template.json").read_text())


def pick(model, version, size, urls=()):
    return {
        "brand": "Acme",
        "model": model,
        "version": version,
        "size": {"us_size": size, "width": "wide"},
        "offers": [{"url": u} for u in urls],
    }


REC = {"picks": [pick("Roomy", "1", 9.0, ["https://x/1"]), pick("Plush", "3", 9.0)]}


def test_hit_rate_matches_model_and_version():
    assert hit_rate(REC, [{"shoe": "Roomy 1", "us_size": 9}])["score"] == 1.0
    assert hit_rate(REC, [{"shoe": "Acme Roomy 2", "us_size": 9}])["score"] == 0.0


def test_size_accuracy_half_size_tolerance():
    experts = [{"shoe": "Acme Roomy 1", "us_size": 8.5}, {"shoe": "Plush 3", "us_size": 10.0}]
    result = size_accuracy(REC, experts)
    assert result["score"] == 0.5  # Roomy within 0.5, Plush a full size off
    assert size_accuracy(REC, [{"shoe": "Other 9", "us_size": 9}])["score"] is None


def test_link_validity():
    assert link_validity(REC, {"https://x/1"})["score"] == 1.0
    assert link_validity(REC, set())["score"] == 0.0
    assert link_validity({"picks": []}, set())["comment"] == "no links"


def test_parser_accuracy_counts_fields():
    assert parser_accuracy(TEMPLATE_PROFILE, TEMPLATE_PROFILE)["score"] == 1.0
    off = json.loads(json.dumps(TEMPLATE_PROFILE))
    off["left"]["us_size"] = 8.0
    off["right"]["heel_width"]["position"] = 0.9  # 0.28 off
    result = parser_accuracy(TEMPLATE_PROFILE, off)
    assert result["score"] == pytest.approx(1 - 2 / 15)
    assert result["comment"] == "wrong: left.us_size, right.heel_width"


def test_template_dataset_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="template entries"):
        load_cases(Path("evals/datasets/expert_picks.template.json"))


def test_comparison_table_saved_between_readme_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n{TABLE_START}\nold\n{TABLE_END}\nafter\n")
    summary = {"hit_rate": 1.0, "size_accuracy": None, "link_validity": 1.0}
    table = comparison_table({"chroma": summary, "pgvector": summary}, 2)
    save_table(table, readme=readme, results=tmp_path / "results.md")
    text = readme.read_text()
    assert "old" not in text and "| pgvector | 1.00 | n/a | 1.00 |" in text
    assert text.endswith(f"{TABLE_END}\nafter\n")


@pytest.mark.db
def test_run_local_end_to_end(indexed, db_session, store):
    case = {
        "name": "wide-forefoot",
        "foot_profile": TEMPLATE_PROFILE,
        "questionnaire": {},
        "expert_picks": [{"shoe": "Acme Roomy 1", "us_size": 9.0, "width": "wide"}],
    }

    def model_factory(_case):
        return scripted_agent(
            lambda _: {
                "summary": "s",
                "picks": [agent_pick(indexed[m]) for m in ("Roomy", "Plush", "Daily")],
            }
        )

    summary = run_local(db_session, store, [case, case], model_factory)
    assert summary == {"hit_rate": 1.0, "size_accuracy": 1.0, "link_validity": 1.0}
    assert db_session.scalar(select(func.count()).select_from(User)) == 0  # users cleaned up
