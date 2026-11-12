import json
from pathlib import Path

import pytest

from evals.run_evals import (
    TABLE_END,
    TABLE_START,
    load_cases,
    results_table,
    run_local,
    save_table,
)
from evals.scoring import grounding, hit_rate, link_validity, parser_accuracy, size_accuracy

FIXTURE = json.loads(Path("data/sample_scans/expected_profile.json").read_text())


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
    assert parser_accuracy(FIXTURE, FIXTURE)["score"] == 1.0
    off = json.loads(json.dumps(FIXTURE))
    off["left"]["us_size"] = 8.0
    off["right"]["heel_width"]["position"] = 0.9  # 0.28 off
    result = parser_accuracy(FIXTURE, off)
    assert result["score"] == pytest.approx(1 - 2 / 15)
    assert result["comment"] == "wrong: left.us_size, right.heel_width"


def test_template_dataset_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="template entries"):
        load_cases(Path("evals/datasets/expert_picks.template.json"))


def test_grounding_only_accepts_the_picks_own_notes():
    rec = {"picks": [{"shoe_id": 1, "why_it_fits": ["Roomy toe box"], "watch_for": ["Odd claim"]}]}
    result = grounding(rec, {1: {"Roomy toe box"}}, {"fallback line"})
    assert result["score"] == 0.5 and "Odd claim" in result["comment"]


def test_results_table_saved_between_readme_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n{TABLE_START}\nold\n{TABLE_END}\nafter\n")
    summary = {"hit_rate": 1.0, "size_accuracy": None, "link_validity": 1.0, "grounding": 1.0}
    save_table(results_table(summary, 2), readme=readme, results=tmp_path / "results.md")
    text = readme.read_text()
    assert "old" not in text and "| 1.00 | n/a | 1.00 | 1.00 |" in text
    assert text.endswith(f"{TABLE_END}\nafter\n")


@pytest.mark.db
def test_run_local_end_to_end(catalog, db_session):
    case = {
        "name": "wide-forefoot",
        "foot_profile": FIXTURE,
        "preferences": {"feel": "balanced"},
        "history": [{"raw_name": "Acme Narrow 2", "rating": "hated"}],
        "expert_picks": [{"shoe": "Acme Roomy 1", "us_size": 9.5, "width": "wide"}],
    }
    summary = run_local(db_session, [case, case])
    assert summary == {"hit_rate": 1.0, "size_accuracy": 1.0, "link_validity": 1.0,
                       "grounding": 1.0}  # fmt: skip
