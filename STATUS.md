# Project Status

Local-first multimodal ad-classification pipeline. Windows-friendly, no Docker, all infrastructure local. Single SQLite file for metadata + vectors + FTS5. LM Studio for Gemma. Custom frontend planned (not yet started).

This document is the handoff. New sessions / models can pick up at the next unchecked item. The `Spec` column points to the section in [Prompt.md](Prompt.md) that governs the work; [AGENTS.md](AGENTS.md) holds the high-level architectural contract.

---

## Phase 1 — Specification

| | Item | Spec | Notes |
|---|---|---|---|
| [x] | Architecture defined | AGENTS.md | local-first, no Docker, no cloud |
| [x] | Pipeline cascade specified | Prompt.md A0–J | ingest → dedup → manifest → preprocess → OCR → VL → align → rules → bundle → VLM → aggregate |
| [x] | Marketing entity extraction | Prompt.md K | brand, products, prices, offers, CTAs, social proof, disclaimers, creative format |
| [x] | Embeddings + vector store | Prompt.md L | sentence-transformers (text), **SigLIP 2** (visual), `VectorStore` protocol, sqlite-vec default |
| [x] | SQLite schema | Prompt.md M | ads, frames, ocr_items, transcript_segments, rule_triggers, classifications, marketing_entities, jobs, campaigns, ad_campaigns, agent_sessions, agent_messages, ads_fts |
| [x] | HTTP API contract | Prompt.md N | FastAPI endpoints + SSE |
| [x] | Job orchestration | Prompt.md O | SQLite jobs table + worker + state machine |
| [x] | Storage layout | Prompt.md P | predictable paths under `data/` |
| [x] | Category taxonomy | Prompt.md Q | 15 categories + 10 risk labels in `taxonomy.yaml` |
| [x] | CLI surface | Prompt.md R | every stage runnable from terminal |
| [x] | AMD/ROCm diagnostic | Prompt.md S | best-effort GPU helper |
| [x] | Config sample | Prompt.md T | one `config.yaml` covers everything |
| [x] | Documentation outline | Prompt.md U | README must cover Datasette, agent, campaigns |
| [x] | Test coverage list | Prompt.md V | what to test, with mocks for heavy models |
| [x] | Acceptance criteria | Prompt.md W | end-to-end pass conditions |
| [x] | Campaigns | Prompt.md X | auto-discovery + manual curation |
| [x] | Hybrid search | Prompt.md Y | FTS5 + sqlite-vec + RRF (no Redis) |
| [x] | NL Query Agent | Prompt.md Z | tool-calling Gemma, read-only DB, audit trail |
| [x] | Dedup / similar-ad detection | Prompt.md A1 | file hash, phash, vector similarity |
| [x] | `compare_ads` tool + verdicts | Prompt.md Z, J | quantitative + qualitative pairwise comparison |
| [x] | Gemma verifier prompt template | Prompt.md (bottom) | full JSON schema with marketing entities |

**Phase 1 status: complete.** All architectural decisions locked.

---

## Phase 2 — Project scaffolding

**Phase 2 status: complete.**

**Code organization rules (apply throughout)**: no megafiles (~400 line soft cap), one responsibility per module, lazy-import heavy deps, tests mirror source layout. See `Code Organization` section at the top of Prompt.md for the suggested package tree.

| | Item | Notes |
|---|---|---|
| [x] | **Verify pre-installed GPU torch BEFORE any pip install** | torch 2.9.1+rocm7.2.1, GPU=True confirmed |
| [x] | Create Python 3.11+ package structure | full tree created per Prompt.md Code Organization |
| [x] | `pyproject.toml` with dependencies | torch NOT listed; transformers pinned to 4.57.6 + tokenizers 0.22.1 (ROCm wheel smoke-tested) |
| [x] | `ad_classifier/diagnostics/env.py` startup check | prints version + backend, fails loudly if CPU-only |
| [x] | Re-verify torch is GPU-capable after `pip install -e .` | confirmed GPU=True after install |
| [x] | `ruff` + `black` config | configured in `pyproject.toml` |
| [x] | `pytest` config | `[tool.pytest.ini_options]` in `pyproject.toml` |
| [x] | `.gitignore` | ignores `data/`, `*.db`, model caches, `.venv/` |
| [x] | `README.md` skeleton | all sections from Prompt.md U |
| [x] | Initial `config.yaml` from Prompt.md T | committed as `config.example.yaml` |
| [x] | `taxonomy.yaml` from Prompt.md Q | 15 categories + 10 risk labels |
| [x] | `prompts/gemma_ad_verifier.txt` | from Prompt.md bottom; version header included |
| [x] | `prompts/gemma_agent_system.txt` | from Prompt.md Z.4 |

