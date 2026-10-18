"""Hybrid shoe search: SQL spec filters + fit-note similarity to a "feel" query.

Specs that are still unknown (NULL, i.e. TODO in the seed data) pass the filters rather than
excluding the shoe; each candidate lists its unknown specs so the agent can say so.
"""

from typing import Literal

from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import FitNote, Shoe
from app.retrieval.store import relevance_search

SPEC_FIELDS = (
    "category",
    "drop_mm",
    "stack_heel_mm",
    "stack_forefoot_mm",
    "weight_g",
    "widths_available",
    "toe_box",
    "upper_volume",
    "heel_lock",
    "price_usd",
)


class ShoeFilters(BaseModel):
    width: Literal["standard", "wide", "extra-wide"] | None = Field(
        default=None, description="Width the shoe must come in"
    )
    toe_box: list[Literal["narrow", "medium", "roomy"]] | None = None
    upper_volume: list[Literal["low", "medium", "high"]] | None = None
    categories: list[Literal["daily", "tempo", "race", "stability", "max-cushion"]] | None = None
    max_price_usd: float | None = None
    min_drop_mm: float | None = None
    max_drop_mm: float | None = None
    min_stack_heel_mm: float | None = None
    max_stack_heel_mm: float | None = None
    exclude_shoe_ids: list[int] = []


class ShoeCandidate(BaseModel):
    shoe_id: int
    name: str
    specs: dict
    unknown_specs: list[str]
    score: float = Field(description="Best fit-note similarity to the query, 0-1; 0 if none")
    best_fit_note: str | None


def _known_or(column, condition):
    """Unknown (NULL) specs pass the filter."""
    return or_(column.is_(None), condition)


def apply_filters(stmt: Select, f: ShoeFilters) -> Select:
    conditions = []
    if f.width:
        conditions.append(
            _known_or(Shoe.widths_available, Shoe.widths_available.contains([f.width]))
        )
    if f.toe_box:
        conditions.append(_known_or(Shoe.toe_box, Shoe.toe_box.in_(f.toe_box)))
    if f.upper_volume:
        conditions.append(_known_or(Shoe.upper_volume, Shoe.upper_volume.in_(f.upper_volume)))
    if f.categories:
        conditions.append(Shoe.category.in_(f.categories))
    if f.max_price_usd is not None:
        conditions.append(_known_or(Shoe.price_usd, Shoe.price_usd <= f.max_price_usd))
    if f.min_drop_mm is not None:
        conditions.append(_known_or(Shoe.drop_mm, Shoe.drop_mm >= f.min_drop_mm))
    if f.max_drop_mm is not None:
        conditions.append(_known_or(Shoe.drop_mm, Shoe.drop_mm <= f.max_drop_mm))
    if f.min_stack_heel_mm is not None:
        conditions.append(_known_or(Shoe.stack_heel_mm, Shoe.stack_heel_mm >= f.min_stack_heel_mm))
    if f.max_stack_heel_mm is not None:
        conditions.append(_known_or(Shoe.stack_heel_mm, Shoe.stack_heel_mm <= f.max_stack_heel_mm))
    if f.exclude_shoe_ids:
        conditions.append(Shoe.id.not_in(f.exclude_shoe_ids))
    return stmt.where(*conditions)


def _jsonable(value):
    return float(value) if hasattr(value, "is_finite") else value  # Decimal -> float


def candidate(shoe: Shoe, score: float | None, note: str | None) -> ShoeCandidate:
    specs = {field: _jsonable(getattr(shoe, field)) for field in SPEC_FIELDS}
    return ShoeCandidate(
        shoe_id=shoe.id,
        name=f"{shoe.brand} {shoe.model} {shoe.version}",
        specs={k: v for k, v in specs.items() if v is not None},
        unknown_specs=[k for k, v in specs.items() if v is None],
        score=round(max(score or 0.0, 0.0), 4),
        best_fit_note=note,
    )


def search_shoes(
    session: Session, store: VectorStore, filters: ShoeFilters, query: str, limit: int = 20
) -> list[ShoeCandidate]:
    if get_settings().vector_backend == "pgvector":
        return _search_pgvector(session, store, filters, query, limit)
    return _search_two_step(session, store, filters, query, limit)


def _search_pgvector(session, store, filters, query, limit) -> list[ShoeCandidate]:
    """One SQL query: spec filters + `embedding <=> :query` ordering, best note per shoe."""
    vector = store.embeddings.embed_query(query)
    distance = FitNote.embedding.cosine_distance(vector)
    best_note = apply_filters(
        select(Shoe.id.label("shoe_id"), FitNote.text, distance.label("distance"))
        .outerjoin(FitNote, (FitNote.shoe_id == Shoe.id) & FitNote.embedding.is_not(None))
        .ext(distinct_on(Shoe.id))
        .order_by(Shoe.id, distance),
        filters,
    ).subquery()
    rows = session.execute(
        select(Shoe, best_note.c.text, best_note.c.distance)
        .join(best_note, best_note.c.shoe_id == Shoe.id)
        .order_by(best_note.c.distance.asc().nulls_last(), Shoe.id)
        .limit(limit)
    ).all()
    return [candidate(shoe, None if dist is None else 1 - dist, text) for shoe, text, dist in rows]


def _search_two_step(session, store, filters, query, limit) -> list[ShoeCandidate]:
    """Chroma: filter shoes in SQL, then rank their fit notes in the vector store."""
    shoes = {s.id: s for s in session.scalars(apply_filters(select(Shoe), filters))}
    if not shoes:
        return []
    note_count = session.scalar(
        select(func.count()).select_from(FitNote).where(FitNote.shoe_id.in_(list(shoes)))
    )
    best: dict[int, tuple[float, str]] = {}
    if note_count:
        hits = relevance_search(
            store, query, k=note_count, filter={"shoe_id": {"$in": list(shoes)}}
        )
        for doc, score in hits:
            best.setdefault(doc.metadata["shoe_id"], (score, doc.page_content))
    ranked = sorted(shoes, key=lambda sid: (-best.get(sid, (-1.0, ""))[0], sid))[:limit]
    return [candidate(shoes[sid], *best.get(sid, (None, None))) for sid in ranked]
