"""Phase 0 tracing check: run a trivial chain and confirm it appears in LangSmith.

    uv run python -m app.smoke

Makes no LLM call, so only LANGSMITH_* needs to be set.
"""

from langchain_core.runnables import RunnableLambda
from langchain_core.tracers.langchain import wait_for_all_tracers

from app.config import configure_langsmith, get_settings


def build_chain():
    normalize = RunnableLambda(lambda text: text.strip().lower(), name="normalize")
    count_words = RunnableLambda(lambda text: {"text": text, "words": len(text.split())})
    return (normalize | count_words).with_config(run_name="phase0_smoke")


def main() -> None:
    tracing = configure_langsmith()
    result = build_chain().invoke("  Get scanned once, and never guess on a shoe again.  ")
    wait_for_all_tracers()
    print(result)
    if tracing:
        print(f"Trace sent to LangSmith project '{get_settings().langsmith_project}'.")
    else:
        print("LangSmith tracing is off: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env.")


if __name__ == "__main__":
    main()