**Dependencies to add (`pyproject.toml`):**

> **⚠️ DO NOT include `torch`, `torchvision`, or `torchaudio` in `pyproject.toml`.**
> The `.venv` already has a manually-installed GPU-accelerated PyTorch build (DirectML or ROCm-Windows wheels for the 7900 XT). Listing torch as a dependency will cause `pip install -e .` to silently swap it for the CPU wheel. When installing torch-dependent packages, use `pip install --no-deps <pkg>` or rely on pip's default `only-if-needed` upgrade strategy. Never run `pip install -U torch`.

Core: `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2` or `sqlmodel`, `pyyaml`, `typer` or `click`, `httpx`, `fastapi`, `uvicorn[standard]`, `python-multipart`, `sse-starlette`, `structlog`.

Pipeline: `pillow`, `imagehash`, `opencv-python-headless`, `numpy`, `ffmpeg-python` (or shell out).

Whisper: `whisper.cpp` via Vulkan is the default Windows AMD path. Smoke-tested on RX 7900 XT with `GGML_VULKAN=ON`, `Vulkan0`, `ggml-tiny.en.bin`, and `samples/jfk.wav`. Runtime files are copied locally to `tools/whisper.cpp/`; the default model is at `models/whisper/ggml-tiny.en.bin`. Both paths are ignored by Git. `faster-whisper` remains the Python fallback.

OCR: `paddleocr` (lazy-imported), `paddlepaddle` (CPU wheel — Windows AMD GPU not supported by Paddle).

Embeddings (torch-based, install with `--no-deps` to preserve pre-installed torch): `sentence-transformers`, `transformers`.

Vectors: `sqlite-vec`, optional `qdrant-client`.

NL agent: `openai` (LM Studio is OpenAI-compatible) or just `httpx`.

Test: `pytest`, `pytest-asyncio`, `httpx` (TestClient).

Dev: `ruff`, `black`, `mypy` (optional), `datasette` (recommended).

**Actual install order used (Windows + 7900 XT ROCm build):**

```bash
# 1. Verify the pre-installed torch is intact and GPU-capable
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
# → torch 2.9.1+rocm7.2.1  True

# 2. Install all non-torch deps
pip install -e .

# 3. Install sentence-transformers + transformers without touching torch
#    This SigLIP 2-capable stack was smoke-tested against torch 2.9.1+rocm7.2.1.
pip install --no-deps "transformers==4.57.6" "tokenizers==0.22.1" "sentence-transformers==3.0.1"

# 4. Install whisper + dev extras
pip install faster-whisper
pip install -e ".[dev,clustering]"

# 5. Re-verify torch is still GPU-capable
python -c "import torch; print(torch.cuda.is_available())"
# → True
```

---

## Phase 3 — Core data + persistence

**Phase 3 status: complete.** Core models, initial SQLite schema, WAL setup, sqlite-vec load check, `init-db`, read-only DB enforcement, and all aggregate repositories implemented.

| | Item | Spec |
|---|---|---|
| [x] | Pydantic models — pipeline core | Prompt.md A |
| [x] | Pydantic models — marketing entities | Prompt.md K |
| [x] | Pydantic models — vector store + similarity | Prompt.md L, A1, J |
| [x] | Pydantic models — campaigns + agent | Prompt.md X, Z |
| [x] | SQLite schema migration (numbered SQL) | Prompt.md M |
| [x] | WAL pragma on connection open | Prompt.md M |
| [x] | sqlite-vec extension load + self-test | Prompt.md L.6 |
| [x] | FTS5 virtual table init + maintenance | Prompt.md M, Y |
| [x] | Repository classes — AdRepository, JobRepository, ClassificationRepository, MarketingEntityRepository | Prompt.md M |
| [x] | `init-db` CLI command | Prompt.md M, R |
| [x] | Path helpers in `paths.py` | Prompt.md P |
| [x] | Tests: schema migrations, classification + marketing entity round-trip | Prompt.md V |

