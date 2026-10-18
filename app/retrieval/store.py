"""Vector store for fit notes. `VECTOR_BACKEND` picks Chroma (dev) or pgvector."""

from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from app.config import get_settings

FIT_NOTES_COLLECTION = "fit_notes"

# BGE v1.5 retrieves better when short queries carry this instruction; passages go without it.
BGE_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "


@lru_cache
def get_embeddings() -> Embeddings:
    from langchain_huggingface import HuggingFaceEmbeddings

    model = get_settings().embedding_model
    query_kwargs: dict = {"normalize_embeddings": True}
    if model.startswith("BAAI/bge-"):
        query_kwargs["prompt"] = BGE_QUERY_PROMPT
    return HuggingFaceEmbeddings(
        model=model,
        encode_kwargs={"normalize_embeddings": True},
        query_encode_kwargs=query_kwargs,
    )


def relevance_search(
    store: VectorStore, query: str, k: int, filter: dict | None = None
) -> list[tuple[Document, float]]:
    """Ranked documents with relevance in [0, 1] (cosine similarity; float noise clamped)."""
    hits = store._similarity_search_with_relevance_scores(query, k=k, filter=filter)
    return [(doc, min(max(score, 0.0), 1.0)) for doc, score in hits]


def get_store(
    embeddings: Embeddings | None = None, persist_directory: str | None = None
) -> VectorStore:
    settings = get_settings()
    embeddings = embeddings or get_embeddings()

    if settings.vector_backend == "chroma":
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=FIT_NOTES_COLLECTION,
            embedding_function=embeddings,
            persist_directory=persist_directory or settings.chroma_dir,
            collection_metadata={"hnsw:space": "cosine"},
        )
    if settings.vector_backend == "pgvector":
        from app.db.session import SessionLocal
        from app.retrieval.pgvector_store import PgFitNoteStore

        return PgFitNoteStore(embeddings, SessionLocal)
    raise ValueError(f"unknown VECTOR_BACKEND: {settings.vector_backend}")
