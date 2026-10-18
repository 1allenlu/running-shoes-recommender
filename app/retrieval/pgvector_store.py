"""Fit-note vector store on Postgres: embeddings live in `fit_notes.embedding`.

One embedding per fit note, so each note must fit in one chunk (500 chars). Filters use the
same shape as Chroma's: {"shoe_id": 3} or {"shoe_id": {"$in": [1, 2]}}.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import FitNote, Shoe


def shoe_id_condition(filter: dict | None):
    """SQL condition for a Chroma-style shoe_id filter, or None for no filter."""
    if not filter:
        return None
    if set(filter) != {"shoe_id"}:
        raise ValueError(f"only shoe_id filters are supported, got {filter}")
    value = filter["shoe_id"]
    if isinstance(value, dict):
        return FitNote.shoe_id.in_(value["$in"])
    return FitNote.shoe_id == value


class PgFitNoteStore(VectorStore):
    def __init__(self, embeddings: Embeddings, session_factory: Callable[[], Session]):
        self._embeddings = embeddings
        self._session_factory = session_factory

    @property
    def embeddings(self) -> Embeddings:
        return self._embeddings

    def reset_collection(self) -> None:
        with self._session_factory() as session:
            session.execute(update(FitNote).values(embedding=None))
            session.commit()

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: list[dict] | None = None,
        *,
        ids: list[str] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        texts = list(texts)
        metadatas = metadatas or [{}] * len(texts)
        ids = ids or [f"fit_note:{m['fit_note_id']}:0" for m in metadatas]
        if any(not doc_id.endswith(":0") for doc_id in ids):
            raise ValueError(
                "pgvector stores one embedding per fit note; split notes over 500 chars "
                "into separate notes"
            )
        vectors = self._embeddings.embed_documents(texts)
        with self._session_factory() as session:
            for meta, vector in zip(metadatas, vectors, strict=True):
                session.execute(
                    update(FitNote)
                    .where(FitNote.id == meta["fit_note_id"])
                    .values(embedding=vector)
                )
            session.commit()
        return ids

    def similarity_search_with_score(
        self, query: str, k: int = 4, filter: dict | None = None, **kwargs: Any
    ) -> list[tuple[Document, float]]:
        """Returns cosine distance (lower is closer)."""
        vector = self._embeddings.embed_query(query)
        distance = FitNote.embedding.cosine_distance(vector)
        stmt = (
            select(FitNote, Shoe, distance.label("distance"))
            .join(Shoe, FitNote.shoe_id == Shoe.id)
            .where(FitNote.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
        condition = shoe_id_condition(filter)
        if condition is not None:
            stmt = stmt.where(condition)
        with self._session_factory() as session:
            rows = session.execute(stmt).all()
        return [
            (
                Document(
                    id=f"fit_note:{note.id}:0",
                    page_content=note.text,
                    metadata={
                        "fit_note_id": note.id,
                        "shoe_id": shoe.id,
                        "brand": shoe.brand,
                        "model": shoe.model,
                        "version": shoe.version,
                        "source": note.source,
                    },
                ),
                float(dist),
            )
            for note, shoe, dist in rows
        ]

    def similarity_search(
        self, query: str, k: int = 4, filter: dict | None = None, **kwargs: Any
    ) -> list[Document]:
        return [doc for doc, _ in self.similarity_search_with_score(query, k, filter)]

    def _select_relevance_score_fn(self) -> Callable[[float], float]:
        return lambda distance: 1.0 - distance

    @classmethod
    def from_texts(
        cls,
        texts: list[str],
        embedding: Embeddings,
        metadatas: list[dict] | None = None,
        *,
        ids: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> "PgFitNoteStore":
        store = cls(embedding, kwargs["session_factory"])
        store.add_texts(texts, metadatas, ids=list(ids) if ids else None)
        return store
