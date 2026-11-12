# LastFit: running shoe recommender

Get scanned once, and never guess on a shoe again. Upload a Fleet Feet / Volumental foot scan,
answer a few questions, and get the top 3 running shoes that fit, with the size to order
and links to buy that exact pair. The current spec is [CLAUDE_CODE_PROMPT.md](CLAUDE_CODE_PROMPT.md)
(LastFit); [docs/DECISIONS.md](docs/DECISIONS.md) maps it to the code.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a local Postgres with the
[pgvector](https://github.com/pgvector/pgvector) extension. (Docker setup comes later.)

```bash
uv sync                      # install dependencies into .venv
cp .env.example .env         # then pick LLM_PROVIDER (see below) and add any keys
createuser -s shoe && createdb -O shoe shoe && createdb -O shoe shoe_test
uv run alembic upgrade head  # creates all tables (and enables the vector extension)
(cd web && npm install && npm run build)     # builds the web app into web/out (Node 22)
uv run uvicorn app.api.main:app --reload --port 8001
```

Open http://localhost:8001 for the app; the API docs are at http://localhost:8001/docs.
(Port 8001, not uvicorn's default 8000.)

## Web app

`web/` is a Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Motion app, exported as
static files that FastAPI serves from `web/out`, so one port serves everything. The flow:

1. **Scan**: drag-and-drop screenshots/PDF (react-dropzone) with an upload progress bar.
2. **Confirm**: every value editable; scales show the LEFT arrow above and RIGHT below, like
   the report, and the arrows drag (or move with arrow keys).
3. **Preferences**: one question per screen with a progress bar, each step validated with
   React Hook Form + Zod.
4. **Shoe history**: catalog autocomplete, loved / fine / hated, issue tags.
5. **Fit list**: three product-style cards with a fit score, a fit meter (shadcn charts) from
   the ranker's sub-scores, reasons, a caveat, the size to order and buy links; a feedback
   dialog; and a follow-up chat that streams from `POST /users/{id}/chat`.

For frontend work with hot reload, run the API on 8001 as above and, in another terminal:

```bash
cd web && npm run dev        # http://localhost:3000, calls the API on :8001 (web/.env.development)
npm run gen:api              # regenerate lib/api-types.ts after changing the API
npm run typecheck && npm run lint
```

The session (user id, answers) lives in the browser's localStorage, so a reload returns to the
same step. If no LLM is configured, scan reading and chat say so; manual entry and ranking
work without one.

## Choosing the LLM

The scan parser and the follow-up chat use an LLM (the explainer comes later); ranking is
our own code and needs no key. The model is set by `LLM_PROVIDER`:

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

Free-tier limits are per day (see aistudio.google.com/rate-limit); reading one scan is one
call. Free-tier prompts may be used by Google to improve its products; check the terms before
sending real scans.

To use Ollama:

```bash
brew install ollama && brew services start ollama
ollama pull qwen3-vl:8b                 # ~6 GB; reads images
echo "LLM_PROVIDER=ollama" >> .env
```

Small local models read scans less reliably than Claude, so check the parsed profile before
confirming it.

## Catalog and retrieval

```bash
uv run python -m app.ingest.load_catalog       # seed files -> Postgres (safe to re-run)
uv run python -m app.ingest.validate_catalog   # lists missing specs, draft notes, size charts
uv run python -m app.ingest.validate_catalog --todo  # rewrites data/seed/TODO_VERIFY.md
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

Reads a Fleet Feet / Volumental report with the configured LLM and prints the parsed
`FootProfile`. To check accuracy, add a hand-checked sample under
`data/sample_scans/` (see its README); `uv run pytest -m llm` then compares the parser to it.

## Ranking (stage 1 fit scorer)

Shoes are ranked by our own scorer in `app/ranking/`, never by the LLM. Hard filters drop
shoes that can't work (hated models, recurring issues, budget, no wide version for 2E+ feet,
goals), then each candidate gets sub-scores for width, volume, heel, the wide forefoot + low
instep combination, ride, history and budget. Weights and tables live in
[config/scoring.yaml](config/scoring.yaml), so tuning needs no code change.

```bash
uv run python -m app.ranking.pipeline --profile data/sample_scans/expected_profile.json
uv run python -m app.ranking.pipeline --profile data/profiles/03_wide_high_instep.json \
    --prefs data/profiles/example_preferences.json \
    --history data/profiles/example_history.json      # add --json or --source db
```

Each pick prints its score, every `weight x sub-score` contribution with the reason behind it,
and the size to order. Until the specs in `data/seed/TODO_VERIFY.md` are filled in, most
sub-scores fall back to a neutral 0.5 and the output carries a low-confidence warning.

## Recommendations (API)

`POST /users` → `POST /users/{id}/scans` (upload; or `POST /users/{id}/scans/manual`) →
`PUT /users/{id}/scans/{scan_id}/confirm` → `PUT /users/{id}/preferences` →
`POST` or `PUT /users/{id}/history` → `POST /users/{id}/recommend` → poll
`GET /tasks/{task_id}`. `GET /shoes/search?q=` autocompletes shoe names. See `/docs`.

`/recommend` runs the ranker (`app/recommend.py`): only the confirmed profile is used, each
pick gets its size (longer foot, brand chart, `size_offset`, +0.5 running room), up to 3
fresh in-stock offers for that exact pair, the link guard (any URL not in `offers` is removed
and flagged) and the affiliate disclosure. Reasons and the caveat are the ranker's own
sub-score notes, so every one maps to a contribution. The full candidate list with scores and
contributions is stored in `recommendations.candidates`.

## Feedback loop

`POST /users/{id}/feedback` records how a recommended shoe worked out: `outcome`
(loved / fine / hated), `kept`, and issue tags (`toe_pressure`, `heel_slip`, `too_narrow`,
`too_much_volume`, `arch_discomfort`, `too_soft`, `too_firm`). The next ranking treats it like
shoe history: hated models are excluded, issues raise the matching weight, an issue reported on
two or more shoes excludes shoes whose specs cause it, and loved/hated shoes steer
`history_fit`. Both tables are the training data for the stage 2 ranker.

## Evals

```bash
cp evals/datasets/expert_picks.template.json evals/datasets/expert_picks.json  # then fill in
uv run python -m evals.run_evals --local   # score locally, no LangSmith
uv run python -m evals.run_evals           # LangSmith experiment + table below
uv run python -m evals.run_evals --parser  # scan-parser accuracy on samples (calls the LLM)
```

Scores: **hit rate** (an expert's pick is in the top 3), **size accuracy** (within half a size
of the expert's), **link validity** (every link exists in `offers`; must be 1.00),
**grounding** (every reason and caveat traces to the pick's sub-scores) and **parser
accuracy** (share of scan fields read correctly). LangSmith runs need
`LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`. Recommendation evals make no LLM calls.

Latest results:

<!-- eval-results:start -->
_Not run yet: needs expert picks in `evals/datasets/expert_picks.json`._
<!-- eval-results:end -->

## MCP server (Claude Desktop)

The MCP server exposes three tools that reuse the ranking pipeline: `find_shoes` (top 3 with
fit scores, contributions, sizes and links), `fit_check` (one shoe's rank, sub-scores or
exclusion reason, plus fit notes) and `get_offers`. Claude Desktop explains; it doesn't rank. Add this to
`~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "lastfit": {
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
