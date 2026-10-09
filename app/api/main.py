from fastapi import FastAPI

from app.config import configure_langsmith

configure_langsmith()

app = FastAPI(title="Running Shoe Recommender", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
