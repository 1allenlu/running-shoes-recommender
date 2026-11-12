# Decisions

Short log of non-obvious choices. Newest first.

## 2026-11-12: Next.js frontend and chat

- **Static export, one port.** `web/` builds to `web/out` (`output: "export"`), and FastAPI
  serves it on :8001 next to the API (the owner uses :8000 for something else). No Node server
  in production; `npm run dev` on :3000 is for frontend work and calls the API via CORS.
- **`/results/?task=<id>`** instead of `results/[taskId]`: a static export can't pre-render
  unknown task ids.
- **Borrowed patterns, not code**, from the references: one-question quiz with per-step Zod
  validation (9d8dev/slider), dropzone with progress (sadmann7/file-uploader,
  shadcn-dropzone), product-card layout (vercel/commerce), shadcn charts for the fit meter,
  and the chat panel (vercel/chatbot) streaming from our own endpoint. No code was copied, so
  their licenses don't apply.
- **shadcn's current style uses Base UI** (not Radix) and the `cn` package (shadcn's own,
  `github.com/shadcn-ui/cn`, no install scripts).
- **Typed client**: `web/lib/api-types.ts` is generated from FastAPI's OpenAPI
  (`npm run gen:api`).
- **Chat is stateless**: the client sends the conversation; tools are bound to the user and
  call the pipeline (`rerank` returns a full `Recommendation`, streamed as a `picks` event so
  the panel draws shoe cards). `rerank` never saves; `record_feedback` is told to confirm first.
- **Fit meter** draws the ranker's per-factor sub-scores (`Pick.breakdown`). Unverified specs
  are striped and labelled; they count as 0.5 in the score.

## 2026-11-11: Removed the LLM-ranking agent

The first build (from the old roadmap) had an LLM agent choose the shoes, which breaks
Guardrail 1. Removed: `app/agent/` (agent, its tools, the LLM feedback-constraint chain and
`pick_size`), `app/retrieval/hybrid.py` (the agent's search), the questionnaire schema, the
agent's eval dataset and tests, and `ROADMAP.md`. In their place:

- `/recommend`, the MCP tools and the evals all run `app/ranking/` through `app/recommend.py`.
- Until the LLM explainer exists (Phase 5), reasons and caveats are the ranker's own sub-score
  notes plus a few fixed lines (`FALLBACK_LINES`), so they are grounded by construction. The
  `grounding` eval checks this and will keep checking once the LLM writes them.
- Feedback on a pick is fed to the ranker like shoe history (loved/fine/hated + issue tags)
  instead of being turned into constraints by an LLM.
- Manual entry (`POST /users/{id}/scans/manual`) saves a scan with no files that is already
  confirmed, so "only `confirmed_profile` is used for ranking" holds for both paths.
- `PUT /users/{id}/history` (replace) sits next to the spec's `POST` (append): the history
  screen sends the whole list each time.

## 2026-11-11: Adopting the LastFit spec

The spec moved to [CLAUDE_CODE_PROMPT.md](../CLAUDE_CODE_PROMPT.md). We are **adapting the
existing code**, not restarting:

| LastFit spec | In this repo | Status |
| --- | --- | --- |
| `backend/` + `web/` monorepo | `app/` (backend) at the repo root, `web/` (Next.js) | Backend not moved yet |
| Docker Compose | Local Homebrew Postgres 17 + pgvector | Deferred (owner's call) |
| Next.js + shadcn + Framer Motion | `web/`, static export served by FastAPI on :8001 | Built (Phase 6) |
| `ranking/` (stage 1) | `app/ranking/` + `config/scoring.yaml` | Built |
| `llm/scan_parser.py` | `app/parsing/scan_parser.py` | Exists; needs a real scan to test |
| `llm/explainer.py` | Sub-score notes in `app/recommend.py` | LLM rephrasing + fit-note RAG is Phase 5 |
| `llm/chat_agent.py`, `POST /chat` | `app/chat_agent.py`, `POST /users/{id}/chat` (SSE) | Built; needs an LLM key for a live check |
| `retrieval/` (store, fit_notes) | `app/retrieval/` (+ `offers.py` for links and the guard) | Done |
| `ingest/` | `app/ingest/` | Done; `TODO_VERIFY.md` generated |
| `mcp_server.py` | `app/mcp_server.py` on the pipeline | Done; needs a Claude Desktop check |
| Section 4 tables | Migrations 0002 and 0003 | Done (`tasks` became `recommendations`) |

## 2026-11-11: Stage 1 ranker details

- **`heel_lock` is `heel_lock_eyelet`.** The column already existed with that meaning; we
  kept the name instead of renaming it across the code, tests and seed data.
- **`toe_box` (narrow/medium/roomy) is kept** alongside `toebox_width_mm`. It is the fallback
  for `width_fit` when the mm measurement is null, which is the case for every shoe today.
- **Filters run in Python, not SQL.** The catalog is tens of shoes; Python filters give every
  exclusion a readable reason and run the same from the DB or the seed CSV.
- **Score is normalized:** `sum(weight x sub-score) / sum(weights that apply)`. Sub-scores
  that don't apply to this runner (`n/a`: no budget, no history, not the combo case) are left
  out for every shoe, so they never change the order, and the score stays 0-1 for the card.
- **Unknown specs score 0.5** (`unknown_score`) and are marked `unknown`, so the explainer
  can't claim anything about them. Ties go to the shoe with more verified specs.
- **"Hated" excludes every version** of that brand + model ("I hated the Pegasus").
- **"≥ 2 of the same issue tag"** is read as: an issue the runner reported on two or more
  shoes. It excludes shoes whose *known* specs cause that issue (table in
  `filters.recurring_issue_excludes`); unknown specs never exclude.
- **Combination rule penalty:** a shoe whose toe room comes only from its wide version (toe
  box not roomy, no mm data) and whose upper isn't low-volume gets `combo_fit x 0.6`; a
  high-volume upper gets `combo_fit = 0`. This is our reading of "wide versions that add
  volume everywhere", since we have no per-width specs.
- **Wide forefoot** means the width letter maps to a wide shoe on that scale (men's E+,
  women's C+). The hard filter uses the spec's 2E threshold separately.
- **Two feet, one band:** when left and right bands differ, we use the band of the mean
  position (the fixture's heel: wide 0.75 + medium 0.62 -> wide).
- **Sizing adds +0.5 on top of the brand chart**, as the spec says. Owner should confirm the
  brand charts we enter map foot length to *street* size, or this double-counts the room.
- **Pressure and arch flexibility aren't scored at all** (not even at weight 0), and a test
  checks medial pressure never changes the order.

## Open questions for the owner

Starting guesses are in `config/scoring.yaml`, marked as placeholders:

- Width letter -> target toe box mm (`width.target_toebox_mm`), and `wide_toebox_min_mm`.
- Default weights (`weights`), issue boosts, and the per-band volume and heel tables.
- Whether pressure distribution should ever carry weight.
- Whether mismatched foot sizes should trigger a lacing or sock tip.
- Which affiliate programs to join first.
