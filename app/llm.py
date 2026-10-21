"""Chat model for the scan parser and the agent. `LLM_PROVIDER` picks Claude, Gemini (has a
free tier) or a local Ollama model; `LLM_MODEL` overrides the provider's default model."""

from langchain_core.language_models import BaseChatModel

from app.config import get_settings

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "google": "gemini-3.5-flash-lite",  # free tier, most requests/day of the free models
    "ollama": "qwen3-vl:8b",
}


def model_name() -> str:
    settings = get_settings()
    return settings.llm_model or DEFAULT_MODELS[settings.llm_provider]


def reads_pdfs() -> bool:
    """Claude and Gemini take PDFs directly; local models need the pages as images."""
    return get_settings().llm_provider in ("anthropic", "google")


def get_chat_model() -> BaseChatModel:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name(), api_key=settings.anthropic_api_key, max_tokens=16000
        )
    if settings.llm_provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name(), api_key=settings.google_api_key, temperature=0
        )
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name(),
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=settings.ollama_num_ctx,
            # Thinking makes each agent step take minutes on a laptop; off by default.
            reasoning=settings.ollama_think,
        )
    raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider}")


def llm_ready() -> tuple[bool, str]:
    """Whether the configured provider can be called (for skipping live tests)."""
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        if settings.anthropic_api_key is None:
            return False, "ANTHROPIC_API_KEY not set"
        return True, ""
    if settings.llm_provider == "google":
        if settings.google_api_key is None:
            return False, "GOOGLE_API_KEY not set"
        return True, ""
    import httpx

    try:
        tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).json()
    except httpx.HTTPError:
        return False, f"Ollama not reachable at {settings.ollama_base_url}"
    if model_name() not in {m["name"] for m in tags.get("models", [])}:
        return False, f"Ollama model {model_name()} not pulled (ollama pull {model_name()})"
    return True, ""
