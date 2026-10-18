from fastapi import FastAPI

from app.api.routes import recommend, users
from app.config import configure_langsmith

configure_langsmith()

app = FastAPI(title="Running Shoe Recommender", version="0.1.0")
app.include_router(users.router)
app.include_router(recommend.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
