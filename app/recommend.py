"""Turn a runner's stored inputs into a `Recommendation`.

    confirmed profile + preferences + history/feedback (DB)
      -> ranking pipeline (top 3, contributions, sizes)
      -> offers for each exact pair -> link guard + disclosure
      -> reasons written from the ranker's own sub-score notes

Reasons are built straight from the sub-scores, so each one maps to a contribution
(Guardrail 3). The LLM explainer (CLAUDE_CODE_PROMPT.md Phase 5) will rephrase these and add
fit-note evidence; it will not change which shoes are picked.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback, Scan, Shoe, ShoeHistory
from app.db.models import Preferences as PreferencesRow
from app.ranking.config import ScoringConfig
from app.ranking.pipeline import Catalog, RankedShoe, RankResult, rank
from app.retrieval.offers import get_offers, validate_links
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, Preferences
from app.schemas.recommendation import FitFactor, Pick, Recommendation

STRONG = 0.6  # sub-scores above this are reasons; at or below, caveats
FLAT_NOTES = {"no special heel need"}  # same for every shoe, so not a reason for this one
# Fixed lines used when no sub-score gives a reason or caveat (still facts about the pick).
LIMITED_DATA = "Ranked on limited data: most of its fit specs aren't verified yet"
OVER_BUDGET = "A little over your budget"
WIDTH_UNKNOWN = "We haven't verified whether it comes in wide"
UNVERIFIED = "Most of this shoe's fit specs aren't verified yet, so try it on before buying"
NO_CHART = "No size chart for this brand yet, so try it on before buying"
FALLBACK_LINES = (LIMITED_DATA, OVER_BUDGET, WIDTH_UNKNOWN, UNVERIFIED, NO_CHART)


class MissingProfile(ValueError):
    pass


def confirmed_profile(session: Session, user_id: uuid.UUID) -> FootProfile | None:
    scan = session.scalars(
        select(Scan)
        .where(Scan.user_id == user_id, Scan.confirmed_profile.is_not(None))
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .limit(1)
    ).first()
    return FootProfile.model_validate(scan.confirmed_profile) if scan else None


def preferences(session: Session, user_id: uuid.UUID) -> Preferences:
    row = session.get(PreferencesRow, user_id)
    if row is None:
        return Preferences()
    return Preferences(
        weekly_km=None if row.weekly_km is None else float(row.weekly_km),
        goals=row.goals,
        surface=row.surface,
        feel=row.feel,
        budget_usd=None if row.budget_usd is None else float(row.budget_usd),
    )


def history(session: Session, user_id: uuid.UUID) -> list[HistoryEntry]:
    """Shoe history plus feedback on past picks: both feed the ranker the same way."""
    entries = [
        HistoryEntry(
            shoe_id=h.shoe_id,
            raw_name=h.raw_name,
            us_size=None if h.us_size is None else float(h.us_size),
            width=h.width,
            rating=h.rating,
            issues=h.issues,
        )
        for h in session.scalars(select(ShoeHistory).where(ShoeHistory.user_id == user_id))
    ]
    rows = session.execute(
        select(Feedback, Shoe)
        .join(Shoe, Shoe.id == Feedback.shoe_id)
        .where(Feedback.user_id == user_id)
    )
    for fb, shoe in rows:
        entries.append(
            HistoryEntry(
                shoe_id=fb.shoe_id,
                raw_name=f"{shoe.brand} {shoe.model} {shoe.version}",
                us_size=float(fb.us_size),
                width=fb.width,
                rating=fb.outcome,
                issues=fb.issues,
            )
        )
    return entries


def _normalize(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def resolve_shoe_id(session: Session, name: str) -> int | None:
    """Match a runner-written name ("Novablast 5", "Brooks Ghost 17") to a catalog shoe."""
    normalized = _normalize(name)
    for shoe in sorted(session.scalars(select(Shoe)), key=lambda s: -len(s.model)):
        if _normalize(f"{shoe.model} {shoe.version}") in normalized:
            return shoe.id
    return None


def sentence(note: str) -> str:
    return note[:1].upper() + note[1:]


def explain(pick: RankedShoe, verified_fraction: float) -> tuple[list[str], list[str]]:
    """Up to 3 reasons and 1 caveat, each the note of an actual sub-score or flag."""
    scored = [
        (name, sub)
        for name, sub in pick.subscores.items()
        if sub.status == "ok" and sub.note not in FLAT_NOTES
    ]
    strong = sorted(
        (x for x in scored if x[1].value > STRONG),
        key=lambda x: -pick.contributions.get(x[0], 0.0),
    )
    why = [sentence(sub.note) for _, sub in strong[:3]]
    if not why:
        why = [LIMITED_DATA]

    weak = sorted((x for x in scored if x[1].value <= STRONG), key=lambda x: x[1].value)
    if weak:
        watch = sentence(weak[0][1].note)
    elif "over_budget" in pick.flags:
        watch = OVER_BUDGET
    elif "width_unknown" in pick.flags:
        watch = WIDTH_UNKNOWN
    elif verified_fraction < 0.5:
        watch = UNVERIFIED
    elif not pick.size.confident:
        watch = NO_CHART
    else:
        watch = None
    return why, [watch] if watch else []


def breakdown(pick: RankedShoe) -> list[FitFactor]:
    """The sub-scores that apply to this runner, heaviest weight first."""
    factors = [
        FitFactor(factor=name, score=sub.value, weight=sub.weight, note=sentence(sub.note))
        for name, sub in pick.subscores.items()
        if sub.status != "na"
    ]
    return sorted(factors, key=lambda f: -f.weight)


def build_recommendation(
    session: Session, user_id: uuid.UUID, cfg: ScoringConfig | None = None
) -> tuple[Recommendation, RankResult]:
    """Recommendation from everything stored for this runner."""
    profile = confirmed_profile(session, user_id)
    if profile is None:
        raise MissingProfile("user has no confirmed foot profile")
    return recommend_for(
        session, profile, preferences(session, user_id), history(session, user_id), cfg
    )


def recommend_for(
    session: Session,
    profile: FootProfile,
    prefs: Preferences,
    past: list[HistoryEntry],
    cfg: ScoringConfig | None = None,
) -> tuple[Recommendation, RankResult]:
    catalog = Catalog.from_db(session)
    result = rank(profile, prefs, past, catalog, cfg)
    shoes = {s.id: s for s in catalog.shoes}

    picks = []
    for ranked in result.top:
        shoe = shoes[ranked.shoe_id]
        why, watch = explain(ranked, shoe.verified_fraction)
        picks.append(
            Pick(
                rank=ranked.rank,
                shoe_id=shoe.id,
                brand=shoe.brand,
                model=shoe.model,
                version=shoe.version,
                fit_score=ranked.fit_score,
                contributions=ranked.contributions,
                breakdown=breakdown(ranked),
                why_it_fits=why,
                watch_for=watch,
                size=ranked.size,
                offers=get_offers(session, shoe.id, ranked.size.us_size, ranked.size.width),
            )
        )
    rec = Recommendation(
        ranker_version=result.ranker_version,
        picks=picks,
        summary=f"Ranked for your {result.foot}.",
        disclosure=None,
        flags=list(result.warnings),
    )
    return validate_links(session, rec), result
