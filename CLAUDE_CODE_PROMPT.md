# Build Prompt: LastFit, a running shoe recommender

> **How to use this file:** put it in the root of an empty repo named `running-shoe-recommender`, then tell Claude Code: *"Read CLAUDE_CODE_PROMPT.md and complete Phase 0."* Go one phase at a time.

> **In this repo:** this spec replaced an earlier roadmap partway through the build. The code keeps its existing `app/` layout and plain web frontend for now, and Docker is deferred. [docs/DECISIONS.md](docs/DECISIONS.md) maps each section of this spec to the code.

---

## 0. Instructions for Claude Code

You are building a full-stack product described in this file. Follow these rules:

1. **Work phase by phase** (section 9). Finish a phase only when its "Done when" checks pass. Tick the checkboxes in this file as tasks complete.
2. **Ask before** changing the stack, the data model, the ranking design, or anything in "Guardrails" (section 8).
3. **Never invent shoe data.** Where a spec is unknown, write `null` and add the shoe to `data/seed/TODO_VERIFY.md`. The owner fills these in by hand.
4. **Small commits**, one logical change each, with clear messages.
5. **Tests with every feature.** Backend: pytest. Frontend: Vitest for logic, Playwright for the main flow.
6. Keep a short `docs/DECISIONS.md` log of any non-obvious choice you make and why.
7. Secrets live only in `.env` files, never committed.

---

## 1. Product

**One line:** get scanned once at Fleet Feet, upload the scan, and get the 3 running shoes that fit your foot, with the size to order and links to buy that exact pair.

**Core principle:** recommend on **fit, comfort and the runner's own history**. Do not prescribe shoes from pronation and never make medical claims.

**Key design decision:** the **ranking is our own model**, not an LLM. The LLM is used only to (a) parse scan screenshots into structured data, (b) write explanations from the ranker's output, and (c) power a follow-up chat. The LLM never decides which shoes rank highest.

### User flow (5 screens)

1. **Upload scan:** drag-and-drop Fleet Feet / Volumental report screenshots or PDF.
2. **Confirm your feet:** show the parsed profile in the same visual language as the scan (per-foot size + width letter, band scales with LEFT arrow above and RIGHT arrow below). The user can drag arrows or edit values to correct parser mistakes, then confirms.
3. **Preferences:** one question per screen with a progress bar: weekly distance, goals, surface, preferred feel (soft / balanced / firm), budget.
4. **Shoe history:** shoes they've run in, each rated *loved / fine / hated*, with optional issue tags (toe pressure, heel slip, too narrow, too much volume, arch discomfort, too soft, too firm). **This screen is also our training-data collector**, so make it quick and pleasant.
5. **Your fit list:** 3 shoe cards, each showing:
   - fit score and a **fit meter**: the runner's foot against the shoe for width, volume, heel and length
   - "why it fits your foot": 2–3 specific reasons from the ranker's feature contributions, e.g. "toe box 4mm wider than average, matches your E-width forefoot"
   - "watch for": one honest caveat
   - size and width to order in that brand
   - up to 3 in-stock buy links with prices
   - an affiliate disclosure line
   - **Follow-up chat panel** below: "compare #1 and #2", "something under $130", "I hated the Pegasus".

After a few runs, the user rates the shoe they bought (screen reachable from the fit list), and the next recommendation improves.

---

## 2. Stack (fixed; ask before changing)

| Layer | Choice |
| --- | --- |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Framer Motion |
| Backend | Python 3.12, FastAPI, Pydantic v2, `uv` |
| Database | Postgres 16 + pgvector (`pgvector/pgvector:pg16`), SQLAlchemy + Alembic |
| Ranking (stage 1) | Our own content-based fit scorer in pure Python/NumPy |
| Ranking (stage 2) | LightGBM `LGBMRanker` (LambdaRank), enabled once enough feedback exists |
| Ranking (stage 3) | kNN over foot profiles ("similar feet liked..."), later |
| LLM framework | LangChain (`langchain`, `langchain-anthropic`) |
| LLM | Claude via `langchain-anthropic`, model id from env var |
| Embeddings | `langchain-huggingface` with `BAAI/bge-small-en-v1.5` (384 dims), swappable |
| Vector store | ChromaDB for dev prototyping, pgvector in production, behind one `get_store()` |
| RAG | Fit-note retrieval to ground explanations and chat answers |
| MCP | Official MCP Python SDK, `FastMCP` |
| Observability + evals | LangSmith |
| Infra | Docker Compose (db, api, web) |

