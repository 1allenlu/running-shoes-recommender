"""Recommendation output: the ranker's top 3, each with reasons, size and buy links.

Shoes, order, scores and contributions come from `app.ranking` (Guardrail 1). Links come only
from the `offers` table (Guardrail 2). Every reason traces to a sub-score (Guardrail 3).
"""

from pydantic import BaseModel, Field

AFFILIATE_DISCLOSURE = (
    "Some links are affiliate links: we may earn a commission if you buy through them, "
    "at no extra cost to you. It does not affect which shoes we recommend."
)


class SizeAdvice(BaseModel):
    us_size: float
    width: str = Field(description="standard, wide or extra-wide")
    basis: str = Field(description="How the size was chosen")
    sizing_note: str | None = None
    confident: bool = Field(description="False when no size chart backed the choice")


class OfferLink(BaseModel):
    offer_id: int
    retailer: str
    price_usd: float | None
    url: str


class FitFactor(BaseModel):
    factor: str = Field(description="Sub-score name, e.g. width_fit")
    score: float | None = Field(description="0-1 match; null when the shoe's spec isn't verified")
    weight: float = Field(description="Effective weight in the ranker")
    note: str


class Pick(BaseModel):
    rank: int
    shoe_id: int
    brand: str
    model: str
    version: str
    fit_score: int = Field(description="0-100, from the ranker")
    contributions: dict[str, float] = Field(description="weight x sub-score, per feature")
    breakdown: list[FitFactor] = Field(
        default=[], description="Each sub-score that applies, heaviest first (for the fit meter)"
    )
    why_it_fits: list[str]
    watch_for: list[str]
    size: SizeAdvice
    offers: list[OfferLink] = Field(max_length=3)


class Recommendation(BaseModel):
    ranker_version: str
    picks: list[Pick]
    summary: str
    disclosure: str | None = Field(description="Affiliate disclosure; set whenever offers exist")
    flags: list[str] = Field(
        default=[], description="Problems found in post-processing, e.g. a removed link"
    )
