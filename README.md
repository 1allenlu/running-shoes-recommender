# Running Shoe Recommender

Get scanned once, and never guess on a shoe again. Upload a Fleet Feet / Volumental foot scan,
answer a short questionnaire, and get the top 3 running shoes that fit, with the size to order
and links to buy that exact pair. See [ROADMAP.md](ROADMAP.md) for the full plan.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a local Postgres with the
[pgvector](https://github.com/pgvector/pgvector) extension. (Docker setup comes later.)

```bash
uv sync                      # install dependencies into .venv
cp .env.example .env         # then fill in ANTHROPIC_API_KEY, LANGSMITH_API_KEY, LLM_MODEL
createuser -s shoe && createdb -O shoe shoe && createdb -O shoe shoe_test
uv run alembic upgrade head  # creates all tables (and enables the vector extension)
uv run uvicorn app.api.main:app --reload
```

The API runs at http://localhost:8000 (`/health`, `/docs`).

## Catalog and retrieval

```bash
uv run python -m app.ingest.load_catalog       # seed files -> Postgres (safe to re-run)
uv run python -m app.ingest.validate_catalog   # lists missing specs, draft notes, size charts
uv run python -m app.ingest.embed_fit_notes    # fit notes -> Chroma (./data/chroma)
uv run python -m app.retrieval.sample_queries  # 10 sample "feel" queries, top shoes each
```

Seed data lives in `data/seed/`. `TODO` cells load as empty and show up in validation.
Fit notes with `"source": "draft-unverified"` are placeholders to replace with real sources.

## Offers (sample feed)

```bash
uv run python -m app.ingest.load_offers        # data/seed/sample_offers_feed.csv -> offers
```

The sample feed is fake: two made-up stores, `example.com` links, no prices. Swap in a real
affiliate feed with the same columns. Safe to run nightly: refreshes `updated_at`, marks
products missing from the feed out of stock, and lists products that match no catalog shoe.
Offers older than 48 hours are never shown.

## Vector backends

`VECTOR_BACKEND=chroma` (default) stores fit-note embeddings in `./data/chroma`;
`VECTOR_BACKEND=pgvector` stores them in `fit_notes.embedding`. Run `embed_fit_notes` after
switching. Tests run every search test on both.

## Scan parser

```bash
uv run python -m app.parsing.scan_parser report.pdf          # or several screenshots
```

Reads a Fleet Feet / Volumental report with Claude (`LLM_MODEL`) and prints the parsed
`FootProfile`. Needs `ANTHROPIC_API_KEY`. To check accuracy, add a hand-checked sample under
`data/sample_scans/` (see its README); `uv run pytest -m llm` then compares the parser to it.

## Recommendations (agent + API)

`POST /users` → `POST /users/{id}/scans` (upload) → `PUT /users/{id}/profile` (confirm) →
`PUT /users/{id}/questionnaire` → `POST /users/{id}/recommend` → poll `GET /tasks/{task_id}`.
See `/docs` for every endpoint.

The agent (`app/agent/`) only chooses shoes and explains why. Code then computes sizes
(`pick_size`, from the longer foot), attaches offers, removes any link not in `offers`, and
adds the affiliate disclosure. `pick_size` needs the `Volumental` reference chart plus the
brand's chart in `size_charts.csv`; until those are filled, it rounds the scanned size up to
the next half size and marks the size as not confident.

`uv run pytest -m llm` runs the agent for real on the 5 profiles in
`evals/datasets/agent_profiles.json` (needs `ANTHROPIC_API_KEY`).

## Development

```bash
uv run pytest                # uses the shoe_test database; DB tests skip if Postgres is down
uv run ruff check . && uv run ruff format .
uv run python -m app.smoke   # sends a trivial chain trace to LangSmith
```

New migration after changing `app/db/models.py`:

```bash
uv run alembic revision --autogenerate -m "describe change"
```