---

## Phase 4 — Pipeline stages (no AI yet, mocks first)

**Phase 4 status: complete.** All pipeline stages implemented: ingest (A0), dedup (A1), manifest (B), frame preprocessing (C), OCR interface + PaddleOCREngine (D), PaddleOCR-VL adapter + gating (E), transcript alignment (F), rules engine + default_rules.yaml (G), evidence bundle builder with H.1 frame selection (H). All stages tested with mocks; 66 tests pass without GPU or LM Studio.

| | Item | Spec |
|---|---|---|
| [x] | A0 Ingest: ffmpeg frame extraction | Prompt.md A0 |
| [x] | A0 Ingest: ffmpeg audio extraction | Prompt.md A0 |
| [x] | A0 Ingest: Whisper backend interface + mock | Prompt.md A0, F |
| [x] | A0 Ingest: faster-whisper implementation | Prompt.md A0 |
| [x] | A0 Ingest: whisper.cpp CLI implementation (`GGML_VULKAN` on Windows AMD) | Prompt.md A0 |
| [x] | A0 Ingest: progress events for SSE | Prompt.md A0, O |
| [x] | A1 Dedup: SHA256 of source file | Prompt.md A1 |
| [x] | A1 Dedup: phash mean across keyframes | Prompt.md A1 |
| [x] | A1 Dedup: short-circuit logic | Prompt.md A1.2 |
| [x] | B Manifest builder | Prompt.md B |
| [x] | C Frame preprocessing (blur, blank, phash dedup, scene change, keyframes) | Prompt.md C |
| [x] | D OCR engine interface + Mock + PaddleOCR (CPU) | Prompt.md D |
| [x] | E PaddleOCR-VL adapter + gating | Prompt.md E |
| [x] | F Whisper transcript loaders + alignment | Prompt.md F |
| [x] | G Rules engine + sample rules YAML | Prompt.md G |
| [x] | H Evidence bundle builder | Prompt.md H |
| [x] | Tests: each stage with mocks + synthetic fixtures | Prompt.md V |

---

## Phase 5 — VLM + classification

**Phase 5 status: complete.** VLM interface + HTTP verifier, aggregation policy, brand normalization, ClassificationRepository, MarketingEntityRepository, and projection write-back are all implemented. 40 new tests pass (130 total). LM Studio smoke test pending — user will signal when ready.

Model: `google/gemma-4-26b-a4b` (configured in `VLMEndpointConfig`).

| | Item | Spec |
|---|---|---|
| [x] | `VLMVerifier` interface + `MockVLMVerifier` | Prompt.md I |
| [x] | `HTTPVLMVerifier` (OpenAI-compatible, image_url base64) | Prompt.md I |
| [x] | Configurable retry + timeout | Prompt.md I |
| [x] | Render Gemma verifier prompt with taxonomy at startup | Prompt.md I, Q |
| [x] | VLM JSON validation + fallback to `review` on parse failure | Prompt.md I |
| [x] | `VLMEndpointConfig` in `AppConfig.vlm.endpoint` | Prompt.md I |
| [x] | J Aggregation + decision policy + sensitive thresholds | Prompt.md J |
| [x] | K Marketing entity persistence — `MarketingEntityRepository` | Prompt.md K, M |
| [x] | `ClassificationRepository` (upsert/get/delete) | Prompt.md M |
| [x] | Brand normalization (`brand_normalize`, alias YAML) | Prompt.md K |
| [x] | `FinalAdClassification` + `RelatedAds` + `SimilarAd` models | Prompt.md J |
| [x] | Tests: VLM prompt rendering, mock/HTTP verifier, parse_failure, aggregation decision matrix, brand normalization, classification + marketing repo round-trip | Prompt.md V |
| [ ] | LM Studio smoke test (google/gemma-4-26b-a4b) | Prompt.md U |

---

## Phase 6 — Embeddings + search

**Phase 6 status: complete.** Text + image embedder interfaces with mocks, `SentenceTransformerEmbedder`, `SigLIP2ImageEmbedder`, `SqliteVecStore` (sqlite-vec, delete-then-insert upsert), FTS5 helpers, RRF fusion, hybrid search, A1.3 similar-ad enrichment, and `bench-vectors` CLI implemented. 40 new tests pass (170 total). Qdrant skipped per user request.

