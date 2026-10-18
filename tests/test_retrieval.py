"""Embedding and sample queries, on both backends (the `store` fixture is parametrized)."""

import pytest
from langchain_chroma import Chroma
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import FitNote
from app.ingest.embed_fit_notes import embed_fit_notes, fit_note_documents
from app.ingest.load_catalog import load_catalog
from app.retrieval.pgvector_store import PgFitNoteStore
from app.retrieval.sample_queries import run
from app.retrieval.store import get_store


@pytest.mark.parametrize("backend_name, cls", [("chroma", Chroma), ("pgvector", PgFitNoteStore)])
def test_backend_switch(monkeypatch, tmp_path, backend_name, cls):
    monkeypatch.setattr(get_settings(), "vector_backend", backend_name)
    store = get_store(DeterministicFakeEmbedding(size=384), persist_directory=str(tmp_path))
    assert isinstance(store, cls)


def stored_count(store, session) -> int:
    if isinstance(store, Chroma):
        return len(store.get()["ids"])
    stmt = select(func.count()).select_from(FitNote).where(FitNote.embedding.is_not(None))
    return session.scalar(stmt)


@pytest.mark.db
def test_embed_is_rebuild_not_append(db_session, seed_dir, store):
    load_catalog(db_session, seed_dir)
    assert embed_fit_notes(db_session, store) == 3
    assert embed_fit_notes(db_session, store) == 3
    assert stored_count(store, db_session) == 3

    docs, _ = fit_note_documents(db_session)
    assert docs[0].metadata.keys() >= {"shoe_id", "brand", "model", "version", "source"}


@pytest.mark.db
def test_queries_return_distinct_shoes(db_session, seed_dir, store):
    load_catalog(db_session, seed_dir)
    embed_fit_notes(db_session, store)
    results = run(store, ["roomy"])
    assert results["roomy"] == [results["roomy"][0]]  # 3 notes, but only 1 shoe
    assert results["roomy"][0][0] == "Acme Glide 2"
