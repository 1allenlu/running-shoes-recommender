# Running Shoe Recommender: Build Roadmap

> **For Claude Code:** This is the build plan for the project. Work through the phases in order. Finish a phase only when its "Done when" checks pass. Tick the boxes in this file as you complete tasks. Ask before changing the stack, the data model, or anything under "Guardrails". Keep each phase in its own commits.

---

## 1. Product in one paragraph

A runner gets a free 3D foot scan at Fleet Feet (Volumental scanner), uploads screenshots or the PDF of the report, and answers a short questionnaire. An AI agent recommends the **top 3 running shoes** that fit their foot. Each pick comes with why it fits, the size to order in that brand, and links to buy that exact pair (model + version + size + width). After a few runs, the user reports how the shoes felt, and the next recommendation improves.

**Pitch:** "Get scanned once, and never guess on a shoe again."

**Approach:** recommend on **fit, comfort and the runner's own history**. Do not prescribe shoes from pronation or claim medical benefits.

---

## 2. Stack (fixed; ask before changing)

| Piece | Choice | Role |
| --- | --- | --- |
| Language | Python 3.12, `uv` for dependencies | Everything |
| LLM framework | LangChain (`langchain`, `langchain-core`, `langchain-anthropic`) | Chains, retriever, agent |
| LLM | Claude via `langchain-anthropic`, model set by env var | Report parsing (vision) and the agent |
| Embeddings | `langchain-huggingface` with `BAAI/bge-small-en-v1.5` (384 dims), swappable by env var | Fit-note embeddings |
| Dev vector store | ChromaDB (`langchain-chroma`), persisted to `./data/chroma` | Prototyping |
| Prod store | Postgres 16 + pgvector (`pgvector/pgvector:pg16` image), SQLAlchemy | All tables + vector search |
| API | FastAPI + Uvicorn, Pydantic v2 | Backend |
| Background jobs | FastAPI `BackgroundTasks` (MVP); task state in Postgres | Agent runs |
| MCP | Official MCP Python SDK, `FastMCP` | Expose tools to Claude Desktop |
| Observability + evals | LangSmith | Tracing every run, eval datasets |
| Tests | pytest | Unit + integration |
| Infra | Local Postgres + pgvector for now; Docker Compose (Postgres + API) deferred | Local dev |

---

## 3. Repo layout

```
shoe-rec/
├── ROADMAP.md
├── README.md
├── pyproject.toml
├── docker-compose.yml          # deferred: added later
├── .env.example
├── data/
│   ├── seed/
│   │   ├── shoes.csv              # hand-entered specs
│   │   ├── size_charts.csv        # per-brand sizing
│   │   └── fit_notes.jsonl        # fit notes per shoe, with source
│   ├── sample_scans/              # example Fleet Feet report screenshots
│   └── chroma/                    # dev vector store (gitignored)
├── app/
│   ├── config.py                  # settings from env vars
│   ├── db/
│   │   ├── models.py              # SQLAlchemy tables
│   │   ├── session.py
│   │   └── migrations/            # Alembic
│   ├── schemas/
│   │   ├── foot_profile.py        # Pydantic FootProfile
│   │   └── recommendation.py      # Pydantic output of the agent
│   ├── ingest/
│   │   ├── load_catalog.py        # seed CSV/JSONL -> Postgres
│   │   ├── embed_fit_notes.py     # chunk + embed fit notes
│   │   └── load_offers.py         # affiliate product feed -> offers table
│   ├── retrieval/
│   │   ├── store.py               # get_store(): Chroma or pgvector by env var
│   │   └── hybrid.py              # SQL filters + vector similarity
│   ├── parsing/
│   │   └── scan_parser.py         # image/PDF -> FootProfile (vision LLM)
│   ├── agent/
│   │   ├── tools.py               # the 6 agent tools
│   │   ├── prompts.py
│   │   └── recommender.py         # builds and runs the agent
│   ├── api/
│   │   ├── main.py                # FastAPI app
│   │   └── routes/                # users, scans, recommend, tasks, feedback
│   └── mcp_server.py              # FastMCP server
├── evals/
│   ├── datasets/                  # test profiles + expert picks
│   └── run_evals.py               # LangSmith evaluation runner
└── tests/
```