| | Item | Spec |
|---|---|---|
| [x] | `TextEmbedder` interface + `MockTextEmbedder` | Prompt.md L |
| [x] | `SentenceTransformerEmbedder` (lazy import) | Prompt.md L |
| [x] | `ImageEmbedder` interface + `MockImageEmbedder` | Prompt.md L |
| [x] | `SigLIP2ImageEmbedder` (HuggingFace transformers, lazy import) | Prompt.md L |
| [x] | `VectorStore` protocol + `SqliteVecStore` (sqlite-vec) | Prompt.md L |
| [~] | Optional: `QdrantStore` — skipped per user request | Prompt.md L |
| [x] | Y Hybrid search: FTS5 + vec + RRF fusion (`search/` package) | Prompt.md Y |
| [x] | A1.3 post-embedding similar-ad enrichment (`dedup/similarity.py`) | Prompt.md A1 |
| [x] | `bench-vectors` CLI command | Prompt.md L.4 |
| [x] | `TextEmbedderConfig`, `ImageEmbedderConfig`, `VectorStoreConfig` in `AppConfig` | Prompt.md L |
| [x] | Tests: mock embedders, SqliteVecStore CRUD + KNN, RRF correctness, hybrid search, similarity enrichment | Prompt.md V |

---

## Phase 7 — Campaigns

**Phase 7 status: core discovery complete.** Auto-discovery, fallback clustering,
campaign/ad-assignment repositories, CLI, and tests are implemented. HTTP campaign
endpoints remain deferred to Phase 8 where the FastAPI app skeleton is introduced.

| | Item | Spec |
|---|---|---|
| [x] | Brand normalization helper (`"JEEP"` / `"Jeep"` → `"jeep"`) | Prompt.md (implemented in Phase 5, `ad_classifier/marketing/brand.py`) |
| [x] | X.2 Auto-discovery: HDBSCAN over `ads_visual` per brand | Prompt.md X.2 |
| [x] | X.2 Fallback agglomerative clusterer | Prompt.md X.2 |
| [~] | X.3 Manual CRUD + assignment endpoints | Prompt.md X.3, X.4; repository CRUD + assignments done, HTTP endpoints deferred to Phase 8 |
| [x] | `campaigns discover` and `campaigns list` CLI | Prompt.md R |
| [x] | Tests: synthetic clusters, user vs auto precedence, cascade on ad delete | Prompt.md V |

---

## Phase 8 — HTTP API + worker

**Phase 8 status: complete for backend orchestration.** FastAPI app factory,
upload/job/ad/search/campaign routes, SSE job events, static `data/` serving,
and the SQLite-backed single-worker poll loop are implemented. The worker wires
the existing local stages end to end and supports injected mocks for tests.

| | Item | Spec |
|---|---|---|
| [x] | FastAPI app skeleton + CORS + OpenAPI at `/docs` | Prompt.md N |
| [x] | Upload endpoint (streaming, MIME whitelist, ffprobe sanity) | Prompt.md N |
| [x] | Ad list/detail/frames/evidence/similar endpoints | Prompt.md N |
| [x] | Ad update endpoint for curated field corrections (`PATCH /api/ads/{ad_id}`) | Prompt.md N |
| [x] | Ad delete endpoint with cascade + optional local artifact cleanup (`DELETE /api/ads/{ad_id}`) | Prompt.md N, P |
| [x] | Search endpoint (text/visual/hybrid) | Prompt.md N, Y |
| [x] | Job status + SSE events + cancel | Prompt.md N, O |
| [x] | Static file mount for `data/` | Prompt.md N, P |
| [x] | Worker process: poll loop + state machine + cancellation | Prompt.md O |
| [x] | Single-worker concurrency to protect VRAM | Prompt.md O |
| [x] | Campaign endpoints | Prompt.md X.4 |
| [x] | Tests: TestClient flows, SSE ordering, worker state transitions | Prompt.md V |

---

## Phase 9 — NL Agent

