# AGENTS.md

## Project goal

This repository implements a local-first, Windows-friendly multimodal ad-classification pipeline with structured marketing-entity extraction, embeddings + hybrid search, campaign tracking, and an interactive natural-language agent that answers questions about the database.

**Categorization-only.** All ingested content is presumed valid TV / promo / ad content. The system **categorizes**; it does not gate, allow, flag, or escalate to human review. There is no `decision` field, no review queue, no thresholds. `risk_labels` are kept as **descriptive observation tags** (e.g., "deceptive_urgency", "before_after") because they're useful for data-mining queries and surface in the UI as informational badges — they never block or gate.

The pipeline ingests:

- raw video files (`.mp4`, `.mov`, `.webm`)
- — extracted from those: timestamped frames sampled every ~500 ms, Whisper transcript segments, optional landing-page metadata, optional advertiser/placement metadata.

The pipeline outputs:

- primary category label (from a configurable taxonomy)
- risk / observation tags (descriptive only)
- confidence score
- timestamped evidence
- OCR verification notes
- structured marketing entities (brand, products, prices, offers, CTAs, social proof, disclaimers, creative format)
- text + visual embeddings persisted to a swappable vector store
- campaign assignments (auto-clustered or user-curated)
- similar / duplicate ad references

Primary design principle:
Do not rely on a single VLM for all extraction and reasoning. Use deterministic extraction and structured evidence first, then use the VLM for verification, semantic reasoning, marketing entity extraction, and final classification. Use embeddings + BM25 + RRF for retrieval. Use a tool-calling LLM agent — not raw text-to-SQL — for the question-answering interface.

**Local-first means local.** No cloud services, no Docker required. LM Studio (Gemma) runs on the same machine; everything else lives in a single SQLite database file plus a few directories.

**Frontend is decoupled.** The pipeline + API + worker are the system; the user-facing UI is a separate Vite + React + TypeScript + Tailwind + shadcn/ui app that consumes the FastAPI OpenAPI surface. The backend must never assume a specific frontend or coupling beyond JSON over HTTP + SSE. CORS allowlist is config-driven (default `http://localhost:5173`).

## Preferred architecture

Stages, top to bottom:

1. **Ingest** — ffmpeg samples frames at `frame_interval_ms`, extracts mono 16 kHz audio; Whisper (faster-whisper / whisper.cpp / mock) produces a transcript JSON. Skip stages whose outputs already exist.
1a. **Dedup / similar-ad detection** — three layers: SHA256 of source file (exact upload match), mean perceptual hash across keyframes (near-duplicate creative), and (after embedding) vector cosine similarity (semantic/campaign-variant match). L1 and L2 can short-circuit the pipeline; L3 enriches the final result with `related_ads`.
2. **Manifest** — build a timestamped manifest of frames + transcript segments, sorted by explicit `frame_index` / `time_ms`, never by filesystem order.
3. **Frame preprocessing** — blank/blur/low-contrast detection, perceptual-hash dedup, scene-change detection, keyframe selection.
4. **OCR** — PaddleOCR (CPU default) extracts raw visible text with bounding boxes, confidence, source engine, and frame timestamp. Raw OCR is preserved exactly.
5. **PaddleOCR-VL (conditional)** — only on hard frames matching gating rules: low confidence, dense text, small disclaimers, fragmented OCR, webpage/app screenshots, sensitive-category triggers.
6. **Transcript alignment** — attach Whisper segments within `±alignment_window_ms` of each frame; preserve full transcript for whole-ad reasoning.
7. **Rules engine** — deterministic regex/keyword rules over OCR + transcript produce category and risk evidence with timestamps. Configurable from YAML.
8. **Evidence bundle** — chronological frame summaries + OCR + PaddleOCR-VL corrections + nearby transcript + full transcript + rule triggers + selected images, capped by `vlm.max_frames_in_bundle`.
9. **VLM verification + classification + marketing entity extraction** — Gemma via LM Studio (OpenAI-compatible chat completion, default port 1234). One call returns: classification decision, risk labels, confidence, timestamped evidence, OCR-quality assessment, conflicts, summary, **and a structured `marketing_entities` block**.
10. **Category aggregation** — combine OCR / VL / rule / transcript / VLM evidence into the final classification record. Merges VLM `primary_category`, the union of VLM + rule-derived `risk_labels` (filtered to taxonomy), confidence, and all timestamped evidence into a single `FinalAdClassification`. No decisioning, no thresholds.
11. **Embedding** — text embedding from concatenated transcript + OCR (`sentence-transformers/all-MiniLM-L6-v2`, 384 dim). Per-keyframe **SigLIP 2** visual embeddings (`google/siglip2-base-patch16-224`, 768 dim) plus a mean-pooled ad-level visual vector. Persisted to the configured `VectorStore`. SigLIP 2 chosen for stronger fine-grained discrimination, better text-in-image handling, and shared text/image embedding space (enables cross-modal queries).
12. **Persistence** — write SQLite metadata (ads, frames, ocr_items, transcript_segments, rule_triggers, classifications, marketing_entities), the `ads_fts` FTS5 row, and the projection columns on `ads` (`brand_name`, `products_text`, `primary_category`, `decision`) in one transaction.
13. **Optional: campaign discovery** — on user request, cluster ad-level CLIP vectors within each brand and propose campaigns (`Campaign`, `AdCampaign`).
14. **NL agent (always-on service)** — a tool-calling Gemma loop answers user questions over the persisted data via a fixed tool catalog (list/count/get/aggregate, FTS5, vector similarity, hybrid search, read-only SQL escape hatch). All sessions and tool calls audited in `agent_sessions` / `agent_messages`.
15. **Final result** — strict JSON returned via API and persisted in `classifications` + `marketing_entities`.

