"""Recommendation output.

The agent returns `AgentRecommendation`, which has no URL, size or offer fields: it only
chooses shoes and explains why. `app.agent.recommender.finalize` turns that into the
`Recommendation` users see, adding sizes and buy links from the database (Guardrail 1).
"""

from pydantic import BaseModel, Field

AFFILIATE_DISCLOSURE = (
    "Some links are affiliate links: we may earn a commission if you buy through them, "
    "at no extra cost to you. It does not affect which shoes we recommend."
)


class AgentPick(BaseModel):
    shoe_id: int
    why_it_fits: list[str] = Field(
        description="Reasons this shoe fits the runner's scan and preferences, each citing "
        "fit notes by id like [note 12]"
    )
    cited_fit_note_ids: list[int] = Field(description="Ids of the fit notes cited above")
    watch_for: list[str] = Field(description="Fit caveats to check when trying the shoe on")


class AgentRecommendation(BaseModel):
    picks: list[AgentPick] = Field(description="Exactly 3 picks, best first")
    summary: str = Field(description="One or two sentences on what the runner's foot needs")


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


class Pick(BaseModel):
    rank: int
    shoe_id: int
    brand: str
    model: str
    version: str
    why_it_fits: list[str]
    cited_fit_note_ids: list[int]
    watch_for: list[str]
    size: SizeAdvice
    offers: list[OfferLink] = Field(max_length=3)


class Recommendation(BaseModel):
    picks: list[Pick]
    summary: str
    disclosure: str | None = Field(description="Affiliate disclosure; set whenever offers exist")
    flags: list[str] = Field(
        default=[], description="Problems found in post-processing, e.g. a removed link"
    )