**Phase 9 status: complete.** Tool catalog (10 tools), read-only DB enforcement,
live-schema renderer, full agent loop with conversation persistence, LM Studio
HTTP client with `tools` param + retry, malformed-call fallback, FastAPI agent
routes (sessions / query / SSE events / tools / schema), and the four CLI
subcommands are all implemented. 46 new tests pass (251 total). LM Studio
smoke test still pending — runs against a real Gemma instance.

| | Item | Spec |
|---|---|---|
| [x] | Tool catalog implementations (list_ads, count_ads, get_ad, get_campaign, list_campaigns, aggregate, hybrid_search, vector_similarity, sql_readonly, compare_ads) | Prompt.md Z.1 |
| [x] | `compare_ads` tool: vector cosine + structured diff + verdict | Prompt.md Z.1, J |
| [x] | Read-only DB connection (`query_only=ON`) | Prompt.md Z.3 |
| [x] | Schema summary auto-rendered from live DB at startup | Prompt.md Z.4 |
| [x] | Agent loop: user → tool_call → tool_result → final | Prompt.md Z.2 |
| [x] | LM Studio integration with `tools` parameter | Prompt.md Z.8 |
| [x] | Malformed tool-call retry + fallback | Prompt.md Z.8 |
| [x] | Conversation persistence in `agent_sessions` / `agent_messages` | Prompt.md Z.2 |
| [x] | Agent endpoints + SSE event types | Prompt.md Z.5 |
| [x] | `agent ask` / `agent repl` / `agent show-tools` / `agent show-schema` CLI | Prompt.md Z.6 |
| [x] | Tests: each tool isolated, full loop with mock LM Studio, read-only enforcement, truncation reporting, SSE event ordering | Prompt.md Z.7 |
| [ ] | LM Studio smoke test (google/gemma-4-26b-a4b agent loop) | Prompt.md Z.8 |

---

## Phase 10 — Polish + delivery

**Phase 10 status: delivery polish is in place.** The VLM payload debug and the
agent-backed end-to-end acceptance path remain deferred by request; the real MP4
worker run reaches the VLM stage and currently receives HTTP 400 from LM Studio.

| | Item | Spec |
|---|---|---|
| [x] | S AMD/ROCm diagnostic helper | Prompt.md S; `ad-classifier paddle-rocm-check` |
| [x] | README full content (architecture, install, examples, agent, campaigns, Datasette) | Prompt.md U |
| [x] | Sample mp4 + expected-output JSON committed to `samples/` | Prompt.md U, W |
| [~] | End-to-end smoke test: ingest → classify → API → agent question | Prompt.md W; real MP4 worker run completed through persistence, VLM returned HTTP 400, agent backend is Phase 9 |
| [~] | All Prompt.md W acceptance criteria pass | Prompt.md W; backend tests/build pass, VLM real-call debug and agent backend pending |
| [ ] | Run Follow-Up review prompt and patch findings | Prompt.md (Follow-Up) |
| [x] | `start.bat` launching API + worker (+ frontend) | Prompt.md U |

---

## Phase 11 — Frontend management UI

Separate Vite + React + TypeScript + Tailwind + shadcn/ui app. It must consume the FastAPI OpenAPI surface only; no backend imports and no direct SQLite access.

**Phase 11 status: initial management UI complete.** The app lives in
`frontend/`, builds with Vite, includes a generated OpenAPI client snapshot, and
uses one API wrapper for JSON/SSE calls. The Agent page is ready for Phase 9
endpoints and displays a graceful not-implemented state until those routes exist.

| | Item | Spec |
|---|---|---|
| [x] | Generate typed API client from `/openapi.json` | Prompt.md U; generated into `frontend/src/lib/api/generated` |
| [x] | All Ads page with paginated table, search, filters, sort, and status/category chips | Prompt.md N, frontend; decision UI intentionally omitted |
| [x] | Ad detail drawer/page with frames, evidence, classification, marketing entities, campaigns, and related ads | Prompt.md N |
| [x] | Edit curated fields from UI: brand, products, category | Prompt.md N; limited to current backend `PATCH /api/ads/{ad_id}` fields |
| [x] | Delete ad record flow with confirmation and cascade warning | Prompt.md N, P |
| [x] | Upload page with job progress via SSE | Prompt.md N, O |
| [x] | Search page using keyword/vector/hybrid API modes | Prompt.md Y |
| [x] | Campaign management page for discovery/listing | Prompt.md X.4 |
| [~] | Tests: API client mocks, All Ads filtering/edit/delete flows, responsive table/detail states | frontend; `npm run build` passes, automated UI tests not added yet |

