"""Stage 1: a transparent, content-based fit scorer (CLAUDE_CODE_PROMPT.md section 5).

Each sub-score is in [0, 1] and comes with a short note saying what drove it. A sub-score is
`n/a` when it doesn't apply to this runner (no budget, no history, not the wide + low-instep
case); `n/a` sub-scores are left out of the score for every shoe, so they never change the
order. A sub-score is `unknown` when the shoe spec it needs is still null; it then counts as
`unknown_score` and the explainer must not claim anything about it.

score = sum(weight x sub-score) / sum(weights that apply), so it stays in [0, 1].
`contributions` holds each weight x sub-score; the explainer and fit meter read from it.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from app.ranking.config import ScoringConfig
from app.ranking.features import FootFeatures, ShoeSpec, article, shoe_vector
from app.schemas.preferences import HistoryEntry, Preferences

Status = Literal["ok", "unknown", "n/a"]


@dataclass(frozen=True)
class SubScore:
    value: float | None
    status: Status
    note: str

    @classmethod
    def ok(cls, value: float, note: str) -> "SubScore":
        return cls(min(max(value, 0.0), 1.0), "ok", note)

    @classmethod
    def unknown(cls, note: str) -> "SubScore":
        return cls(None, "unknown", note)

    @classmethod
    def na(cls, note: str) -> "SubScore":
        return cls(None, "n/a", note)


@dataclass
class HistoryContext:
    """Per-runner history, prepared once and shared across every candidate."""

    loved: list[dict[str, float]] = field(default_factory=list)
    hated: list[dict[str, float]] = field(default_factory=list)
    issue_counts: Counter = field(default_factory=Counter)

    @classmethod
    def build(
        cls, history: list[HistoryEntry], shoes_by_id: dict[int, ShoeSpec]
    ) -> "HistoryContext":
        ctx = cls()
        for entry in history:
            ctx.issue_counts.update(set(entry.issues))
            shoe = shoes_by_id.get(entry.shoe_id) if entry.shoe_id is not None else None
            if shoe is None:
                continue
            if entry.rating == "loved":
                ctx.loved.append(shoe_vector(shoe))
            elif entry.rating == "hated":
                ctx.hated.append(shoe_vector(shoe))
        return ctx


def effective_weights(cfg: ScoringConfig, ctx: HistoryContext) -> dict[str, float]:
    """Base weights, raised once for each issue tag the runner has reported."""
    weights = dict(cfg.weights)
    for issue in ctx.issue_counts:
        for name, factor in cfg.issue_weight_boosts.get(issue, {}).items():
            weights[name] = weights.get(name, 0.0) * factor
    return weights


# --- Sub-scores ---------------------------------------------------------------------------


def width_fit(foot: FootFeatures, shoe: ShoeSpec, cfg: ScoringConfig) -> SubScore:
    w = cfg.width
    target = w.target_toebox_mm[foot.width_letter]
    if shoe.toebox_width_mm is not None:
        width = shoe.toebox_width_mm
        version = ""
        if foot.wide_forefoot and shoe.offers_wide:
            width += w.wide_version_extra_mm
            version = " (wide version)"
        gap = width - target
        # Too narrow is penalized harder than too wide (smaller tolerance).
        tolerance = w.narrow_tolerance_mm if gap < 0 else w.wide_tolerance_mm
        value = 1 - abs(gap) / tolerance
        side = "wider" if gap >= 0 else "narrower"
        return SubScore.ok(
            value,
            f"toe box ~{width:.0f} mm{version}, {abs(gap):.0f} mm {side} than the "
            f"~{target:.0f} mm target for {foot.width_letter} width",
        )

    table = w.toe_box_scores["wide_foot" if foot.wide_forefoot else "standard_foot"]
    if shoe.toe_box is not None:
        value = table[shoe.toe_box]
        note = f"{shoe.toe_box} toe box for {article(foot.width_letter)}-width forefoot"
        if foot.wide_forefoot and shoe.offers_wide and w.wide_version_score > value:
            value, note = w.wide_version_score, f"{note}, offered in wide"
        return SubScore.ok(value, note)

    if foot.wide_forefoot and shoe.offers_wide is not None:
        if shoe.offers_wide:
            return SubScore.ok(w.wide_version_score, "offered in wide; toe box size not verified")
        return SubScore.ok(w.no_wide_version_score, "not offered in wide")
    return SubScore.unknown("toe box width not verified yet")


def volume_fit(foot: FootFeatures, shoe: ShoeSpec, cfg: ScoringConfig) -> SubScore:
    if shoe.upper_volume is None:
        return SubScore.unknown("upper volume not verified yet")
    table = getattr(cfg.volume, foot.instep_band)
    value = table[shoe.upper_volume]
    note = f"{shoe.upper_volume}-volume upper for {article(foot.instep_band)} instep"
    if foot.instep_band == "low" and shoe.heel_lock:
        value += cfg.volume.heel_lock_bonus_low_instep
        note += ", heel lock eyelet to snug it down"
    return SubScore.ok(value, note)


def _heel_needs_hold(foot: FootFeatures) -> bool:
    return foot.wide_forefoot and foot.heel_band in ("narrow", "medium")


def heel_fit(foot: FootFeatures, shoe: ShoeSpec, cfg: ScoringConfig) -> SubScore:
    if not _heel_needs_hold(foot):
        return SubScore.ok(cfg.heel.no_special_need, "no special heel need")
    parts = []
    if shoe.heel_counter is not None:
        parts.append(
            (cfg.heel.counter_scores[shoe.heel_counter], f"{shoe.heel_counter} heel counter")
        )
    if shoe.heel_lock is not None:
        parts.append(
            (
                cfg.heel.lock_scores[shoe.heel_lock],
                "heel lock eyelet" if shoe.heel_lock else "no heel lock eyelet",
            )
        )
    if not parts:
        return SubScore.unknown("heel counter and heel lock not verified yet")
    value = sum(v for v, _ in parts) / len(parts)
    reason = " and ".join(n for _, n in parts)
    return SubScore.ok(value, f"{reason} to hold a {foot.heel_band} heel under a wide forefoot")


def combo_applies(foot: FootFeatures) -> bool:
    return foot.wide_forefoot and foot.instep_band == "low"


def combo_fit(foot: FootFeatures, shoe: ShoeSpec, width: SubScore, cfg: ScoringConfig) -> SubScore:
    """Wide forefoot + low instep: room up front, but a low-volume upper and a locked heel."""
    if not combo_applies(foot):
        return SubScore.na("not a wide forefoot with a low instep")
    if shoe.upper_volume == "high":
        return SubScore.ok(0.0, "high-volume upper: too much room over a low instep")

    checks, notes = [], []
    if width.status == "ok":
        roomy = width.value >= cfg.combo.roomy_width_fit
        checks.append(1.0 if roomy else 0.0)
        notes.append("enough toe room" if roomy else "toe box not roomy enough")
    if shoe.upper_volume is not None:
        checks.append(1.0)
        notes.append(f"{shoe.upper_volume}-volume upper")
    if shoe.heel_lock is not None:
        checks.append(1.0 if shoe.heel_lock else 0.0)
        notes.append("heel lock eyelet" if shoe.heel_lock else "no heel lock eyelet")
    if not checks:
        return SubScore.unknown("toe box, upper volume and heel lock not verified yet")

    value = sum(checks) / len(checks)
    # A wide version that is only roomy because the whole shoe is bigger adds volume everywhere.
    only_via_wide = shoe.offers_wide and shoe.toe_box != "roomy" and shoe.toebox_width_mm is None
    if only_via_wide and shoe.upper_volume != "low":
        value *= cfg.combo.wide_version_penalty
        notes.append("room comes from the wide version, which adds volume everywhere")
    return SubScore.ok(value, "wide forefoot + low instep: " + ", ".join(notes))


def ride_fit(prefs: Preferences, shoe: ShoeSpec, cfg: ScoringConfig) -> SubScore:
    r = cfg.ride
    stack_prefs = {r.stack_by_goal[g] for g in prefs.goals if g in r.stack_by_goal}
    stack_pref = stack_prefs.pop() if len(stack_prefs) == 1 else None
    if prefs.feel is None and stack_pref is None:
        return SubScore.na("no preferred feel or stack")

    parts, unknown = [], []
    if prefs.feel is not None:
        if shoe.midsole_softness is None:
            unknown.append("midsole softness")
        else:
            parts.append(
                (r.feel_scores[prefs.feel][shoe.midsole_softness],
                 f"{shoe.midsole_softness} midsole for a {prefs.feel} feel")
            )  # fmt: skip
    if stack_pref is not None:
        if shoe.stack_heel_mm is None:
            unknown.append("stack height")
        else:
            fits = (
                shoe.stack_heel_mm >= r.high_stack_min_mm
                if stack_pref == "high"
                else shoe.stack_heel_mm <= r.low_stack_max_mm
            )
            parts.append(
                (1.0 if fits else r.stack_mismatch_score,
                 f"{shoe.stack_heel_mm:.0f} mm heel stack for goals that suit a {stack_pref} stack")
            )  # fmt: skip
    if not parts:
        return SubScore.unknown(f"{' and '.join(unknown)} not verified yet")
    return SubScore.ok(sum(v for v, _ in parts) / len(parts), "; ".join(n for _, n in parts))


def _cosine(a: dict[str, float], b: dict[str, float], min_dims: int) -> float | None:
    shared = a.keys() & b.keys()
    if len(shared) < min_dims:
        return None
    dot = sum(a[k] * b[k] for k in shared)
    na = math.sqrt(sum(a[k] ** 2 for k in shared))
    nb = math.sqrt(sum(b[k] ** 2 for k in shared))
    if na == 0 or nb == 0:
        return 1.0 if na == nb else 0.0  # two all-average shoes are alike
    return dot / (na * nb)


def history_fit(shoe: ShoeSpec, ctx: HistoryContext, cfg: ScoringConfig) -> SubScore:
    if not ctx.loved and not ctx.hated:
        return SubScore.na("no rated shoes from our catalog yet")
    vec = shoe_vector(shoe)
    min_dims = cfg.history.min_shared_dims

    def mean_sim(vectors):
        sims = [s for v in vectors if (s := _cosine(vec, v, min_dims)) is not None]
        return sum(sims) / len(sims) if sims else None

    loved, hated = mean_sim(ctx.loved), mean_sim(ctx.hated)
    if loved is None and hated is None:
        return SubScore.unknown("not enough verified specs to compare with your past shoes")
    value = 0.5 + 0.5 * ((loved or 0.0) - (hated or 0.0))
    notes = []
    if loved is not None:
        notes.append(f"similarity {loved:+.2f} to shoes you loved")
    if hated is not None:
        notes.append(f"{hated:+.2f} to shoes you hated")
    return SubScore.ok(value, ", ".join(notes))


def budget_fit(prefs: Preferences, shoe: ShoeSpec, cfg: ScoringConfig) -> SubScore:
    if prefs.budget_usd is None:
        return SubScore.na("no budget set")
    if shoe.price_usd is None:
        return SubScore.unknown("price not verified yet")
    budget, price = prefs.budget_usd, shoe.price_usd
    if price > budget:
        return SubScore.ok(0.0, f"${price:.0f}, over your ${budget:.0f} budget")
    under = (budget - price) / budget
    value = 0.5 + 0.5 * min(under / cfg.budget.full_reward_under_fraction, 1.0)
    return SubScore.ok(value, f"${price:.0f}, ${budget - price:.0f} under your budget")


# --- Total --------------------------------------------------------------------------------


@dataclass
class ScoredShoe:
    shoe: ShoeSpec
    score: float  # 0-1
    contributions: dict[str, float]  # weight x sub-score, for sub-scores that apply
    subscores: dict[str, SubScore]
    weights: dict[str, float]


def score_shoe(
    foot: FootFeatures,
    prefs: Preferences,
    ctx: HistoryContext,
    shoe: ShoeSpec,
    cfg: ScoringConfig,
    weights: dict[str, float] | None = None,
) -> ScoredShoe:
    weights = weights if weights is not None else effective_weights(cfg, ctx)
    width = width_fit(foot, shoe, cfg)
    subscores = {
        "width_fit": width,
        "volume_fit": volume_fit(foot, shoe, cfg),
        "heel_fit": heel_fit(foot, shoe, cfg),
        "combo_fit": combo_fit(foot, shoe, width, cfg),
        "ride_fit": ride_fit(prefs, shoe, cfg),
        "history_fit": history_fit(shoe, ctx, cfg),
        "budget_fit": budget_fit(prefs, shoe, cfg),
    }
    contributions, total_weight = {}, 0.0
    for name, sub in subscores.items():
        weight = weights.get(name, 0.0)
        if sub.status == "n/a" or weight == 0:
            continue
        value = sub.value if sub.status == "ok" else cfg.unknown_score
        contributions[name] = weight * value
        total_weight += weight
    score = sum(contributions.values()) / total_weight if total_weight else 0.0
    return ScoredShoe(shoe, score, contributions, subscores, weights)