---

## 4. Environment variables (`.env.example`)

```
ANTHROPIC_API_KEY=
LLM_MODEL=                         # Claude model id for agent + parsing
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
VECTOR_BACKEND=chroma              # chroma | pgvector
DATABASE_URL=postgresql+psycopg://shoe:shoe@localhost:5432/shoe
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=shoe-rec
```

---

## 5. Data model

| Table | Columns |
| --- | --- |
| `shoes` | id, brand, model, version, category (daily, tempo, race, stability, max-cushion), drop_mm, stack_heel_mm, stack_forefoot_mm, weight_g, widths_available (array: standard, wide, extra-wide), toe_box (narrow, medium, roomy), upper_volume (low, medium, high), heel_lock (bool), price_usd |
| `fit_notes` | id, shoe_id, source, text, embedding vector(384) |
| `size_charts` | id, brand, us_size, length_mm_min, length_mm_max, sizing_note |
| `offers` | id, shoe_id, retailer, us_size, width, price_usd, in_stock, affiliate_url, updated_at |
| `users` | id, foot_profile (JSONB), questionnaire (JSONB), created_at |
| `scans` | id, user_id, raw_file_path, parsed_profile (JSONB), parser_version, created_at |
| `tasks` | id, user_id, status (queued, running, done, failed), result (JSONB), error, created_at |
| `feedback` | id, user_id, shoe_id, us_size, width, rating (1–5), notes, created_at |

Index `fit_notes.embedding` with HNSW (cosine). "That exact pair" = shoe_id + us_size + width, which is the key of `offers`.

### Foot profile (output of the scan parser)

The Fleet Feet / Volumental report gives a US size and width letter per foot. Everything else is a category relative to the population, shown as an arrow on a scale. Arrows can sit between bands, so store both the nearest band and a 0–1 position along the scale.

```json
{
  "sex_scale": "men",
  "left": {
    "us_size": 8.1, "width": "E",
    "arch_height":      {"band": "low",    "position": 0.10},
    "instep_height":    {"band": "low",    "position": 0.15},
    "heel_width":       {"band": "wide",   "position": 0.75},
    "pressure":         {"band": "centered","position": 0.50},
    "arch_flexibility": {"band": "moderate","position": 0.50}
  },
  "right": {
    "us_size": 8.3, "width": "E",
    "arch_height":      {"band": "low",    "position": 0.40},
    "instep_height":    {"band": "low",    "position": 0.20},
    "heel_width":       {"band": "medium", "position": 0.62},
    "pressure":         {"band": "medial", "position": 0.15},
    "arch_flexibility": {"band": "flexible","position": 0.35}
  }
}
```

Scales: width 3A, 2A, A, B, C, D, E, 2E, 3E · arch height and instep height low/medium/high · heel width narrow/medium/wide · pressure medial/centered/lateral · arch flexibility flexible/moderate/rigid. Pressure and flexibility come from the pressure plate and may be missing (not every store has one), so they are optional.

### Questionnaire

```json
{
  "weekly_km": 30,
  "goals": ["daily training", "half marathon"],
  "surface": "road",
  "feel": "soft | balanced | firm",
  "budget_usd": 160,
  "loved_shoes": [{"model": "Novablast 4", "notes": "comfortable toe box"}],
  "disliked_shoes": [{"model": "Pegasus 40", "notes": "too narrow in the toes"}]
}
```

---

## 6. Guardrails (do not violate)

1. **Links come only from the `offers` table.** The LLM never writes, edits, or completes a URL. The final output is post-processed: every URL must exist in `offers`, or it is removed and the run is flagged.
2. **No medical claims.** Never claim a shoe prevents, treats, or diagnoses injury. Pressure data is context for fit, not a prescription.
3. **No scraping review sites.** Catalog data is hand-entered or comes from affiliate feeds and brand pages used within their terms.
4. **Affiliate disclosure** appears in every response that contains buy links.
5. **Structured outputs everywhere.** The parser and the agent's final answer are validated Pydantic models, not free text.
6. **Secrets only in `.env`**, never committed.

---

## 7. Phases

### Phase 0: Project setup