---

## 3. Repo layout

```
running-shoe-recommender/
├── CLAUDE_CODE_PROMPT.md
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/DECISIONS.md
├── data/
│   ├── seed/
│   │   ├── shoes.csv
│   │   ├── size_charts.csv
│   │   ├── fit_notes.jsonl
│   │   ├── sample_offers_feed.csv     # clearly fake URLs on example.com
│   │   └── TODO_VERIFY.md
│   ├── sample_scans/                  # scan screenshots + expected_profile.json
│   └── chroma/                        # gitignored
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── config.py
│   │   ├── db/ (models.py, session.py, migrations/)
│   │   ├── schemas/ (foot_profile.py, preferences.py, recommendation.py, feedback.py)
│   │   ├── ingest/ (load_catalog.py, embed_fit_notes.py, load_offers.py)
│   │   ├── ranking/
│   │   │   ├── features.py            # foot × shoe feature vector
│   │   │   ├── filters.py             # hard constraints
│   │   │   ├── fit_scorer.py          # stage 1 scorer
│   │   │   ├── sizing.py              # size to order per brand
│   │   │   ├── ltr.py                 # stage 2 LightGBM ranker
│   │   │   ├── knn.py                 # stage 3 similar-feet
│   │   │   └── pipeline.py            # candidates → score → top 3
│   │   ├── retrieval/ (store.py, fit_notes.py)
│   │   ├── llm/
│   │   │   ├── scan_parser.py         # vision → FootProfile
│   │   │   ├── explainer.py           # contributions + fit notes → reasons
│   │   │   └── chat_agent.py          # follow-up chat with tools
│   │   ├── api/ (main.py, routes/)
│   │   └── mcp_server.py
│   ├── training/ (build_dataset.py, train_ltr.py)
│   ├── evals/ (datasets/, run_evals.py)
│   └── tests/
└── web/
    ├── app/
    │   ├── page.tsx                   # landing
    │   ├── scan/page.tsx              # screen 1
    │   ├── confirm/page.tsx           # screen 2
    │   ├── preferences/page.tsx       # screen 3
    │   ├── history/page.tsx           # screen 4
    │   └── results/[taskId]/page.tsx  # screen 5 + chat
    ├── components/
    │   ├── band-scale.tsx             # LEFT/RIGHT arrow scale, editable
    │   ├── width-scale.tsx            # 3A…3E
    │   ├── quiz-step.tsx
    │   ├── shoe-card.tsx
    │   ├── fit-meter.tsx
    │   └── chat-panel.tsx
    └── lib/api.ts                     # typed client generated from FastAPI OpenAPI
```

---

## 4. Data model

| Table | Columns |
| --- | --- |
| `shoes` | id, brand, model, version, category (daily, tempo, race, stability, max_cushion), drop_mm, stack_heel_mm, stack_forefoot_mm, weight_g, price_usd, widths_available (array), **toebox_width_mm**, **toebox_width_bigtoe_mm**, **forefoot_width_mm**, **heel_width_mm**, upper_volume (low/medium/high), upper_stretch (low/medium/high), heel_lock_eyelet (bool), heel_counter (soft/medium/firm), midsole_softness (soft/balanced/firm), stability_features (bool) |
| `fit_notes` | id, shoe_id, source, text, embedding vector(384) |
| `size_charts` | id, brand, us_size, length_mm_min, length_mm_max, size_offset (e.g. +0.5 if the model runs small), note |
| `offers` | id, shoe_id, retailer, us_size, width, price_usd, in_stock, affiliate_url, updated_at |
| `users` | id, created_at |
| `scans` | id, user_id, raw_file_paths, parsed_profile (JSONB), confirmed_profile (JSONB), parser_version, created_at |
| `preferences` | user_id, weekly_km, goals, surface, feel, budget_usd, updated_at |
| `shoe_history` | id, user_id, shoe_id (nullable if unknown model), raw_name, us_size, width, rating (loved/fine/hated), issues (array of tags), created_at |
| `recommendations` | id, user_id, task_status, ranker_version, candidates (JSONB with scores + contributions), result (JSONB), created_at |
| `feedback` | id, user_id, recommendation_id, shoe_id, us_size, width, outcome (loved/fine/hated), kept (bool), issues (array), notes, created_at |

