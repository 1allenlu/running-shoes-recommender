# Running Shoe Recommender

Get scanned once, and never guess on a shoe again. Upload a Fleet Feet / Volumental foot scan,
answer a short questionnaire, and get the top 3 running shoes that fit, with the size to order
and links to buy that exact pair. See [ROADMAP.md](ROADMAP.md) for the full plan.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker.

```bash
uv sync                      # install dependencies into .venv
cp .env.example .env         # then fill in ANTHROPIC_API_KEY, LANGSMITH_API_KEY, LLM_MODEL
docker compose up --build    # Postgres 16 + pgvector, runs migrations, starts the API
```

The API runs at http://localhost:8000 (`/health`, `/docs`).

To run the API outside Docker against the compose database:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.api.main:app --reload
```

## Development

```bash
uv run pytest                # DB tests skip if Postgres isn't reachable
uv run ruff check . && uv run ruff format .
uv run python -m app.smoke   # sends a trivial chain trace to LangSmith
```

New migration after changing `app/db/models.py`:

```bash
uv run alembic revision --autogenerate -m "describe change"
```
