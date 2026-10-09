import os

from app.config import Settings, configure_langsmith


def test_defaults(monkeypatch):
    monkeypatch.delenv("VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.vector_backend == "chroma"
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"


def test_reads_env(monkeypatch):
    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert settings.vector_backend == "pgvector"
    assert settings.anthropic_api_key.get_secret_value() == "sk-test"
    assert "sk-test" not in repr(settings)


def test_langsmith_off_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    settings = Settings(_env_file=None, langsmith_tracing=True)
    assert configure_langsmith(settings) is False
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_langsmith_exports_env(monkeypatch):
    for var in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(
        _env_file=None, langsmith_tracing=True, langsmith_api_key="ls-test", langsmith_project="p"
    )
    assert configure_langsmith(settings) is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-test"
    assert os.environ["LANGSMITH_PROJECT"] == "p"
