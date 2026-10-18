"""Settings loaded from environment variables and `.env`."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-opus-5-5"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    vector_backend: Literal["chroma", "pgvector"] = "chroma"
    chroma_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"

    database_url: str = "postgresql+psycopg://shoe:shoe@localhost:5432/shoe"

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "shoe-rec"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_langsmith(settings: Settings | None = None) -> bool:
    """Export LangSmith settings to os.environ, where LangChain reads them.

    pydantic-settings reads `.env` into the Settings object only, so without this
    the tracer never sees values that live in `.env`. Returns whether tracing is on.
    """
    settings = settings or get_settings()
    enabled = settings.langsmith_tracing and settings.langsmith_api_key is not None
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key is not None:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    return enabled
