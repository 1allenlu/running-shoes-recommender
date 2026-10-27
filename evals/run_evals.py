"""Run the Phase 9 evals.

    uv run python -m evals.run_evals                   # LangSmith experiment on VECTOR_BACKEND
    uv run python -m evals.run_evals --backend both    # chroma vs pgvector + comparison table
    uv run python -m evals.run_evals --local           # no LangSmith: score locally, print table
    uv run python -m evals.run_evals --parser          # scan-parser accuracy on data/sample_scans

Options: --dataset PATH (default evals/datasets/expert_picks.json), --limit N.
Each recommendation makes ~10-20 model calls; use --limit on free tiers.
"""

import argparse
import hashlib
import json
import statistics
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.recommender import run_recommendation
from app.config import configure_langsmith, get_settings
from app.db.models import Offer, User
from app.llm import model_name
from evals.scoring import hit_rate, link_validity, parser_accuracy, size_accuracy

DEFAULT_DATASET = Path("evals/datasets/expert_picks.json")
SAMPLE_SCANS = Path("data/sample_scans")
RESULTS_FILE = Path("evals/results.md")
README = Path("README.md")
TABLE_START, TABLE_END = "<!-- eval-results:start -->", "<!-- eval-results:end -->"
REC_KEYS = ("hit_rate", "size_accuracy", "link_validity")


def load_cases(path: Path, limit: int | None = None) -> list[dict]:
    if not path.exists():
        sys.exit(f"{path} not found: copy evals/datasets/expert_picks.template.json and fill it in")
    cases = json.loads(path.read_text())
    templates = [c["name"] for c in cases if c["name"].startswith("TEMPLATE")]
    if templates:
        sys.exit(f"{path} still has template entries: {templates}")
    return cases[:limit] if limit else cases


def run_case(session: Session, store, case: dict, model=None, constraint_chain=None) -> dict:
    """Recommend for a throwaway user built from the case; returns the Recommendation as JSON."""
    user = User(foot_profile=case["foot_profile"], questionnaire=case["questionnaire"])
    session.add(user)
    session.commit()
    try:
        rec = run_recommendation(session, user.id, store, model, constraint_chain)
        return rec.model_dump(mode="json")
    finally:
        session.delete(user)
        session.commit()


def score_case(rec: dict, expert_picks: list[dict], known_urls: set[str]) -> list[dict]:
    return [
        hit_rate(rec, expert_picks),
        size_accuracy(rec, expert_picks),
        link_validity(rec, known_urls),
    ]


def summarize(scores: list[list[dict]]) -> dict[str, float | None]:
    summary = {}
    for key in REC_KEYS:
        values = [s["score"] for case in scores for s in case if s["key"] == key]
        values = [v for v in values if v is not None]
        summary[key] = statistics.mean(values) if values else None
    return summary


def prepare_backend(session: Session, backend: str):
    """Point the app at a vector backend and (re)build its fit-note index."""
    from app.ingest.embed_fit_notes import embed_fit_notes
    from app.retrieval.store import get_store

    get_settings().vector_backend = backend
    store = get_store()
    embed_fit_notes(session, store)
    return store


def run_local(
    session: Session,
    store,
    cases: list[dict],
    model_factory: Callable | None = None,
    constraint_chain=None,
) -> dict[str, float | None]:
    known_urls = set(session.scalars(select(Offer.affiliate_url)))
    all_scores = []
    for case in cases:
        model = model_factory(case) if model_factory else None
        rec = run_case(session, store, case, model, constraint_chain)
        scores = score_case(rec, case["expert_picks"], known_urls)
        all_scores.append(scores)
        line = "  ".join(f"{s['key']}={_fmt(s['score'])}" for s in scores)
        print(f"  {case['name']}: {line}")
    return summarize(all_scores)


