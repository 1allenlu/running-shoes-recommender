from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import recommend, users
from app.config import configure_langsmith, get_settings
from app.llm import llm_ready, model_name

configure_langsmith()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Running Shoe Recommender", version="0.1.0")
app.include_router(users.router)
app.include_router(recommend.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", tags=["health"])
def status() -> dict:
    """Whether the AI model (scan reading, recommendations) is configured."""
    ready, reason = llm_ready()
    return {
        "llm_ready": ready,
        "reason": reason or None,
        "provider": get_settings().llm_provider,
        "model": model_name(),
    }


# The web app. Mounted last so the API routes above take precedence.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
