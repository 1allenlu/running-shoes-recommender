from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import chat, recommend, shoes, users
from app.config import configure_langsmith, get_settings
from app.llm import llm_ready, model_name

configure_langsmith()

# The Next.js app in web/, built as static files (`npm run build` -> web/out).
WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "out"

app = FastAPI(title="LastFit", version="0.2.0")
app.include_router(users.router)
app.include_router(recommend.router)
app.include_router(shoes.router)
app.include_router(chat.router)
# `npm run dev` serves the frontend on :3000 and calls this API across origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", tags=["health"])
def status() -> dict:
    """Whether the AI model (scan reading) is configured. Ranking never needs it."""
    ready, reason = llm_ready()
    return {
        "llm_ready": ready,
        "reason": reason or None,
        "provider": get_settings().llm_provider,
        "model": model_name(),
    }


# The web app. Mounted last so the API routes above take precedence.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
else:

    @app.get("/", include_in_schema=False)
    def no_frontend() -> HTMLResponse:
        return HTMLResponse(
            "<p>The web app isn't built yet. Run <code>cd web && npm install && npm run build"
            "</code>, then reload. API docs are at <a href='/docs'>/docs</a>.</p>"
        )
