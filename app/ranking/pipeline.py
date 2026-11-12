"""Ranking pipeline: confirmed foot profile + preferences + history -> top 3 with sizes.

    uv run python -m app.ranking.pipeline --profile data/sample_scans/expected_profile.json
    uv run python -m app.ranking.pipeline --profile p.json --prefs prefs.json \
        --history history.json --source db --json

This is the only place shoes are ranked (Guardrail 1). The LLM explains the result; it never
reorders it. Offers and the explanation are added by the caller.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from app.ranking.config import ScoringConfig, default_config, load_config
from app.ranking.features import FootFeatures, ShoeSpec
from app.ranking.filters import apply_filters
from app.ranking.fit_scorer import HistoryContext, ScoredShoe, effective_weights, score_shoe
from app.ranking.sizing import ChartRow, size_to_order
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, Preferences
from app.schemas.recommendation import SizeAdvice

DEFAULT_SEED_DIR = Path("data/seed")


@dataclass
class Catalog:
    shoes: list[ShoeSpec]
    charts: dict[str, list[ChartRow]]

    @classmethod
    def from_seed(cls, seed_dir: Path = DEFAULT_SEED_DIR) -> "Catalog":
        """Straight from the seed files; shoe ids follow row order (1, 2, ...)."""
        from app.ingest.load_catalog import parse_shoes, parse_size_charts

        shoes = [
            ShoeSpec.from_mapping(i, row)
            for i, row in enumerate(parse_shoes(seed_dir / "shoes.csv"), 1)
        ]
        rows, _ = parse_size_charts(seed_dir / "size_charts.csv")
        return cls(shoes, _group_charts(rows))

    @classmethod
    def from_db(cls, session) -> "Catalog":
        from sqlalchemy import select

        from app.db.models import Shoe, SizeChart

        shoes = [
            ShoeSpec.from_mapping(s.id, s) for s in session.scalars(select(Shoe).order_by(Shoe.id))
        ]
        keys = ("brand", "us_size", "length_mm_min", "length_mm_max", "size_offset", "sizing_note")
        rows = [{k: getattr(r, k) for k in keys} for r in session.scalars(select(SizeChart))]
        return cls(shoes, _group_charts(rows))

    def resolve(self, history: list[HistoryEntry]) -> list[HistoryEntry]:
        """Fill in shoe_id where raw_name names a catalog shoe ("Brooks Ghost 17" or "Ghost 17")."""
        names = {}
        for s in self.shoes:
            names[" ".join(s.name.lower().split())] = s.id
            names.setdefault(f"{s.model} {s.version}".lower(), s.id)
        out = []
        for entry in history:
            if entry.shoe_id is None:
                found = names.get(" ".join(entry.raw_name.lower().split()))
                entry = entry.model_copy(update={"shoe_id": found})
            out.append(entry)
        return out


def _group_charts(rows: list[dict]) -> dict[str, list[ChartRow]]:
    charts: dict[str, list[ChartRow]] = {}
    for r in rows:
        charts.setdefault(r["brand"], []).append(
            ChartRow(
                us_size=float(r["us_size"]),
                length_mm_min=float(r["length_mm_min"]),
                length_mm_max=float(r["length_mm_max"]),
                size_offset=float(r.get("size_offset") or 0),
                note=r.get("sizing_note"),
            )
        )
    return charts


class SubScoreOut(BaseModel):
    value: float | None
    status: str
    weight: float
    note: str


class RankedShoe(BaseModel):
    rank: int
    shoe_id: int
    name: str
    brand: str
    score: float  # 0-1
    fit_score: int  # 0-100, what the card shows
    contributions: dict[str, float]
    subscores: dict[str, SubScoreOut]
    flags: list[str]
    unknown_specs: list[str]
    size: SizeAdvice


class ExcludedShoe(BaseModel):
    shoe_id: int
    name: str
    reason: str


class RankResult(BaseModel):
    ranker_version: str
    foot: str
    top: list[RankedShoe]
    candidates: list[RankedShoe]  # every shoe that passed the filters, best first
    excluded: list[ExcludedShoe]
    warnings: list[str]


def _ranked(rank: int, scored: ScoredShoe, flags: list[str], size: SizeAdvice) -> RankedShoe:
    return RankedShoe(
        rank=rank,
        shoe_id=scored.shoe.id,
        name=scored.shoe.name,
        brand=scored.shoe.brand,
        score=round(scored.score, 4),
        fit_score=round(scored.score * 100),
        contributions={k: round(v, 4) for k, v in scored.contributions.items()},
        subscores={
            name: SubScoreOut(
                value=None if sub.value is None else round(sub.value, 3),
                status=sub.status,
                weight=round(scored.weights.get(name, 0.0), 4),
                note=sub.note,
            )
            for name, sub in scored.subscores.items()
        },
        flags=flags,
        unknown_specs=scored.shoe.unknown_specs,
        size=size,
    )


def rank(
    profile: FootProfile,
    prefs: Preferences,
    history: list[HistoryEntry],
    catalog: Catalog,
    cfg: ScoringConfig | None = None,
    top_k: int = 3,
) -> RankResult:
    cfg = cfg or default_config()
    history = catalog.resolve(history)
    foot = FootFeatures.from_profile(profile)
    filtered = apply_filters(catalog.shoes, foot, prefs, history, cfg)
    ctx = HistoryContext.build(history, {s.id: s for s in catalog.shoes})
    weights = effective_weights(cfg, ctx)

    scored = [
        (score_shoe(foot, prefs, ctx, c.shoe, cfg, weights), c.flags) for c in filtered.candidates
    ]
    # Ties (common while specs are TODO) go to the shoe with more verified specs, then by name.
    scored.sort(
        key=lambda pair: (-pair[0].score, -pair[0].shoe.verified_fraction, pair[0].shoe.name)
    )

    ranked = [
        _ranked(i, s, flags, size_to_order(s.shoe.brand, foot, catalog.charts, cfg))
        for i, (s, flags) in enumerate(scored, 1)
    ]
    warnings = list(filtered.warnings)
    if len(ranked) < top_k:
        warnings.append(f"Only {len(ranked)} shoes in our catalog fit your answers.")
    guessed = [s.shoe.name for s, _ in scored[:top_k] if s.shoe.verified_fraction < 0.5]
    if guessed:
        warnings.append(
            f"Low confidence: we haven't verified most fit specs for {', '.join(guessed)} "
            "yet, so try them on before buying."
        )
    return RankResult(
        ranker_version=cfg.version,
        foot=foot.describe(),
        top=ranked[:top_k],
        candidates=ranked,
        excluded=[
            ExcludedShoe(shoe_id=e.shoe.id, name=e.shoe.name, reason=e.reason)
            for e in filtered.excluded
        ],
        warnings=warnings,
    )


# --- CLI ----------------------------------------------------------------------------------


def format_result(result: RankResult) -> str:
    lines = [
        f"{result.ranker_version} · {result.foot}",
        f"{len(result.candidates)} candidates, {len(result.excluded)} excluded",
        "",
    ]
    for pick in result.top:
        size = pick.size
        sure = "" if size.confident else " (not confident)"
        order = f"size {size.us_size:g} {size.width}{sure}"
        lines.append(f"#{pick.rank} {pick.name}  fit {pick.fit_score}/100  {order}")
        for name, sub in pick.subscores.items():
            if sub.status == "n/a":
                continue
            value = "  ?  " if sub.value is None else f"{sub.value:.2f}"
            contrib = pick.contributions.get(name, 0.0)
            lines.append(f"    {name:<12} {sub.weight:.2f} x {value} = {contrib:.3f}  {sub.note}")
        lines.append(f"    size: {size.basis}")
        if pick.flags:
            lines.append(f"    flags: {', '.join(pick.flags)}")
        if pick.unknown_specs:
            some = ", ".join(pick.unknown_specs[:4])
            lines.append(f"    unverified specs: {len(pick.unknown_specs)} ({some}, ...)")
        lines.append("")
    for ex in result.excluded:
        lines.append(f"excluded: {ex.name}: {ex.reason}")
    for warning in result.warnings:
        lines.append(f"warning: {warning}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rank shoes for a confirmed foot profile.")
    parser.add_argument("--profile", type=Path, required=True, help="FootProfile JSON")
    parser.add_argument("--prefs", type=Path, help="Preferences JSON")
    parser.add_argument("--history", type=Path, help="JSON list of shoe history entries")
    parser.add_argument(
        "--source",
        choices=("seed", "db"),
        default="seed",
        help="Catalog source (default: seed files)",
    )
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--config", type=Path, help="Scoring config (default: config/scoring.yaml)")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    args = parser.parse_args(argv)

    profile = FootProfile.model_validate_json(args.profile.read_text())
    prefs = Preferences.model_validate_json(args.prefs.read_text()) if args.prefs else Preferences()
    history = (
        [HistoryEntry.model_validate(h) for h in json.loads(args.history.read_text())]
        if args.history
        else []
    )
    cfg = load_config(args.config) if args.config else default_config()

    if args.source == "db":
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            catalog = Catalog.from_db(session)
    else:
        catalog = Catalog.from_seed(args.seed_dir)

    result = rank(profile, prefs, history, catalog, cfg, top_k=args.top)
    sys.stdout.write(
        result.model_dump_json(indent=2) + "\n" if args.json else format_result(result)
    )


if __name__ == "__main__":
    main()
