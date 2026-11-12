"""Run the evals (CLAUDE_CODE_PROMPT.md Phase 12).

    uv run python -m evals.run_evals            # LangSmith experiment
    uv run python -m evals.run_evals --local    # no LangSmith: score locally, print table
    uv run python -m evals.run_evals --parser   # scan-parser accuracy on data/sample_scans

Options: --dataset PATH (default evals/datasets/expert_picks.json), --limit N.
Recommendations come from the ranker, so these make no LLM calls (the parser evals do).
"""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import configure_langsmith
from app.db.models import Offer
from app.ranking.config import default_config
from app.recommend import FALLBACK_LINES, recommend_for, sentence
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, Preferences
from evals.scoring import grounding, hit_rate, link_validity, parser_accuracy, size_accuracy

DEFAULT_DATASET = Path("evals/datasets/expert_picks.json")
SAMPLE_SCANS = Path("data/sample_scans")
EXPECTED_FILE = "expected_profile.json"
RESULTS_FILE = Path("evals/results.md")
README = Path("README.md")
TABLE_START, TABLE_END = "<!-- eval-results:start -->", "<!-- eval-results:end -->"
REC_KEYS = ("hit_rate", "size_accuracy", "link_validity", "grounding")


def load_cases(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        sys.exit(f"{path} not found: copy evals/datasets/expert_picks.template.json and fill it in")
    cases = json.loads(path.read_text())
    templates = [c["name"] for c in cases if c["name"].startswith("TEMPLATE")]
    if templates:
        sys.exit(f"{path} still has template entries: {templates}")
    return cases[:limit] if limit else cases


def run_case(session: Session, case: dict) -> dict:
    """The Recommendation for one case as JSON, plus each pick's sub-score notes."""
    rec, ranking = recommend_for(
        session,
        FootProfile.model_validate(case["foot_profile"]),
        Preferences.model_validate(case.get("preferences") or {}),
        [HistoryEntry.model_validate(h) for h in case.get("history", [])],
    )
    notes = {
        c.shoe_id: sorted({sentence(s.note) for s in c.subscores.values()}) for c in ranking.top
    }
    return {"recommendation": rec.model_dump(mode="json"), "notes": notes}


def score_case(out: dict, expert_picks: list[dict], known_urls: set[str]) -> list[dict]:
    rec = out["recommendation"]
    notes = {int(k): set(v) for k, v in out["notes"].items()}
    return [
        hit_rate(rec, expert_picks),
        size_accuracy(rec, expert_picks),
        link_validity(rec, known_urls),
        grounding(rec, notes, {line.lower() for line in FALLBACK_LINES}),
    ]


def summarize(scores: list[list[dict]]) -> dict[str, float | None]:
    summary = {}
    for key in REC_KEYS:
        values = [s["score"] for case in scores for s in case if s["key"] == key]
        values = [v for v in values if v is not None]
        summary[key] = statistics.mean(values) if values else None
    return summary


def run_local(session: Session, cases: list[dict]) -> dict[str, float | None]:
    known_urls = set(session.scalars(select(Offer.affiliate_url)))
    all_scores = []
    for case in cases:
        scores = score_case(run_case(session, case), case["expert_picks"], known_urls)
        all_scores.append(scores)
        line = "  ".join(f"{s['key']}={_fmt(s['score'])}" for s in scores)
        print(f"  {case['name']}: {line}")
    return summarize(all_scores)


def run_langsmith(session: Session, cases: list[dict]) -> dict:
    from langsmith import Client, evaluate

    client = Client()
    content = json.dumps(cases, sort_keys=True).encode()
    dataset_name = f"lastfit-expert-picks-{hashlib.sha256(content).hexdigest()[:8]}"
    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(dataset_name, description="Profiles + expert shoe picks")
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": {k: c.get(k) for k in ("foot_profile", "preferences", "history")},
                    "outputs": {"expert_picks": c["expert_picks"]},
                    "metadata": {"name": c["name"]},
                }
                for c in cases
            ],
        )
    known_urls = set(session.scalars(select(Offer.affiliate_url)))
    by_key = {}

    def evaluator(key):
        def run(outputs: dict, reference_outputs: dict) -> dict:
            scores = score_case(outputs, reference_outputs["expert_picks"], known_urls)
            return next(s for s in scores if s["key"] == key)

        run.__name__ = key
        return run

    results = evaluate(
        lambda inputs: run_case(session, inputs),
        data=dataset_name,
        evaluators=[evaluator(k) for k in REC_KEYS],
        experiment_prefix=f"ranker-{default_config().version}",
        metadata={"ranker_version": default_config().version},
        max_concurrency=1,
    )
    scores = [
        [{"key": r.key, "score": r.score} for r in row["evaluation_results"]["results"]]
        for row in results
    ]
    by_key.update(summarize(scores))
    return by_key


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def results_table(summary: dict, n_cases: int) -> str:
    return "\n".join(
        [
            f"Ranker `{default_config().version}`, {n_cases} profiles.",
            "",
            "| Hit@3 | Size within ½ | Link validity | Grounding |",
            "| --- | --- | --- | --- |",
            "| " + " | ".join(_fmt(summary[k]) for k in REC_KEYS) + " |",
        ]
    )


def save_table(table: str, readme: Path = README, results: Path = RESULTS_FILE) -> None:
    results.write_text(table + "\n")
    text = readme.read_text()
    if TABLE_START in text and TABLE_END in text:
        before, rest = text.split(TABLE_START, 1)
        after = rest.split(TABLE_END, 1)[1]
        readme.write_text(f"{before}{TABLE_START}\n{table}\n{TABLE_END}{after}")


def run_parser_evals(scan_dirs: list[Path]) -> float | None:
    from app.parsing.scan_parser import parse_scan

    suffixes = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
    scores = []
    for scan_dir in scan_dirs:
        files = sorted(p for p in scan_dir.iterdir() if p.suffix.lower() in suffixes)
        expected = json.loads((scan_dir / EXPECTED_FILE).read_text())
        result = parser_accuracy(expected, parse_scan(files).model_dump())
        scores.append(result["score"])
        print(f"  {scan_dir.name}: {result['score']:.2f} ({result['comment']})")
    return statistics.mean(scores) if scores else None


def main(argv: list[str] | None = None) -> None:
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--local", action="store_true", help="score locally, skip LangSmith")
    parser.add_argument("--parser", action="store_true", help="scan-parser accuracy only")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.parser:
        scan_dirs = sorted(d for d in SAMPLE_SCANS.iterdir() if (d / EXPECTED_FILE).exists())
        if not scan_dirs:
            sys.exit(f"no hand-checked samples in {SAMPLE_SCANS} (see its README)")
        print(f"parser accuracy: {_fmt(run_parser_evals(scan_dirs[: args.limit]))}")
        return

    if not args.local and not configure_langsmith():
        sys.exit(
            "LangSmith is off: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY, or use --local"
        )
    cases = load_cases(args.dataset, args.limit)
    with SessionLocal() as session:
        summary = run_local(session, cases) if args.local else run_langsmith(session, cases)
    table = results_table(summary, len(cases))
    print("\n" + table)
    save_table(table)
    print(f"\nSaved to {RESULTS_FILE} and the README.")


if __name__ == "__main__":
    main()
