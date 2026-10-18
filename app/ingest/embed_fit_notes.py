"""Chunk and embed fit notes from Postgres into the vector store. Rebuilds the collection.

uv run python -m app.ingest.embed_fit_notes
"""

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FitNote, Shoe

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)


def fit_note_documents(session: Session) -> tuple[list[Document], list[str]]:
    rows = session.execute(
        select(FitNote, Shoe).join(Shoe, FitNote.shoe_id == Shoe.id).order_by(FitNote.id)
    )
    docs, ids = [], []
    for note, shoe in rows:
        metadata = {
            "fit_note_id": note.id,
            "shoe_id": shoe.id,
            "brand": shoe.brand,
            "model": shoe.model,
            "version": shoe.version,
            "source": note.source,
        }
        for i, chunk in enumerate(splitter.split_text(note.text)):
            docs.append(Document(page_content=chunk, metadata=metadata))
            ids.append(f"fit_note:{note.id}:{i}")
    return docs, ids


def embed_fit_notes(session: Session, store: VectorStore) -> int:
    """Rebuild the store from Postgres. Both backends (Chroma, pgvector) have reset_collection."""
    docs, ids = fit_note_documents(session)
    store.reset_collection()
    if docs:
        store.add_documents(docs, ids=ids)
    return len(docs)


def main() -> None:
    from app.config import configure_langsmith
    from app.db.session import SessionLocal
    from app.retrieval.store import get_store

    configure_langsmith()
    with SessionLocal() as session:
        count = embed_fit_notes(session, get_store())
    print(f"embedded {count} chunks")


if __name__ == "__main__":
    main()