## Model responsibilities

PaddleOCR:

- raw visible text extraction
- bounding boxes
- per-token confidence
- per-frame evidence

PaddleOCR-VL:

- optional hard-frame parser
- dense layout handling
- small-text correction
- structured document-like extraction

Gemma / VLM (verifier role):

- semantic verification of OCR
- multimodal reasoning across frames
- temporal reasoning over the frame sequence
- policy classification against the configured taxonomy
- conflict resolution between image, OCR, and transcript
- structured marketing-entity extraction grounded in evidence

Gemma / VLM (agent role, separate prompt):

- routes user questions to tool calls (`list_ads`, `count_ads`, `get_campaign`, `hybrid_search`, `vector_similarity`, `aggregate`, `sql_readonly`, etc.)
- never writes; the underlying DB connection is read-only
- cites `ad_id` / `campaign_id` in answers; never fabricates them
- prefers structured tools over `sql_readonly`

sentence-transformers (text embedder):

- one 384-dim vector per ad from concatenated transcript + OCR

SigLIP 2 (image embedder):

- one 768-dim vector per kept keyframe; mean-pool to one ad-level vector
- shared text/image space allows the agent to do cross-modal queries (text query → matching frames)
- the `ImageEmbedder` interface is model-agnostic; CLIP / EVA-CLIP / OpenCLIP can be swapped via config

Rules engine:

- deterministic triggers
- sensitive-category review routing
- confidence adjustment
- audit-friendly decisions

## Git workflow

- **Always commit and push directly to `main`.** No feature branches, no pull requests.
- After completing any unit of work, stage the relevant files, commit, and `git push origin main`.
- Never open a PR. Never create or switch to a non-`main` branch.

## Engineering constraints

- **PyTorch is pre-installed and must not be reinstalled.** The project's `.venv` already contains a manually-installed GPU-accelerated PyTorch build (DirectML or ROCm-Windows wheels) tuned for the deployment hardware (AMD 7900 XT). Implementers must:
  - **Not** list `torch`, `torchvision`, or `torchaudio` in `pyproject.toml` as direct dependencies.
  - When installing packages that depend on torch (e.g., `transformers`, `sentence-transformers`), use `pip install --no-deps <pkg>` or rely on pip's default `only-if-needed` upgrade strategy — never `--upgrade` or `-U` torch.
  - Add a startup environment check (`ad_classifier/diagnostics/env.py`) that imports torch, prints `torch.__version__`, the active backend (CUDA / ROCm / DirectML / CPU), and `torch.cuda.is_available() or hasattr(torch, 'directml')`. Fail loudly if torch is missing or running CPU-only when a GPU build was expected.
  - The README must include a clear "Do not run `pip install torch` — the GPU wheel is pre-installed" warning in the install section.
