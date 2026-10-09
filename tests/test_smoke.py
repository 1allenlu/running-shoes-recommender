import pytest

from app.config import configure_langsmith
from app.smoke import build_chain, main


def test_chain_output():
    assert build_chain().invoke("  Hello Shoe World ") == {"text": "hello shoe world", "words": 3}


@pytest.mark.tracing
def test_trace_reaches_langsmith(capsys):
    if not configure_langsmith():
        pytest.skip("LANGSMITH_TRACING/LANGSMITH_API_KEY not set")
    main()
    assert "Trace sent to LangSmith" in capsys.readouterr().out