- [x] `uv init`, add dependencies, `ruff` + `pytest` configured
- [ ] *(Deferred)* `docker-compose.yml` with `pgvector/pgvector:pg16` (enable the `vector` extension on startup) and the API service. For now, use a local Postgres with pgvector; the first migration enables the extension.
- [x] `app/config.py` reading `.env` with `pydantic-settings`
- [x] Alembic set up; first migration creates all tables in section 5
- [ ] LangSmith tracing on; a trivial chain shows up in the LangSmith project

**Done when:** migrations run cleanly against local Postgres, `pytest` passes, and a test trace appears in LangSmith.

### Phase 1: Catalog and seed data

- [x] `data/seed/shoes.csv` with 20 popular road shoes to start (expand to 40–60 later); include several with wide versions
- [x] `data/seed/size_charts.csv` for each brand in the catalog
- [x] `data/seed/fit_notes.jsonl`: 3–6 notes per shoe, each with a `source` field
- [x] `load_catalog.py` loads all seed files into Postgres (idempotent)

Leave clearly marked `TODO` placeholders for any spec you can't confirm, rather than inventing values. The user will fill or verify them.

**Done when:** catalog loads with no errors, and a validation script reports any shoe missing specs or fit notes.

### Phase 2: Embeddings and retrieval (Chroma first)

- [x] `embed_fit_notes.py`: chunk fit notes with `RecursiveCharacterTextSplitter` (500 chars, 50 overlap), embed, store in Chroma with metadata (shoe_id, brand, model)
- [x] `store.py`: `get_store()` returns Chroma or pgvector based on `VECTOR_BACKEND` (pgvector raises `NotImplementedError` until Phase 6)
- [x] Notebook or script that runs 10 sample queries ("roomy toe box, secure heel", "soft but stable") and prints the top shoes

**Done when:** sample queries return sensible shoes and every retrieval appears in LangSmith.

### Phase 3: Scan parser

- [x] `FootProfile` Pydantic schema matching section 5
- [x] `scan_parser.py`: takes images or a PDF, sends them to the vision LLM with `with_structured_output(FootProfile)`
- [x] Prompt explains the report layout: per-foot size + width letter, arrow positions on each scale, LEFT arrows above and RIGHT arrows below each scale
- [x] Save raw file + parsed result + parser version to `scans`
- [ ] Unit test against `data/sample_scans/` with a hand-checked expected profile

**Done when:** the parser reproduces the hand-checked profile for the sample scan (sizes exact, bands correct, positions within ±0.15).

### Phase 4: Agent

Tools (in `agent/tools.py`), each a LangChain `@tool` with a clear docstring:

| Tool | Behavior |
| --- | --- |
| `get_profile(user_id)` | Foot profile, questionnaire, past feedback |
| `search_shoes(filters, vibe)` | Hybrid search: SQL filters on `shoes` + vector similarity on `fit_notes`; returns ~20 candidates with scores |
| `get_fit_notes(shoe_id, question)` | Top fit-note chunks for that shoe relevant to the question |
| `similar_to(shoe_id)` | Shoes with similar specs and fit notes to one the runner loved |
| `pick_size(brand, foot_us_size, width)` | Size to order in that brand, from `size_charts` + sizing notes; uses the longer foot |
| `get_offers(shoe_id, us_size, width)` | In-stock offers sorted by price, with `affiliate_url` |

Decision logic (put in the system prompt):

1. Read the profile. Size and width come from the **longer foot**.
2. Turn the profile into filters (width availability, toe box, upper volume, drop/stack preferences, budget, category) and a "feel" query.
3. If the runner listed loved shoes, call `similar_to` first.
4. Call `search_shoes`; exclude shoes the runner disliked or rated ≤ 2.
5. For the best 5–6, call `get_fit_notes` to check toe box, width, volume and heel fit against the scan. Watch for combinations a simple rule misses, e.g. **wide forefoot + low instep (low volume)**: needs a roomy toe box but a snug upper and secure heel, not just a "wide" shoe.
6. Rank to a top 3. For each, call `pick_size`, then `get_offers`.
7. Return a `Recommendation` object: for each pick, why it fits (citing fit notes), what to watch for, size and width to order, up to 3 offers. Include the affiliate disclosure.

