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
| [x] | `pyproject.toml` with dependencies | torch NOT listed; transformers pinned to 4.40.2 (ROCm wheel compat) |
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
#    NOTE: this ROCm wheel lacks torch._C._distributed_c10d — transformers >=4.41 imports it
#    at module load time and crashes. Pin to 4.40.2 + sentence-transformers 3.0.1.
pip install --no-deps "transformers==4.40.2" "sentence-transformers==3.0.1"

# 4. Install whisper + dev extras
pip install faster-whisper
pip install -e ".[dev,clustering]"

# 5. Re-verify torch is still GPU-capable
python -c "import torch; print(torch.cuda.is_available())"
# → True
```

---

## Phase 3 — Core data + persistence

**Phase 3 status: in progress.** Core models, initial SQLite schema, WAL setup, sqlite-vec load check, `init-db`, read-only DB enforcement, and focused tests are implemented. Repository coverage is still partial: `AdRepository` and `JobRepository` exist; the remaining aggregate repositories are next.

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
| [~] | Repository classes (one per aggregate) | Prompt.md M |
| [x] | `init-db` CLI command | Prompt.md M, R |
| [x] | Path helpers in `paths.py` | Prompt.md P |
| [~] | Tests: schema migrations, projection write-back | Prompt.md V |

---

## Phase 4 — Pipeline stages (no AI yet, mocks first)

**Phase 4 status: in progress.** A0 ingest is implemented for prepared local video files: ffprobe metadata, ffmpeg frames/audio, whisper backend interface with mock/faster-whisper/whisper.cpp, progress events, manifest writing, cache reuse, optional SQLite persistence, and tests. Next unchecked core stage is dedup / similar-ad detection.

| | Item | Spec |
|---|---|---|
| [x] | A0 Ingest: ffmpeg frame extraction | Prompt.md A0 |
| [x] | A0 Ingest: ffmpeg audio extraction | Prompt.md A0 |
| [x] | A0 Ingest: Whisper backend interface + mock | Prompt.md A0, F |
| [x] | A0 Ingest: faster-whisper implementation | Prompt.md A0 |
| [x] | A0 Ingest: whisper.cpp CLI implementation (`GGML_VULKAN` on Windows AMD) | Prompt.md A0 |
| [x] | A0 Ingest: progress events for SSE | Prompt.md A0, O |
| [ ] | A1 Dedup: SHA256 of source file | Prompt.md A1 |
| [ ] | A1 Dedup: phash mean across keyframes | Prompt.md A1 |
| [ ] | A1 Dedup: short-circuit logic | Prompt.md A1.2 |
| [x] | B Manifest builder | Prompt.md B |
| [ ] | C Frame preprocessing (blur, blank, phash dedup, scene change, keyframes) | Prompt.md C |
| [ ] | D OCR engine interface + Mock + PaddleOCR (CPU) | Prompt.md D |
| [ ] | E PaddleOCR-VL adapter + gating | Prompt.md E |
| [~] | F Whisper transcript loaders + alignment | Prompt.md F |
| [ ] | G Rules engine + sample rules YAML | Prompt.md G |
| [ ] | H Evidence bundle builder | Prompt.md H |
| [~] | Tests: each stage with mocks + synthetic fixtures | Prompt.md V |

---

## Phase 5 — VLM + classification

| | Item | Spec |
|---|---|---|
| [ ] | `VLMVerifier` interface + `MockVLMVerifier` | Prompt.md I |
| [ ] | `HTTPVLMVerifier` (OpenAI-compatible, image_url base64) | Prompt.md I |
| [ ] | Configurable retry + timeout | Prompt.md I |
| [ ] | Render Gemma verifier prompt with taxonomy at startup | Prompt.md I, Q |
| [ ] | VLM JSON validation + fallback to `review` on parse failure | Prompt.md I |
| [ ] | J Aggregation + decision policy + sensitive thresholds | Prompt.md J |
| [ ] | K Marketing entity persistence (with projection write-back) | Prompt.md K, M |
| [ ] | LM Studio smoke test (Gemma 3 12B vision) | Prompt.md U |
| [ ] | Tests: valid + malformed VLM JSON, decision matrix, marketing entity round-trip | Prompt.md V |

---

## Phase 6 — Embeddings + search

| | Item | Spec |
|---|---|---|
| [ ] | `TextEmbedder` interface + `MockTextEmbedder` | Prompt.md L |
| [ ] | `SentenceTransformerEmbedder` (lazy import) | Prompt.md L |
| [ ] | `ImageEmbedder` interface + `MockImageEmbedder` | Prompt.md L |
| [ ] | `SigLIP2ImageEmbedder` (HuggingFace transformers, lazy import) | Prompt.md L |
| [ ] | `VectorStore` protocol + `SqliteVecStore` | Prompt.md L |
| [ ] | Optional: `QdrantStore` (no Docker; native Windows binary) | Prompt.md L |
| [ ] | Y Hybrid search: FTS5 + vec + RRF fusion | Prompt.md Y |
| [ ] | A1.3 post-embedding similar-ad enrichment | Prompt.md A1 |
| [ ] | `bench-vectors` CLI (parametrized backends) | Prompt.md L.4 |
| [ ] | Tests: parametrized over backends, RRF correctness, dim alignment, mock embedders | Prompt.md V |

---

## Phase 7 — Campaigns

| | Item | Spec |
|---|---|---|
| [ ] | Brand normalization helper (`"JEEP"` / `"Jeep"` → `"jeep"`) | Prompt.md (gap from earlier) |
| [ ] | X.2 Auto-discovery: HDBSCAN over `ads_visual` per brand | Prompt.md X.2 |
| [ ] | X.2 Fallback agglomerative clusterer | Prompt.md X.2 |
| [ ] | X.3 Manual CRUD + assignment endpoints | Prompt.md X.3, X.4 |
| [ ] | `campaigns discover` and `campaigns list` CLI | Prompt.md R |
| [ ] | Tests: synthetic clusters, user vs auto precedence, cascade on ad delete | Prompt.md V |

---

## Phase 8 — HTTP API + worker

| | Item | Spec |
|---|---|---|
| [ ] | FastAPI app skeleton + CORS + OpenAPI at `/docs` | Prompt.md N |
| [ ] | Upload endpoint (streaming, MIME whitelist, ffprobe sanity) | Prompt.md N |
| [ ] | Ad list/detail/frames/evidence/similar endpoints | Prompt.md N |
| [ ] | Ad update endpoint for curated field corrections (`PATCH /api/ads/{ad_id}`) | Prompt.md N |
| [ ] | Ad delete endpoint with cascade + optional local artifact cleanup (`DELETE /api/ads/{ad_id}`) | Prompt.md N, P |
| [ ] | Search endpoint (text/visual/hybrid) | Prompt.md N, Y |
| [ ] | Job status + SSE events + cancel | Prompt.md N, O |
| [ ] | Static file mount for `data/` | Prompt.md N, P |
| [ ] | Worker process: poll loop + state machine + cancellation | Prompt.md O |
| [ ] | Single-worker concurrency to protect VRAM | Prompt.md O |
| [ ] | Campaign endpoints | Prompt.md X.4 |
| [ ] | Tests: TestClient flows, SSE ordering, worker state transitions | Prompt.md V |

---

## Phase 9 — NL Agent

| | Item | Spec |
|---|---|---|
| [ ] | Tool catalog implementations (each tool against repo + mocks) | Prompt.md Z.1 |
| [ ] | `compare_ads` tool: vector cosine + structured diff + verdict | Prompt.md Z.1, J |
| [ ] | Read-only DB connection (`query_only=ON`) | Prompt.md Z.3 |
| [ ] | Schema summary auto-rendered from live DB at startup | Prompt.md Z.4 |
| [ ] | Agent loop: user → tool_call → tool_result → final | Prompt.md Z.2 |
| [ ] | LM Studio integration with `tools` parameter | Prompt.md Z.8 |
| [ ] | Malformed tool-call retry + fallback | Prompt.md Z.8 |
| [ ] | Conversation persistence in `agent_sessions` / `agent_messages` | Prompt.md Z.2 |
| [ ] | Agent endpoints + SSE event types | Prompt.md Z.5 |
| [ ] | `agent ask` / `agent repl` / `agent show-tools` / `agent show-schema` CLI | Prompt.md Z.6 |
| [ ] | Tests: each tool isolated, full loop with mock LM Studio, read-only enforcement, truncation reporting, SSE event ordering | Prompt.md Z.7 |

---

## Phase 10 — Polish + delivery

| | Item | Spec |
|---|---|---|
| [ ] | S AMD/ROCm diagnostic helper | Prompt.md S |
| [ ] | README full content (architecture, install, examples, agent, campaigns, Datasette) | Prompt.md U |
| [ ] | Sample mp4 + expected-output JSON committed to `samples/` | Prompt.md U, W |
| [ ] | End-to-end smoke test: ingest → classify → API → agent question | Prompt.md W |
| [ ] | All Prompt.md W acceptance criteria pass | Prompt.md W |
| [ ] | Run Follow-Up review prompt and patch findings | Prompt.md (Follow-Up) |
| [ ] | `start.bat` launching API + worker (+ optional Qdrant) | Prompt.md U |

---

## Phase 11 — Frontend management UI

Separate Vite + React + TypeScript + Tailwind + shadcn/ui app. It must consume the FastAPI OpenAPI surface only; no backend imports and no direct SQLite access.

| | Item | Spec |
|---|---|---|
| [ ] | Generate typed API client from `/openapi.json` | Prompt.md U |
| [ ] | All Ads page with paginated table, search, filters, sort, and status/decision/category chips | Prompt.md N, frontend |
| [ ] | Ad detail drawer/page with frames, evidence, transcript, OCR, classification, marketing entities, campaigns, and related ads | Prompt.md N |
| [ ] | Edit curated fields from UI: brand, products, category, decision, risk labels, marketing entities | Prompt.md N |
| [ ] | Delete ad record flow with confirmation, cascade preview, and optional local artifact cleanup | Prompt.md N, P |
| [ ] | Upload page with job progress via SSE | Prompt.md N, O |
| [ ] | Search page using keyword/vector/hybrid API modes | Prompt.md Y |
| [ ] | Campaign management page for manual assignment/curation | Prompt.md X.4 |
| [ ] | Tests: API client mocks, All Ads filtering/edit/delete flows, responsive table/detail states | frontend |

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