---

## Frontend (separate, by user)

Built independently from this spec. Talks to the FastAPI surface only.

**Recommended stack** (chosen for AI-assisted development productivity + demo polish):

```
Vite + React + TypeScript
+ Tailwind CSS
+ shadcn/ui            (Radix primitives + Tailwind tokens)
+ TanStack Query       (data fetching + cache for /api/*)
+ @microsoft/fetch-event-source  (SSE client for jobs + agent streaming)
```

Reasoning: Tailwind + shadcn is the combination AI design assistants generate cleanest, most-consistent UI in. Vite gives instant HMR with no SSR overhead. React has the most training data for AI tooling. TypeScript types can be auto-generated from FastAPI's OpenAPI spec via `openapi-typescript-codegen` so the API/frontend boundary stays type-safe.

Setup: `pnpm create vite@latest` → `pnpm dlx shadcn@latest init` → done.

Avoid: Bootstrap (looks dated), MUI (Material look is polarizing, harder to theme), CRA/Webpack (slower than Vite), plain CSS (AI consistency drifts).

Suggested panels:

- **Upload + classification panel** — `POST /api/ads/upload`, then SSE on `/api/jobs/{job_id}/events` for progress (frame extraction → OCR → VLM stages)
- **All Ads management page** — `/api/ads/*`; uses shadcn Table + DataTable patterns for pagination, search, filters, sort, edit curated fields, and delete records
- **Similarity panel** — `/api/ads/{id}/similar`; cards with cosine score badges per modality, verdict label, structured field-diff list
- **Campaigns view** — `/api/campaigns/*`; auto-discovery proposals + manual curate
- **Agent chat panel** — `/api/agent/sessions/{id}/query` with SSE; render tool-call cards inline (collapsible) so users see *how* the agent answered

Datasette runs alongside as a dev-time DB inspector: `datasette serve ad_classifier.db -o` — opens the full DB in a browser tab, useful during development and as a "raw data" view during demos.

---

## Open architectural decisions (none currently)

All major decisions locked as of this snapshot. If a new question comes up:

- Vector backend: **sqlite-vec** (default), Qdrant native binary as scale path. Decided.
- Vector models: **sentence-transformers MiniLM** for text, **SigLIP 2 base** for images. Decided.
- Hybrid search: **FTS5 + sqlite-vec + Python RRF**, no Redis. Decided.
- LM Studio: default port `1234`, Gemma 3 12B with vision. Decided.
- PaddleOCR device: **CPU**, AMD GPU as best-effort diagnostic. Decided.
- DB: **SQLite WAL** (not Postgres). Decided.
- Agent: **tool-calling**, not raw text-to-SQL. Decided.
- Job queue: **SQLite jobs table + worker process**, not Celery/RQ. Decided.

If any of these need to change later, update **AGENTS.md** first (architectural contract) and **Prompt.md** second (spec). Then this file's "Open architectural decisions" section.

---

## How to use this for a new session

1. Open this file. Find the first unchecked item.
2. Read the linked Prompt.md section.
3. Implement.
4. Run the relevant tests from Prompt.md V.
5. Tick the box. Commit. Repeat.

Ground rules a new session should preserve:

- **No monolithic scripts.** ~400-line soft cap per file. Each stage / embedder / repo / tool is its own module. Stages talk via Pydantic models, never direct imports.
- **CLI is tiered.** R.1 operational is required; R.2 diagnostic recommended; R.3 per-stage commands optional — build them only when actively working on that stage. API is the production interface.
- Local-first, no cloud, no Docker.
- Mocks for every heavy dep — tests must pass without GPU and without LM Studio.
- Lazy-import heavy deps (PaddleOCR, transformers, torch, sentence-transformers) so import cost is paid only when actually used.
- Raw OCR preserved exactly; corrections stored separately.
- Evidence is timestamped and source-tagged.
- Marketing entities and similar-ad verdicts are **grounded** — never fabricated.
- Read-only DB enforcement for the NL agent.
- Projection columns stay in sync with JSON source-of-truth in one transaction.
