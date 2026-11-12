"""Fit-note RAG: the notes about one shoe that best answer a fit question.

Used to ground explanations and chat answers; never to rank.
"""

from langchain_core.vectorstores import VectorStore

from app.retrieval.store import relevance_search

UNVERIFIED_SOURCE = "draft-unverified"


def get_fit_notes(store: VectorStore, shoe_id: int, question: str, k: int = 4) -> list[dict]:
    hits = relevance_search(store, question, k=k, filter={"shoe_id": shoe_id})
    return [
        {
            "fit_note_id": doc.metadata["fit_note_id"],
            "text": doc.page_content,
            "source": doc.metadata["source"],
            "verified": doc.metadata["source"] != UNVERIFIED_SOURCE,
            "relevance": round(score, 4),
        }
        for doc, score in hits
    ]