Indexes: HNSW (cosine) on `fit_notes.embedding`. `offers` keyed by (shoe_id, us_size, width), which is "that exact pair".

**`shoe_history` and `feedback` are the training data** for stages 2 and 3. Keep them clean and structured (tags, not free text) from day one.

### Foot profile (scan parser output)

The Fleet Feet / Volumental report shows per-foot US size + width letter, then bands relative to the population, each as an arrow on a scale. Arrows can sit between bands, so store the nearest band and a 0–1 position. Pressure and arch flexibility come from a pressure plate that not every store has, so they're optional.

Fixture for `data/sample_scans/expected_profile.json` (a real scan):

```json
{
  "sex_scale": "men",
  "left": {
    "us_size": 8.1, "width": "E",
    "arch_height":      {"band": "low",      "position": 0.10},
    "instep_height":    {"band": "low",      "position": 0.15},
    "heel_width":       {"band": "wide",     "position": 0.75},
    "pressure":         {"band": "centered", "position": 0.50},
    "arch_flexibility": {"band": "moderate", "position": 0.50}
  },
  "right": {
    "us_size": 8.3, "width": "E",
    "arch_height":      {"band": "low",      "position": 0.40},
    "instep_height":    {"band": "low",      "position": 0.20},
    "heel_width":       {"band": "medium",   "position": 0.62},
    "pressure":         {"band": "medial",   "position": 0.15},
    "arch_flexibility": {"band": "flexible", "position": 0.35}
  }
}
```

Scales: width `3A, 2A, A, B, C, D, E, 2E, 3E` · arch height and instep height `low/medium/high` · heel width `narrow/medium/wide` · pressure `medial/centered/lateral` · arch flexibility `flexible/moderate/rigid`.

---

## 5. Ranking design (the core of the product)

### Pipeline

```
confirmed foot profile + preferences + shoe history
   → hard filters (SQL)              → ~20–40 candidates
   → feature builder (foot × shoe)
   → ranker (stage 1 now; stage 2 when enabled)
   → top 3 + per-feature contributions
   → sizing → offers
   → explainer (LLM + fit-note RAG) → Recommendation
```

### Hard filters (`filters.py`)

- category matches goals and surface (road only for the MVP)
- `price_usd <= budget` (allow +10% with a flag)
- if foot width ≥ 2E, the shoe must offer a wide version or have `toebox_width_mm` above a configurable threshold
- exclude shoes the user rated *hated*, and shoes with ≥ 2 of the same issue tag the user has reported before

### Stage 1: content-based fit scorer (`fit_scorer.py`)

A transparent weighted model. Each sub-score is in [0, 1]; the final score is a weighted sum. **Weights live in `config/scoring.yaml`**, not in code, so they can be tuned.