- **No monolithic scripts.** Each pipeline stage, embedder, vector backend, repository, and agent tool is its own module. Soft cap of ~400 lines per file. Stages do not import each other directly — they exchange Pydantic models. Tests mirror source layout. See `Code Organization` in Prompt.md for the suggested package tree.
- **Logging**: use `structlog` (preferred) or stdlib `logging` configured once in `ad_classifier/logging.py`. Every log line is structured JSON in production mode, human-readable in dev mode. Each log entry must include `ad_id` and `stage` when available. No `print()` calls in shipped code.
- **Error handling**: a stage that fails on a single frame logs and continues with degraded evidence. A stage that fails outright (e.g., ffmpeg crash, LM Studio unreachable) marks the job as `failed` with: `jobs.error` = short user-facing message; the full traceback goes to logs only — never to API responses or `agent_messages`. Pipeline never silently swallows exceptions; "graceful degradation" must produce an audit trail.
- **Restartability**: completed sub-stages cache their output to disk (frames, audio, whisper.json, ocr.json, evidence_bundle.json). Re-running a job reuses any output that already exists; only the failing stage and downstream stages re-run. `--force` re-runs everything from scratch.
- **CLI is tiered, not exhaustive.** Build R.1 (operational: `init-db`, `api`, `worker`) first. R.2 (diagnostic helpers) is recommended. R.3 (per-stage dev tools) is optional — only build a per-stage CLI command when that stage is actively being worked on. The API is the production interface; the CLI is dev tooling.
- **Local first**: no cloud services in the default deployment. No Docker required.
- **CPU defaults**: PaddleOCR `device: cpu`, embeddings `device: cpu`. AMD GPU support for PaddleOCR is best-effort via the diagnostic helper, never required.
- Do not silently overwrite OCR text with VLM corrections. Store raw OCR and corrected OCR separately.
- Every extracted claim must retain source: frame index, timestamp, OCR engine or transcript source, confidence if available, bounding box if available.
- The final classifier must cite evidence by timestamp.
- Marketing entities must be grounded in actual frames or transcript segments. Never fabricate brand, price, offer, or CTA values.
- The `sensitive` flag on categories is informational only. No threshold logic.
- The code must be testable without external paid services, without GPU, and without a running LM Studio instance — use mocks.
- Any VLM, OCR, embedding, and vector-store integration must be abstracted behind an interface with a mock implementation.
- Use clear type hints. Use Pydantic models or dataclasses for structured pipeline objects.
- **Projection columns** (`ads.brand_name`, `products_text`, `primary_category`, `decision`) are written from the JSON source of truth in the same transaction as `marketing_entities` / `classifications`. The JSON columns remain authoritative.
- **Read-only enforcement** for the NL agent's DB connection — `query_only=ON` pragma on SQLite. The agent must not be able to mutate the database under any tool call.
- **Tool-call format, not text-to-SQL**: the agent emits tool names + structured args. Each tool maps to a parameterized query template. `sql_readonly` exists as an escape hatch but is bounded (50-row cap) and audited.
- **WAL mode** on SQLite so the API process and worker process can read/write concurrently.
- Add unit tests for parsing, timestamp alignment, deduplication, rule triggers, final aggregation, marketing-entity parsing, embeddings (with mocks), vector-store CRUD (parametrized over backends), hybrid search RRF, campaign clustering, NL agent tool calls, SSE event ordering, read-only enforcement.
- Add CLI commands for local testing of every stage.

## Sensitive categories

Categories flagged as `sensitive: true` in `taxonomy.yaml` (medical/health, financial services, gambling, crypto/investment, political, etc.) are **purely informational**. The frontend may surface a "regulated category" badge; the agent may filter ("show me ads in sensitive categories"); but the classification pipeline treats them identically to any other category. There is no review threshold, no escalation, no gating.

Risk / observation tags worth surfacing in the UI:

- deceptive urgency
- unverified health claims
- guaranteed returns
- before/after claims
- targeting minors
- regulated substances
- brand impersonation
- hidden disclaimers
- price manipulation
- false scarcity

These are *observations*, not policy violations. They populate `risk_labels` so analysts can query "show me ads using urgency tactics across all brands" — useful for the data-mining demo, never used to block content.

The full canonical taxonomy (categories + risk labels, with sensitive flags) lives in `taxonomy.yaml` and is rendered into the Gemma verifier prompt at startup so the model only outputs allowed labels.

## Output requirements

The final result must follow this shape:

```json
{
  "ad_id": "ad_xxxxxxxx",
  "primary_category": "string",
  "risk_labels": ["string"],
  "confidence": 0.0,
  "sensitive_category": false,
  "evidence": [
    {
      "time_ms": 0,
      "frame_index": 0,
      "source": "ocr|paddlevl|transcript|visual|rule|vlm",
      "text": "string",
      "bbox": [0, 0, 0, 0],
      "confidence": 0.0,
      "reason": "string"
    }
  ],
  "ocr_quality": {
    "overall": "good|mixed|poor",
    "possible_errors": [],
    "missed_text": []
  },
  "marketing_entities": {
    "brand": {
      "name": "string|null",
      "logo_present": false,
      "logo_evidence": [],
      "tagline": "string|null"
    },
    "products": ["string"],
    "prices": [],
    "offers": [],
    "ctas": [],
    "social_proof": {
      "rating": null,
      "rating_count": null,
      "testimonials": [],
      "badges": []
    },
    "disclaimers": [],
    "creative_format": {
      "aspect_ratio": "1:1|9:16|16:9|4:5",
      "duration_ms": 0,
      "has_voiceover": true,
      "has_on_screen_text": true
    }
  },
  "campaigns": [
    {"campaign_id": "string", "name": "string", "assigned_by": "auto|user"}
  ],
  "embeddings": {
    "text_model": "sentence-transformers/all-MiniLM-L6-v2",
    "visual_model": "google/siglip2-base-patch16-224",
    "indexed_in": "sqlite-vec|qdrant"
  },
  "related_ads": {
    "exact_duplicate_of": null,
    "near_duplicate_of": null,
    "semantically_similar": [
      {
        "ad_id": "string",
        "overall_score": 0.91,
        "visual_score": 0.88,
        "text_score": 0.94,
        "verdict": "same_campaign_different_sku",
        "differences": [
          {"field": "products", "left": ["Wrangler"], "right": ["Grand Cherokee"]}
        ]
      }
    ]
  },
  "model_outputs": {
    "ocr": {},
    "paddlevl": {},
    "vlm": {}
  },
  "debug": {
    "selected_frames": [],
    "dropped_frames": [],
    "rules_triggered": [],
    "dropped_labels": []
  }
}
```
