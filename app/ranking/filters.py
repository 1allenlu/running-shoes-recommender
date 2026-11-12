"""Hard filters: shoes that can't be recommended, whatever they score.

Rules from CLAUDE_CODE_PROMPT.md section 5. A spec that is still null never excludes a shoe;
the candidate gets a flag instead, so the explainer can say what's unverified.

The catalog is small (tens of shoes), so filters run in Python over `ShoeSpec`s rather than in
SQL: every exclusion gets a readable reason, and the same code runs from the DB or the seed CSV.
"""

from collections import Counter
from dataclasses import dataclass, field

from app.ranking.config import ScoringConfig
from app.ranking.features import FootFeatures, ShoeSpec, article, width_at_least
from app.schemas.preferences import HistoryEntry, Preferences


@dataclass
class Candidate:
    shoe: ShoeSpec
    flags: list[str] = field(default_factory=list)


@dataclass
class Excluded:
    shoe: ShoeSpec
    reason: str


@dataclass
class FilterResult:
    candidates: list[Candidate]
    excluded: list[Excluded]
    warnings: list[str]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def hated_models(history: list[HistoryEntry], shoes_by_id: dict[int, ShoeSpec]) -> set[str]:
    """Brand + model the runner hated. Every version is excluded: "I hated the Pegasus"."""
    hated = set()
    for entry in history:
        if entry.rating != "hated":
            continue
        shoe = shoes_by_id.get(entry.shoe_id) if entry.shoe_id is not None else None
        if shoe is not None:
            hated.add(_norm(f"{shoe.brand} {shoe.model}"))
    return hated


def recurring_issues(history: list[HistoryEntry]) -> set[str]:
    """Issue tags reported on two or more shoes."""
    counts = Counter(tag for entry in history for tag in set(entry.issues))
    return {tag for tag, n in counts.items() if n >= 2}


def allowed_categories(prefs: Preferences, cfg: ScoringConfig) -> set[str] | None:
    """Categories that suit at least one goal; None means no restriction."""
    mapped = [
        cfg.filters.categories_by_goal[g]
        for g in prefs.goals
        if g in cfg.filters.categories_by_goal
    ]
    return {c for cats in mapped for c in cats} if mapped else None


def apply_filters(
    shoes: list[ShoeSpec],
    foot: FootFeatures,
    prefs: Preferences,
    history: list[HistoryEntry],
    cfg: ScoringConfig,
) -> FilterResult:
    f = cfg.filters
    shoes_by_id = {s.id: s for s in shoes}
    hated = hated_models(history, shoes_by_id)
    issues = recurring_issues(history)
    categories = allowed_categories(prefs, cfg)
    needs_wide = width_at_least(foot.width_letter, f.wide_min_letter)
    warnings = []
    if prefs.surface in ("trail", "mixed"):
        warnings.append("Only road shoes are covered for now; trail picks aren't available yet.")

    candidates, excluded = [], []
    for shoe in shoes:
        reason, flags = None, []

        if _norm(f"{shoe.brand} {shoe.model}") in hated:
            reason = "you rated this model hated"
        if reason is None:
            for issue in sorted(issues):
                for attr, values in f.recurring_issue_excludes.get(issue, {}).items():
                    if getattr(shoe, attr) in values:
                        spec, problem = attr.replace("_", " "), issue.replace("_", " ")
                        value = getattr(shoe, attr)
                        reason = f"{spec} is {value}, and you've had {problem} in 2+ shoes"
                        break
                if reason:
                    break
        if reason is None and categories is not None and shoe.category not in categories:
            reason = f"{shoe.category} shoe doesn't suit your goals"

        if reason is None and prefs.budget_usd is not None:
            limit = prefs.budget_usd * (1 + cfg.budget.over_budget_allowance)
            if shoe.price_usd is None:
                flags.append("price_unknown")
            elif shoe.price_usd > limit:
                reason = f"${shoe.price_usd:.0f} is more than 10% over your budget"
            elif shoe.price_usd > prefs.budget_usd:
                flags.append("over_budget")

        if reason is None and needs_wide:
            roomy = (
                shoe.toebox_width_mm is not None and shoe.toebox_width_mm >= f.wide_toebox_min_mm
            )
            if not (shoe.offers_wide or roomy):
                if shoe.offers_wide is False:
                    reason = f"no wide version for {article(foot.width_letter)}-width foot"
                else:  # widths not verified yet
                    flags.append("width_unknown")

        if reason is None:
            candidates.append(Candidate(shoe, flags))
        else:
            excluded.append(Excluded(shoe, reason))
    return FilterResult(candidates, excluded, warnings)