| Sub-score | Logic |
| --- | --- |
| `width_fit` | Map foot width letter + ball width position to a target forefoot/toe box width in mm (calibration table in config). Score by distance from target; penalize too narrow harder than too wide. If the shoe has a wide version, score the wide version. |
| `volume_fit` | Low instep → prefer `upper_volume` low/medium, `heel_lock_eyelet`, higher `upper_stretch` is neutral. High instep → penalize low-volume uppers. |
| `heel_fit` | Narrow/medium heel + wide forefoot → reward firm heel counter + heel lock eyelet (reduces slip). |
| **Combination rule** | Wide forefoot **and** low instep: the key case simple tools miss. Boost shoes with roomy toe box + lower-volume upper + heel lock; penalize "wide" versions that add volume everywhere. |
| `ride_fit` | Match `midsole_softness` to the preferred feel; match stack to goals. |
| `history_fit` | Cosine similarity of the shoe's feature vector to shoes the user loved, minus similarity to shoes they hated. Issue tags push the matching feature: "toe pressure" raises width weight, "heel slip" raises heel weight. |
| `budget_fit` | Small reward for being under budget. |

Pressure distribution and arch flexibility are **context only** in stage 1 (weight 0 by default, configurable). Do not route users to stability shoes because of medial pressure.

**Output for every candidate:** `score`, plus a dict of `contributions` (weight × sub-score per feature). The explainer and the fit meter both read from `contributions`, so explanations are always grounded in the actual ranking.

### Sizing (`sizing.py`)

- Use the **longer foot**.
- Convert foot US size to foot length, find the brand's size from `size_charts`, apply the model's `size_offset`, add a running-shoe allowance (configurable, default +0.5 size). Round to the nearest available half size.
- Return `us_size`, `width`, and a one-line rationale.

### Stage 2: learning-to-rank (`ltr.py`, `training/`)

- **Dataset (`build_dataset.py`):** each row = (user, shoe) with features = foot profile features + shoe features + stage-1 sub-scores + interaction terms. Label from `shoe_history` and `feedback`: loved = 2, fine = 1, hated = 0. Group by user.
- **Model:** LightGBM `LGBMRanker`, objective `lambdarank`.
- **Validation:** grouped cross-validation by user; metric NDCG@3 and Hit@3.
- **Gate:** only serve stage 2 when there are ≥ 300 labeled rows from ≥ 50 users **and** it beats stage 1 on held-out NDCG@3. Until then, run it in **shadow mode**: compute and log both rankings, serve stage 1.
- Explanations for stage 2 use SHAP values as `contributions`.

### Stage 3: similar feet (`knn.py`), later

- Represent each confirmed foot profile as a normalized vector.
- For a new user, find the k nearest profiles and aggregate which shoes those runners loved or hated.
- Blend into the stage-2 score as a feature. Build the module and tests now; enable it when data allows.

---

## 6. LLM components

### Scan parser (`llm/scan_parser.py`)

- Input: 1+ images or a PDF. Output: `FootProfile` via `with_structured_output`.
- Prompt explains the layout: per-foot size + width letter at the top; for each scale, the LEFT arrow is above the scale and the RIGHT arrow is below; estimate each arrow's position along the scale (0 = left end, 1 = right end).
- The result is shown on screen 2 for the user to confirm. **Only `confirmed_profile` is used for ranking.**

### Explainer (`llm/explainer.py`)