- [x] Implement tools with tests against the seeded database
- [x] `recommender.py` builds the agent; output validated as `Recommendation`
- [x] Post-processing enforces Guardrail 1 (URLs must exist in `offers`)

**Done when:** for 5 hand-written test profiles, the agent returns 3 valid picks with sizes, and every link exists in `offers`.

### Phase 5: FastAPI

| Endpoint | Behavior |
| --- | --- |
| `POST /users` | Create a user |
| `POST /users/{id}/scans` | Upload report images/PDF; runs parser; returns parsed profile for the user to confirm |
| `PUT /users/{id}/profile` | User confirms or corrects the parsed profile |
| `PUT /users/{id}/questionnaire` | Save questionnaire |
| `POST /users/{id}/recommend` | Start agent as a background task; return `task_id` |
| `GET /tasks/{task_id}` | Status and result |
| `POST /users/{id}/feedback` | Rating + notes for a shoe |
| `GET /health` | Health check |

- [x] Routes implemented with Pydantic request/response models
- [x] Integration test: full flow from scan upload to recommendation result

**Done when:** the integration test passes and `/docs` shows every endpoint.

### Phase 6: Move to pgvector

- [x] pgvector implementation behind `get_store()`
- [x] `hybrid.py`: one SQL query combining spec filters and `embedding <=> :query` ordering
- [x] Re-embed fit notes into Postgres
- [x] Switch `VECTOR_BACKEND=pgvector`; all tests still pass

**Done when:** the full flow works on pgvector, and Chroma still works when the env var is switched back.

### Phase 7: Offers and affiliate links

- [x] `load_offers.py` reads a product feed (CSV/XML) into `offers`, matching feed products to `shoes` + size + width
- [x] Until a real affiliate feed is available, use a clearly labeled sample feed in `data/seed/` with placeholder URLs on an `example.com` domain
- [x] Matching report: feed products that didn't match any shoe
- [x] Script safe to run nightly (idempotent, updates `updated_at`, marks missing items out of stock)

**Done when:** recommendations show offers from the loaded feed, and stale offers (> 48h) are excluded.

### Phase 8: MCP server

- [x] `mcp_server.py` with FastMCP (named `MCPServer` in MCP SDK 2.x) exposing `find_shoes(profile_or_user_id, preferences)`, `fit_check(user_id, shoe)`, `get_offers(shoe, size, width)`, reusing the agent's tool functions
- [x] README section: how to add the server to Claude Desktop's config
- [ ] Manual test from Claude Desktop

**Done when:** Claude Desktop can call all three tools and get correct results.

### Phase 9: Evals (LangSmith)

- [ ] `evals/datasets/`: ~20 test profiles; for each, shoes picked by an experienced runner or fitter (the user will supply these; leave a template)
- [x] Evaluators:
  - **Hit rate:** expert's pick appears in the top 3
  - **Size accuracy:** recommended size within half a size of the expert's
  - **Link validity:** 100% of URLs exist in `offers` (must be 100%)
  - **Parser accuracy** on sample scans
- [ ] Run the same eval with `VECTOR_BACKEND=chroma` and `pgvector`; save a comparison table to the README

**Done when:** evals run from one command and results appear as LangSmith experiments.

### Phase 10: Feedback loop

- [x] Feedback lowers or excludes shoes rated badly; notes like "toe box too narrow" add constraints to the next run (parsed by a small structured-output chain)
- [x] Test: after negative feedback on a shoe, the next recommendation excludes it and respects the new constraint

**Done when:** the test passes.

---

## 8. Out of scope for the MVP

- Gait video analysis or any custom computer vision
- Trail, spike and walking shoes
- Multi-retailer price comparison beyond the loaded feeds
- Frontend (the API + `/docs` + MCP are the MVP interface; a frontend comes after)
- Payments, accounts beyond a basic user id

---

## 9. Open questions (do not decide; ask the user)

- Does the emailed Fleet Feet report carry the same fields as the in-store screen?
- Which affiliate programs to join first, and do they accept a pre-launch site?
- How should pressure distribution (e.g. medial) influence picks, if at all?
- Should mismatched feet (different sizes) prompt a note about lacing or socks?
