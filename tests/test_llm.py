import pytest

from app.agent.recommender import response_format
from app.config import get_settings
from app.llm import get_chat_model, llm_ready, model_name, reads_pdfs


@pytest.fixture
def provider(monkeypatch):
    def use(name: str, **settings):
        monkeypatch.setattr(get_settings(), "llm_provider", name)
        monkeypatch.setattr(get_settings(), "llm_model", "")
        for key, value in settings.items():
            monkeypatch.setattr(get_settings(), key, value)

    return use


def test_google_provider(provider):
    from langchain.agents.structured_output import ToolStrategy
    from langchain_google_genai import ChatGoogleGenerativeAI

    provider("google", google_api_key=None)
    assert llm_ready() == (False, "GOOGLE_API_KEY not set")
    provider("google", google_api_key="test-key")
    assert llm_ready() == (True, "")
    assert model_name() == "gemini-3.5-flash-lite"
    assert isinstance(get_chat_model(), ChatGoogleGenerativeAI)
    assert reads_pdfs()
    assert isinstance(response_format(), ToolStrategy)


def test_anthropic_provider(provider):
    from langchain.agents.structured_output import ProviderStrategy

    provider("anthropic", anthropic_api_key=None)
    assert llm_ready() == (False, "ANTHROPIC_API_KEY not set")
    assert model_name() == "claude-opus-5-5"
    assert reads_pdfs()
    assert isinstance(response_format(), ProviderStrategy)


def test_ollama_provider_sends_pdf_pages_as_images(provider):
    provider("ollama")
    assert not reads_pdfs()


def test_model_override(provider):
    provider("google", llm_model="gemini-3.1-flash-lite")
    assert model_name() == "gemini-3.1-flash-lite"