- Input: the top 3 shoes, each with its `contributions`, sizing rationale, and fit-note chunks retrieved via RAG (`retrieval/fit_notes.py`, query built from the user's top-weighted features).
- Output: `why_it_fits` (2–3 reasons), `watch_for` (1 caveat).
- **Every reason must map to a contribution or a retrieved fit note.** It must not mention any feature or claim that isn't in its input.

### Follow-up chat agent (`llm/chat_agent.py`)

LangChain tool-calling agent. Tools call the ranking pipeline; the agent never ranks on its own.

| Tool | Behavior |
| --- | --- |
| `get_profile(user_id)` | Confirmed profile, preferences, history |
| `rerank(user_id, overrides)` | Re-run the pipeline with changed constraints (budget, feel, exclude shoe) |
| `compare(shoe_a, shoe_b, user_id)` | Side-by-side contributions + specs |
| `get_fit_notes(shoe_id, question)` | RAG over fit notes |
| `get_offers(shoe_id, us_size, width)` | In-stock offers from the `offers` table |
| `record_feedback(user_id, shoe_id, outcome, issues)` | Save feedback mentioned in chat, after confirming with the user |

---

## 7. API (FastAPI)

| Endpoint | Behavior |
| --- | --- |
| `POST /users` | Create user |
| `POST /users/{id}/scans` | Upload files; run parser; return parsed profile |
| `PUT /users/{id}/scans/{scan_id}/confirm` | Save confirmed (possibly edited) profile |
| `PUT /users/{id}/preferences` | Save preferences |
| `POST /users/{id}/history` | Add shoe history entries |
| `GET /shoes/search?q=` | Autocomplete for the history screen |
| `POST /users/{id}/recommend` | Start pipeline + explainer as a background task; return `task_id` |
| `GET /tasks/{task_id}` | Status + `Recommendation` result |
| `POST /users/{id}/chat` | Follow-up chat, streamed (SSE) |
| `POST /users/{id}/feedback` | Outcome for a recommended shoe |
| `GET /health` | Health check |

Generate a typed TypeScript client for `web/lib/api.ts` from the OpenAPI schema.

---

## 8. Guardrails (do not violate)

1. **The LLM never ranks.** Ranking comes only from `ranking/`.
2. **Links come only from the `offers` table.** The LLM never writes or edits a URL. Post-process every response: any URL not in `offers` is removed and the run is flagged in logs.
3. **Explanations are grounded:** every reason traces to a contribution or a retrieved fit note.
4. **No medical claims.** Never say a shoe prevents, treats or diagnoses injury.
5. **No scraping** review or lab sites (e.g. RunRepeat). Specs are entered by hand or come from affiliate feeds and brand pages used within their terms.
6. **Affiliate disclosure** on every screen and response that shows buy links.
7. **No copied branding.** The confirm screen uses the same *kind* of band-scale visualization as the scan, but with our own design, colors and no Fleet Feet / Volumental logos.
8. **Third-party UI code:** check the license of any component before copying it (e.g. 21st.dev components may not be MIT). Log the check in `docs/DECISIONS.md`.

---

## 9. Phases

### Phase 0: Setup
- [ ] Monorepo with `backend/` and `web/`; Docker Compose for db, api, web
- [x] Postgres with the `vector` extension enabled; Alembic migration for all tables in section 4
- [ ] FastAPI skeleton with `/health`; Next.js skeleton with shadcn/ui and Tailwind
- [ ] LangSmith tracing on; a test trace appears
- [ ] CI: ruff + pytest + typecheck + Vitest

**Done when:** `docker compose up` serves the API and web app, migrations run, and all checks pass.

### Phase 1: Catalog
- [x] `shoes.csv` with 20 popular road shoes (expand to 40–60 later), including several with wide versions; unknown values `null` and listed in `TODO_VERIFY.md`
- [x] `size_charts.csv` for each brand; `fit_notes.jsonl` with 3–6 notes per shoe and a `source` field
- [x] Idempotent `load_catalog.py`; a validation script reporting missing fields

**Done when:** catalog loads cleanly and the validation report is generated.

### Phase 2: Fit-note retrieval (Chroma, then pgvector)
- [x] Chunk (500 chars, 50 overlap), embed, store in Chroma; `get_store()` switches by `VECTOR_BACKEND`
- [x] pgvector implementation of the same interface
- [x] Script running 10 sample queries on both backends

**Done when:** both backends return sensible fit notes and retrievals show in LangSmith.

### Phase 3: Stage 1 ranker and sizing
- [x] `features.py`, `filters.py`, `fit_scorer.py`, `sizing.py`, `pipeline.py`, `config/scoring.yaml`
- [x] Unit tests for each sub-score, including the **wide forefoot + low instep** case using the fixture profile
- [x] A CLI: `python -m app.ranking.pipeline --profile data/sample_scans/expected_profile.json` prints the top 3 with contributions and sizes

**Done when:** tests pass and the CLI output is sensible for the fixture and 5 hand-written profiles.

### Phase 4: Scan parser
- [ ] `FootProfile` schema; parser with structured output; saves to `scans`
- [ ] Test against `data/sample_scans/` with `expected_profile.json`

**Done when:** sizes and width letters exact, bands correct, positions within ±0.15.

### Phase 5: Explainer and API
- [ ] Explainer with fit-note RAG; grounding check (every reason maps to an input)
- [ ] All endpoints in section 7; background task for `/recommend`
- [x] Integration test: upload → confirm → preferences → history → recommend → result

**Done when:** the integration test passes and `/docs` lists every endpoint.

### Phase 6: Frontend
Design references to study (borrow ideas, not code or branding):
- **Brooks Shoe Finder:** one question per screen, progress bar, start screen
- **Rundida Shoe Match:** honest, minimal results page with 3 picks
- **RunRepeat catalog:** showing measured specs next to category averages
- **Volumental "fit list":** results as a ranked list personalized to foot shape
- **vercel/chatbot** repo: chat panel patterns and streaming UI
- **21st.dev Product Finder Quiz:** multi-step quiz → best match with reasons (check license first)

Tasks:
- [x] Screens 1–5 per section 1, mobile-first, with Framer Motion transitions
- [x] `band-scale.tsx` and `width-scale.tsx`: show LEFT/RIGHT arrows, draggable for corrections
- [x] `shoe-card.tsx` + `fit-meter.tsx` driven by `contributions`
- [x] `chat-panel.tsx` streaming from `/chat`
- [ ] Playwright test of the full flow with the sample scan

**Done when:** the Playwright test passes on mobile and desktop viewports.

### Phase 7: Offers
- [x] `load_offers.py` for a product feed (CSV/XML); matching report for unmatched products
- [x] Sample feed with `example.com` URLs until a real affiliate feed exists
- [x] Offers older than 48h excluded; link post-processing guard (Guardrail 2)

**Done when:** results show offers from the feed and the guard test passes.

### Phase 8: Chat agent
- [x] Tools in section 6; agent uses only tools to rank or fetch offers
- [ ] Tests: "cheaper", "exclude X", "compare #1 and #2" produce correct tool calls

**Done when:** tests pass and traces in LangSmith show tool usage.

### Phase 9: Feedback loop and stage 2 ranker
- [ ] Feedback screen and `record_feedback` flow
- [ ] `build_dataset.py` and `train_ltr.py` with grouped CV, NDCG@3, Hit@3
- [ ] Shadow mode: log stage 1 and stage 2 rankings side by side; serve stage 2 only past the gate in section 5
- [ ] SHAP-based contributions for stage 2
- [ ] Synthetic-data test proving the training pipeline runs end to end (clearly marked synthetic, never used for serving)

**Done when:** training runs end to end on synthetic data and shadow logging works.

### Phase 10: Similar-feet module (stage 3)
- [ ] `knn.py` with tests; disabled by config until enough real data exists

**Done when:** tests pass and the module can be enabled by a config flag.

### Phase 11: MCP server
- [x] `mcp_server.py` (FastMCP) exposing `find_shoes`, `fit_check`, `get_offers`, reusing the pipeline
- [x] README section on adding it to Claude Desktop

**Done when:** Claude Desktop can call all three tools.

### Phase 12: Evals (LangSmith)
- [x] Datasets in `evals/datasets/`: ~20 profiles with expert-picked shoes (template; owner supplies picks)
- [x] Evaluators: Hit@3 vs expert picks, size within half a size, parser accuracy, explanation grounding, link validity (must be 100%)
- [ ] One command runs all evals as a LangSmith experiment; results table in the README

**Done when:** evals run from one command and results appear in LangSmith.

---

## 10. Out of scope (MVP)

Gait video or custom computer vision · trail, spike and walking shoes · accounts beyond a user id · payments · native mobile app.

## 11. Open questions (ask the owner; don't decide)

- Calibration table for width letter → target toe box width in mm
- Default weights in `scoring.yaml` (start with a sensible guess and log it in `DECISIONS.md`)
- Which affiliate programs to join first
- Whether pressure distribution should ever carry weight in scoring
- Whether mismatched foot sizes should trigger a lacing or sock tip
