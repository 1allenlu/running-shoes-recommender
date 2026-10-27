"""Turn the runner's feedback notes into constraints for the next recommendation.

A small structured-output chain reads notes like "toe box too narrow" together with that
shoe's specs and returns `FeedbackConstraints` (e.g. toe_box must be "roomy"). The agent's
searches are merged with them, and `finalize` drops picks that conflict with known specs.
"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback, Shoe, User
from app.retrieval.hybrid import ShoeFilters

WIDTH_ORDER = ["standard", "wide", "extra-wide"]

CONSTRAINT_SYSTEM = """\
You turn a runner's feedback on shoes they tried into fit constraints for choosing their next \
shoes. Each item gives the shoe's known specs and the runner's note.

- Make relative complaints absolute using the specs: "toe box too narrow" on a shoe whose \
toe_box is "medium" means toe_box must be ["roomy"]; on a "narrow" one, ["medium", "roomy"].
- "Too tight overall" / "too narrow" on a standard-width shoe can mean width "wide".
- "Heel slips" means heel_lock true. "Too much drop" on a 10 mm drop shoe means max_drop_mm \
below 10, and so on.
- Only constrain what the notes actually say. Leave everything else null.
- Put anything that is not one of these fields (e.g. "laces dig in") in `other`, briefly.
- No medical interpretation: describe fit only."""


class FeedbackConstraints(BaseModel):
    toe_box: list[Literal["narrow", "medium", "roomy"]] | None = Field(
        default=None, description="Acceptable toe boxes"
    )
    upper_volume: list[Literal["low", "medium", "high"]] | None = Field(
        default=None, description="Acceptable upper volumes"
    )
    width: Literal["standard", "wide", "extra-wide"] | None = Field(
        default=None, description="Minimum shoe width"
    )
    min_drop_mm: float | None = None
    max_drop_mm: float | None = None
    min_stack_heel_mm: float | None = None
    max_stack_heel_mm: float | None = None
    heel_lock: bool | None = Field(default=None, description="True if the heel must lock in")
    other: list[str] = Field(default=[], description="Fit wishes that are not fields above")

    def violations(self, shoe: Shoe) -> list[str]:
        """Constraints this shoe breaks, judged on known specs only."""
        problems = []
        if self.toe_box and shoe.toe_box and shoe.toe_box not in self.toe_box:
            problems.append(f"toe box is {shoe.toe_box}, need {'/'.join(self.toe_box)}")
        if self.upper_volume and shoe.upper_volume and shoe.upper_volume not in self.upper_volume:
            problems.append(
                f"upper volume is {shoe.upper_volume}, need {'/'.join(self.upper_volume)}"
            )
        if self.width and shoe.widths_available is not None:
            wide_enough = WIDTH_ORDER[WIDTH_ORDER.index(self.width) :]
            if not set(shoe.widths_available) & set(wide_enough):
                problems.append(f"not made in {self.width} or wider")
        if self.heel_lock and shoe.heel_lock is False:
            problems.append("no locked-in heel")
        ranges = (
            ("drop", shoe.drop_mm, self.min_drop_mm, self.max_drop_mm),
            ("heel stack", shoe.stack_heel_mm, self.min_stack_heel_mm, self.max_stack_heel_mm),
        )
        for label, value, low, high in ranges:
            if value is None:
                continue
            value = float(value)
            if low is not None and value < low:
                problems.append(f"{label} {value:g} mm < {low:g} mm")
            if high is not None and value > high:
                problems.append(f"{label} {value:g} mm > {high:g} mm")
        return problems


def merge_filters(filters: ShoeFilters, c: FeedbackConstraints | None) -> ShoeFilters:
    """Tighten the agent's search filters with the feedback constraints."""
    if c is None:
        return filters

    def both(a, b):
        if a and b:
            return [v for v in a if v in b] or b  # disagreement: feedback wins
        return a or b

    def wider(a, b):
        return max(a, b, key=WIDTH_ORDER.index) if a and b else a or b

    def lo(a, b):
        return max(v for v in (a, b) if v is not None) if a is not None or b is not None else None

    def hi(a, b):
        return min(v for v in (a, b) if v is not None) if a is not None or b is not None else None

    return filters.model_copy(
        update={
            "toe_box": both(filters.toe_box, c.toe_box),
            "upper_volume": both(filters.upper_volume, c.upper_volume),
            "width": wider(filters.width, c.width),
            "min_drop_mm": lo(filters.min_drop_mm, c.min_drop_mm),
            "max_drop_mm": hi(filters.max_drop_mm, c.max_drop_mm),
            "min_stack_heel_mm": lo(filters.min_stack_heel_mm, c.min_stack_heel_mm),
            "max_stack_heel_mm": hi(filters.max_stack_heel_mm, c.max_stack_heel_mm),
            "heel_lock": filters.heel_lock or c.heel_lock,
        }
    )


def feedback_with_notes(session: Session, user: User) -> list[dict]:
    rows = session.execute(
        select(Feedback, Shoe)
        .join(Shoe, Feedback.shoe_id == Shoe.id)
        .where(Feedback.user_id == user.id, Feedback.notes.is_not(None), Feedback.notes != "")
        .order_by(Feedback.created_at)
    ).all()
    return [
        {
            "shoe": f"{shoe.brand} {shoe.model} {shoe.version}",
            "rating": fb.rating,
            "size_worn": f"{float(fb.us_size):g} {fb.width}",
            "specs": {
                "toe_box": shoe.toe_box,
                "upper_volume": shoe.upper_volume,
                "widths_available": shoe.widths_available,
                "heel_lock": shoe.heel_lock,
                "drop_mm": None if shoe.drop_mm is None else float(shoe.drop_mm),
                "stack_heel_mm": None if shoe.stack_heel_mm is None else float(shoe.stack_heel_mm),
            },
            "note": fb.notes,
        }
        for fb, shoe in rows
    ]


def build_constraint_chain() -> Runnable:
    from app.llm import get_chat_model

    return get_chat_model().with_structured_output(FeedbackConstraints, method="json_schema")


def derive_constraints(
    session: Session, user: User, chain: Runnable | None = None
) -> FeedbackConstraints | None:
    """One model call over all of the runner's feedback notes; None if there are no notes."""
    items = feedback_with_notes(session, user)
    if not items:
        return None
    chain = chain or build_constraint_chain()
    messages = [
        SystemMessage(CONSTRAINT_SYSTEM),
        HumanMessage(json.dumps(items, indent=2)),
    ]
    return chain.invoke(messages, config={"run_name": "feedback_constraints"})
