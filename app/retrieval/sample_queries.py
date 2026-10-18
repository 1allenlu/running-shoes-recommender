"""Run sample "feel" queries against the fit-note store and print the top shoes.

    uv run python -m app.retrieval.sample_queries

Each query goes through a LangChain retriever, so it is traced in LangSmith when enabled.
"""

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

SAMPLE_QUERIES = [
    "roomy toe box, secure heel",
    "soft but stable",
    "wide forefoot with a narrow heel",
    "low instep, needs a snug low-volume upper",
    "available in extra-wide",
    "light and fast for tempo runs",
    "max cushioning for long easy runs",
    "zero drop",
    "traditional high drop daily trainer",
    "bouncy energetic foam",
]


def top_shoes(docs: list[Document], limit: int = 3) -> list[tuple[str, str]]:
    """Collapse ranked chunks to distinct shoes, keeping each shoe's best-matching note."""
    shoes: dict[int, tuple[str, str]] = {}
    for doc in docs:
        m = doc.metadata
        name = f"{m['brand']} {m['model']} {m['version']}"
        shoes.setdefault(m["shoe_id"], (name, doc.page_content))
    return list(shoes.values())[:limit]


def run(store: VectorStore, queries: list[str] = SAMPLE_QUERIES, k: int = 12) -> dict:
    retriever = store.as_retriever(search_kwargs={"k": k})
    return {query: top_shoes(retriever.invoke(query)) for query in queries}


def main() -> None:
    from langchain_core.tracers.langchain import wait_for_all_tracers

    from app.config import configure_langsmith
    from app.retrieval.store import get_store

    configure_langsmith()
    for query, shoes in run(get_store()).items():
        print(f"\n{query}")
        for name, note in shoes:
            print(f"  {name:32} {note[:90]}")
    wait_for_all_tracers()


if __name__ == "__main__":
    main()
