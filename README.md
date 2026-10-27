# Running Shoe Recommender

Get scanned once, and never guess on a shoe again. Upload a Fleet Feet / Volumental foot scan,
answer a short questionnaire, and get the top 3 running shoes that fit, with the size to order
and links to buy that exact pair. See [ROADMAP.md](ROADMAP.md) for the full plan.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a local Postgres with the
[pgvector](https://github.com/pgvector/pgvector) extension. (Docker setup comes later.)

```bash
uv sync                      # install dependencies into .venv
cp .env.example .env         # then pick LLM_PROVIDER (see below) and add any keys
createuser -s shoe && createdb -O shoe shoe && createdb -O shoe shoe_test
uv run alembic upgrade head  # creates all tables (and enables the vector extension)
uv run uvicorn app.api.main:app --reload
```

The API runs at http://localhost:8000 (`/health`, `/docs`).

## Web app

```bash
uv run uvicorn app.api.main:app --reload     # then open http://localhost:8000
```

The web app (`app/web/`: plain HTML, CSS and JavaScript, no build step) walks a runner through
scan upload → confirm the profile → questionnaire → three picks with sizes and buy links →
feedback. It follows the system light/dark setting and remembers the session in the browser,
so a reload returns to the same step. If no LLM is configured it says so, and the scan can be
entered by hand. The API docs stay at `/docs`.

## Choosing the LLM

The scan parser and the agent use one chat model, set by `LLM_PROVIDER`:

| `LLM_PROVIDER` | Cost | Default `LLM_MODEL` | Notes |
| --- | --- | --- | --- |
| `anthropic` | Paid API | `claude-opus-5-5` | Best quality; needs `ANTHROPIC_API_KEY`; reads PDFs directly |
| `google` | Free tier (cloud) | `gemini-3.5-flash-lite` | Needs a free `GOOGLE_API_KEY` from aistudio.google.com/apikey; reads PDFs directly |
| `ollama` | Free, local | `qwen3-vl:8b` | No key, but runs on your machine (heavy: an 8B model on a laptop is slow and hot) |

To use Gemini's free tier:

```bash
echo "LLM_PROVIDER=google" >> .env
echo "GOOGLE_API_KEY=..." >> .env       # from aistudio.google.com/apikey
```

Free-tier limits are per day (see aistudio.google.com/rate-limit). One recommendation makes
roughly 10-20 model calls, so run a single live profile at a time, e.g.
`uv run pytest -m llm -k wide-forefoot`. Free-tier prompts may be used by Google to improve
its products; check the terms before sending real scans.

To use Ollama:

```bash
brew install ollama && brew services start ollama
ollama pull qwen3-vl:8b                 # ~6 GB; reads images and calls tools
echo "LLM_PROVIDER=ollama" >> .env
```

Small local models read scans and run the agent less reliably than Claude, so check the
parsed profile before confirming it, and watch the `flags` on recommendations.

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

## Feedback loop

`POST /users/{id}/feedback` records a rating and notes for a shoe the runner tried. On the
next recommendation: shoes rated 2 or lower are excluded, shoes rated 3 are ranked lower, and
notes like "toe box too narrow" are turned into fit constraints (one model call, using that
shoe's specs) that narrow every search and are re-checked on the final picks.

## Evals

```bash
cp evals/datasets/expert_picks.template.json evals/datasets/expert_picks.json  # then fill in
uv run python -m evals.run_evals --local --limit 2        # score locally, no LangSmith
uv run python -m evals.run_evals --backend both           # LangSmith experiments + table below
uv run python -m evals.run_evals --parser                 # scan-parser accuracy on samples
```

Scores: **hit rate** (an expert's pick is in the top 3), **size accuracy** (within half a size
of the expert's), **link validity** (every link exists in `offers`; must be 1.00), and
**parser accuracy** (share of scan fields read correctly). LangSmith runs need
`LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`. Each profile makes ~10-20 model calls.

Chroma vs pgvector (written by `--backend both`):

<!-- eval-results:start -->
_Not run yet: needs expert picks in `evals/datasets/expert_picks.json` and an LLM provider._
<!-- eval-results:end -->

## MCP server (Claude Desktop)

The MCP server exposes three tools: `find_shoes`, `fit_check` and `get_offers`. They make no
model calls; Claude Desktop does the reasoning. Add this to
`~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "shoe-recommender": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "--directory", "/Users/allenlu/Desktop/projects/running-shoes-recommender",
        "run", "python", "-m", "app.mcp_server"
      ]
    }
  }
}
```

Postgres must be running, the catalog and offers loaded, and fit notes embedded (see above).
Try: "Find shoes for user `<id>`", "How would the Ghost 17 fit user `<id>`?",
"Where can I buy the Ghost 17 in 9.5 wide?". Offers older than 48 hours are hidden, so re-run
`load_offers` if links disappear.

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