def run_langsmith(session: Session, store, cases: list[dict], backend: str) -> dict:
    from langsmith import Client, evaluate

    client = Client()
    content = json.dumps(cases, sort_keys=True).encode()
    dataset_name = f"shoe-rec-expert-picks-{hashlib.sha256(content).hexdigest()[:8]}"
    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(dataset_name, description="Profiles + expert shoe picks")
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": {
                        "foot_profile": c["foot_profile"],
                        "questionnaire": c["questionnaire"],
                    },
                    "outputs": {"expert_picks": c["expert_picks"]},
                    "metadata": {"name": c["name"]},
                }
                for c in cases
            ],
        )
    known_urls = set(session.scalars(select(Offer.affiliate_url)))

    def target(inputs: dict) -> dict:
        return {"recommendation": run_case(session, store, inputs)}

    def hit(outputs: dict, reference_outputs: dict) -> dict:
        return hit_rate(outputs["recommendation"], reference_outputs["expert_picks"])

    def size(outputs: dict, reference_outputs: dict) -> dict:
        return size_accuracy(outputs["recommendation"], reference_outputs["expert_picks"])

    def links(outputs: dict) -> dict:
        return link_validity(outputs["recommendation"], known_urls)

    results = evaluate(
        target,
        data=dataset_name,
        evaluators=[hit, size, links],
        experiment_prefix=f"{backend}-{model_name()}",
        metadata={"vector_backend": backend, "llm_provider": get_settings().llm_provider,
                  "llm_model": model_name()},
        max_concurrency=1,
    )  # fmt: skip
    scores = [
        [{"key": r.key, "score": r.score} for r in row["evaluation_results"]["results"]]
        for row in results
    ]
    return summarize(scores)


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def comparison_table(by_backend: dict[str, dict], n_cases: int) -> str:
    settings = get_settings()
    lines = [
        f"Model: `{settings.llm_provider}` / `{model_name()}`, {n_cases} profiles.",
        "",
        "| Backend | Hit rate | Size accuracy | Link validity |",
        "| --- | --- | --- | --- |",
    ]
    for backend, s in by_backend.items():
        lines.append(
            f"| {backend} | {_fmt(s['hit_rate'])} | {_fmt(s['size_accuracy'])} "
            f"| {_fmt(s['link_validity'])} |"
        )
    return "\n".join(lines)


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
        expected = json.loads((scan_dir / "expected.json").read_text())
        result = parser_accuracy(expected, parse_scan(files).model_dump())
        scores.append(result["score"])
        print(f"  {scan_dir.name}: {result['score']:.2f} ({result['comment']})")
    return statistics.mean(scores) if scores else None


def main(argv: list[str] | None = None) -> None:
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--backend", choices=["chroma", "pgvector", "both"])
    parser.add_argument("--local", action="store_true", help="score locally, skip LangSmith")
    parser.add_argument("--parser", action="store_true", help="scan-parser accuracy only")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.parser:
        scan_dirs = sorted(d for d in SAMPLE_SCANS.iterdir() if (d / "expected.json").exists())
        if not scan_dirs:
            sys.exit(f"no hand-checked samples in {SAMPLE_SCANS} (see its README)")
        print(f"parser accuracy: {_fmt(run_parser_evals(scan_dirs[: args.limit]))}")
        return

    if not args.local and not configure_langsmith():
        sys.exit(
            "LangSmith is off: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY, or use --local"
        )
    cases = load_cases(args.dataset, args.limit)
    backend = args.backend or get_settings().vector_backend
    backends = ["chroma", "pgvector"] if backend == "both" else [backend]

    by_backend = {}
    with SessionLocal() as session:
        for name in backends:
            print(f"{name}:")
            store = prepare_backend(session, name)
            if args.local:
                by_backend[name] = run_local(session, store, cases)
            else:
                by_backend[name] = run_langsmith(session, store, cases, name)

    table = comparison_table(by_backend, len(cases))
    print("\n" + table)
    if len(backends) > 1:
        save_table(table)
        print(f"\nSaved to {RESULTS_FILE} and the README.")


if __name__ == "__main__":
    main()
