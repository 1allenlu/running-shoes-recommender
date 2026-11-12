from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ShoeOut
from app.db.models import Shoe

router = APIRouter(prefix="/shoes", tags=["shoes"])


@router.get("/search")
def search_shoes(
    q: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = 10,
) -> list[ShoeOut]:
    """Autocomplete for the history screen: every word must appear in brand, model or version."""
    name = func.concat_ws(" ", Shoe.brand, Shoe.model, Shoe.version)
    stmt = select(Shoe)
    for word in q.split():
        stmt = stmt.where(name.ilike(f"%{word}%"))
    shoes = session.scalars(stmt.order_by(Shoe.brand, Shoe.model).limit(limit))
    return [
        ShoeOut(
            shoe_id=s.id,
            name=f"{s.brand} {s.model} {s.version}",
            brand=s.brand,
            model=s.model,
            version=s.version,
        )
        for s in shoes
    ]
