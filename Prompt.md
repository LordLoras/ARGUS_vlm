# Codex Prompt: Local-First Multimodal Ad Classification Pipeline

Assume `AGENTS.md` already exists in the repository. Follow it.

Implement a local-first multimodal ad-classification pipeline.

Before editing:
1. Inspect the repository structure.
2. Identify the language, package manager, test framework, and existing conventions.
3. Reuse existing patterns where possible.
4. If the repository is empty or minimal, create a clean Python 3.11+ package structure.

Goal:
Build a Windows-friendly, local-first pipeline that ingests a raw `.mp4` ad, extracts frames and a Whisper transcript, runs OCR with PaddleOCR, optionally escalates difficult frames to PaddleOCR-VL, sends a compact evidence bundle to a Gemma VLM (LM Studio backend) for classification + marketing entity extraction, persists results to SQLite, embeds the ad into a swappable vector store, and exposes everything via a FastAPI HTTP API consumed by a custom frontend.

Production-oriented but runnable locally with mock components. **No Docker required.**

---

# Code Organization

> **⚠️ PyTorch pre-installed — do not reinstall.**
> The project's `.venv` already contains a manually-installed GPU-accelerated PyTorch build (DirectML or ROCm-Windows wheels) for the AMD 7900 XT. Any pip operation that touches torch will break GPU acceleration silently.
>
> Rules:
> - Do **not** list `torch` / `torchvision` / `torchaudio` in `pyproject.toml`.
> - When installing torch-dependent packages (`transformers`, `sentence-transformers`, `easyocr`, etc.), use `pip install --no-deps <pkg>` or pip's default `only-if-needed` upgrade strategy. Never run `pip install -U torch` or `pip install --upgrade torch`.
> - Add a startup env check (`ad_classifier/diagnostics/env.py`) that prints `torch.__version__`, active backend (CUDA / ROCm / DirectML / CPU), and `torch.cuda.is_available()` / DirectML detection. Fail loudly if torch is CPU-only when a GPU build was expected.
> - README install section must include a prominent warning: "Do not run `pip install torch`."

**No monolithic scripts.** Each pipeline stage, embedder, vector backend, repository, and tool is its own module. Soft rules:

- One responsibility per module. Stages do not import each other directly — they communicate via Pydantic models.
- File size soft cap **~400 lines**. If a module grows past that, split it.
- Tests mirror source layout under `tests/`.
- Lazy-import heavy dependencies (PaddleOCR, transformers, torch) so they aren't paid at import time and so unit tests run without them.
- Interfaces (Protocol or ABC) live in their own file; implementations sit beside them.

Suggested package layout:

```
ad_classifier/
  __init__.py
  config.py                       # load + validate config.yaml
  paths.py                        # P; one place for every on-disk path
  models/                         # Pydantic models from section A
    __init__.py
    pipeline.py                   # AdInput, FrameRef, TranscriptSegment, OCRItem, ...
    marketing.py                  # MarketingEntities + sub-models (K)
    similarity.py                 # RelatedAds, FieldDiff, SimilarityVerdict (J, A1)
    campaigns.py                  # Campaign, AdCampaign (X)
    agent.py                      # AgentSession, AgentMessage, ToolCall, ... (Z)
    jobs.py                       # JobRecord, JobState (O)
    vectors.py                    # VectorRecord, VectorHit, HybridHit (L, Y)
  db/
    schema.sql                    # M
    migrations/                   # numbered SQL or alembic
    connection.py                 # WAL + sqlite-vec extension load
    repositories/
      ads.py
      frames.py
      ocr_items.py
      transcript_segments.py
      rule_triggers.py
      classifications.py
      marketing_entities.py
      jobs.py
      campaigns.py
      ad_campaigns.py
      agent_sessions.py
      agent_messages.py
      ads_fts.py
  ingest/                         # A0
    __init__.py
    ffmpeg.py
    whisper.py                    # interface
    whisper_faster.py             # faster-whisper backend
    whisper_cpp.py                # whisper.cpp backend
    whisper_mock.py
  dedup/                          # A1
    file_hash.py
    phash.py
    similarity.py                 # post-embedding enrichment + verdict logic
  pipeline/
    manifest.py                   # B
    preprocess.py                 # C
    ocr/
      base.py                     # D interface
      mock.py
      paddleocr_engine.py
    paddlevl/
      base.py                     # E interface
      mock.py
      cli_adapter.py
    transcript_align.py           # F
    rules.py                      # G
    bundle.py                     # H
    aggregate.py                  # J
  vlm/
    base.py                       # I interface (VLMVerifier)
    mock.py
    http_client.py                # HTTPVLMVerifier (LM Studio compatible)
  embeddings/
    text/
      base.py
      mock.py
      sentence_transformers_embedder.py
    image/
      base.py
      mock.py
      siglip2_embedder.py
  vectors/
    base.py                       # VectorStore protocol
    sqlite_vec_store.py
    qdrant_store.py
    hybrid.py                     # Y; FTS5 + vec + RRF
  campaigns/
    discover.py                   # X auto-detection
  agent/
    tools/
      __init__.py
      list_ads.py
      get_ad_detail.py
      count_ads.py
      list_campaigns.py
      get_campaign.py
      full_text_search.py
      vector_similarity.py
      hybrid_search.py
      aggregate.py
      compare_ads.py              # A1, J
      sql_readonly.py
    schema_summary.py             # auto-generate from live DB
    loop.py                       # tool-call loop driver
    lm_studio.py                  # OpenAI-compatible client
  api/
    app.py                        # FastAPI app factory
    deps.py                       # DI for repos, vector store, etc.
    routes/
      ads.py
      jobs.py
      search.py
      campaigns.py                # X.4
      agent.py                    # Z.5
      static.py
  worker/
    runner.py                     # poll loop + dispatch
    stages.py                     # state machine wiring
  cli/
    __init__.py                   # typer/click app
    operational.py                # R.1 (init-db, api, worker)
    diagnostic.py                 # R.2 (test-amd-paddle, bench-vectors, agent show-*)
    dev.py                        # R.3 (per-stage helpers, optional)
  diagnostics/
    amd_paddle.py                 # S

prompts/
  gemma_ad_verifier.txt
  gemma_agent_system.txt

tests/
  models/...
  db/...
  ingest/...
  ...                             # mirror src/

config.example.yaml
taxonomy.yaml
pyproject.toml
README.md
```

This is a recommendation, not a mandate — minor reshuffling is fine. The hard rules are: no megafiles, no cross-stage imports, lazy heavy deps, tests mirror source.

---

# Required Features

## A0. Video Ingestion (mp4 → frames + transcript)

Front-of-pipeline stage that turns a raw video into the inputs the rest of the pipeline expects.

Inputs:

- video file path (`.mp4`, `.mov`, `.webm`)
- optional `ad_id` (else generate `ad_{8-char-base32-uuid4}`)
- `frame_interval_ms`, default `500`

Outputs:

- `data/frames/{ad_id}/frame_NNN_tNNNNms.png`
- `data/audio/{ad_id}/audio.wav` (16 kHz mono)
- `data/whisper/{ad_id}/whisper.json` (matches Shape 1 in section F)
- a row in the `ads` table

Sub-stages:

1. **ffprobe** — read duration, fps, resolution, codec; reject if not decodable.
2. **ffmpeg frame extraction** — sample every `frame_interval_ms`; emit PNG with the canonical filename pattern.
3. **ffmpeg audio extraction** — mono 16 kHz WAV.
4. **Whisper transcription** — backend configurable: `faster-whisper` (default), `whisper_cpp`, `mock`. Model size configurable (`tiny | base | small | medium | large-v3`).

Implementation notes:

- Each sub-stage behind an interface so tests can mock them.
- `ffmpeg` / `ffprobe` paths configurable; default to `PATH` lookup.
- Skip stages whose outputs already exist unless `--force`.
- Emit progress events suitable for SSE: `{"stage": "extracting", "done": 12, "total": 45}`.
- The Whisper JSON written here must round-trip through the loader in section F.

CLI:

```bash
python -m ad_classifier ingest \
  --video ./samples/ad.mp4 \
  --ad-id ad123 \
  --whisper-model base
```

Add tests with a tiny generated mp4 fixture and mock backends.

---

## A1. Duplicate / Similar Ad Detection

Three-layer check that runs at upload to catch existing matches before paying the cost of full classification, and after embedding to enrich the result with semantically similar neighbours.

### A1.1 Layers

| Layer | Signal | Catches | Cost | When |
|---|---|---|---|---|
| **L1: file hash** | SHA256 of source mp4 | literal re-upload of same file | µs | upload time, before ingest |
| **L2: perceptual hash** | mean phash across kept keyframes | re-encode, crop, different intro/outro length, cross-platform cuts | ms | after preprocessing |
| **L3: vector similarity** | cosine on `ads_visual` + `ads_text` | A/B variants, different SKU same campaign, paraphrased copy, cross-language | ~10 ms | after embedding |

L1 and L2 can short-circuit the pipeline. L3 never blocks; it enriches the final result.

### A1.2 Upload-time short-circuit

```
POST /api/ads/upload
  ↓
sha256(file) → ads.source_hash match?
  ├─ yes & config.dedup.skip_on_exact=true   → return existing ad_id, no job
  └─ no
      ↓
   queue ingest job
      ↓
   after preprocessing:
   compute phash_mean → check ads.phash_mean
   ├─ Hamming ≤ phash_distance_threshold (default 4)
   │   → mark related_ads.near_duplicate_of = matched ad_id
   │   → if config.dedup.skip_on_near_duplicate=true: skip remaining stages
   │     and reuse the matched ad's classification (with new ad_id)
   └─ otherwise continue full pipeline
```

### A1.3 Post-embedding enrichment

After Section L embeddings are written:

1. Query `ads_visual` for top-k (default 5) excluding self.
2. Query `ads_text` for top-k excluding self.
3. For any hit with cosine ≥ `similarity.related_threshold` (default 0.85):
   - call `compare_ads(self, hit)` to compute structured diff + verdict (Section Z)
   - attach to result's `related_ads.semantically_similar` list

### A1.4 Configurable thresholds

In `config.yaml`:

```yaml
dedup:
  skip_on_exact: true
  skip_on_near_duplicate: false      # demo default false; conservative
  phash_distance_threshold: 4

similarity:
  related_threshold: 0.85            # cosine cutoff for "related"
  near_duplicate_threshold: 0.95     # cosine cutoff for "near-duplicate"
  same_campaign_threshold: 0.85
  related_top_k: 5
  modality_weights:
    visual: 0.5
    text: 0.5
  verdicts:
    near_duplicate: { min_overall: 0.95, requires_no_field_diff: true }
    same_campaign_different_sku: { min_overall: 0.85, brand_match: true,
                                    differs_in: ["products"] }
    same_campaign_different_offer: { min_overall: 0.85, brand_match: true,
                                      differs_in: ["offers"] }
    similar_messaging_different_brand: { min_overall: 0.85,
                                          modality: "text", brand_match: false }
    related: { min_overall: 0.70 }
    unrelated: { min_overall: 0.0 }   # default fall-through
```

### A1.5 CLI

```bash
python -m ad_classifier dedup-check --video ./samples/ad.mp4
python -m ad_classifier dedup-check --ad-id ad123              # re-run on existing
python -m ad_classifier compare-ads ad_42 ad_43
```

### A1.6 Tests

- L1: same file twice → second upload returns existing ad_id with no new job.
- L2: synthetic frames with phash distance below/above threshold.
- L3: mock embeddings producing known cosine distances → correct verdict assignment.
- Verdict thresholds applied in priority order (most specific verdict wins).
- `skip_on_near_duplicate` path reuses classification correctly.

---

## A. Data Models

Create typed models. Use Pydantic if available; otherwise dataclasses.

Pipeline core:

- `AdInput`
- `FrameRef`
- `TranscriptSegment`
- `OCRItem`
- `PaddleVLOutput`
- `FrameEvidence`
- `EvidenceBundle`
- `VLMVerificationResult`
- `RuleTrigger`
- `FinalAdClassification`

Marketing entities (section K):

- `Brand`, `Price`, `Offer`, `CallToAction`, `SocialProof`, `Disclaimer`, `CreativeFormat`, `MarketingEntities`

Vector store (section L):

- `VectorRecord`, `VectorHit`, `HybridHit`

Similarity / dedup (section A1, section J):

- `RelatedAds`, `RelatedAd`, `FieldDiff`, `SimilarityVerdict` (Literal)

Jobs (section O):

- `JobRecord`, `JobState` (Literal of state names)

Campaigns (section X):

- `Campaign`, `AdCampaign`

NL Agent (section Z):

- `AgentSession`, `AgentMessage`, `ToolCall`, `ToolResult`, `AgentEvent`

Each frame must include:

- `ad_id`
- `frame_index`
- `time_ms`
- file path
- optional width/height
- quality flags
- OCR results
- optional PaddleOCR-VL results

Each transcript segment must include:

- `start_ms`
- `end_ms`
- `text`
- optional confidence

Each evidence item must include:

- source: `ocr | paddlevl | transcript | visual | rule | vlm`
- `time_ms`
- `frame_index` when applicable
- text or description
- bbox when applicable
- confidence when available
- reason

---

## B. Manifest Builder

Implement a manifest builder that accepts:

- an input directory containing screenshots
- a Whisper JSON transcript
- optional `ad_id`
- optional `frame_interval_ms`, default `500`

Support filenames such as:

- `frame_000_t0000ms.png`
- `frame_001_t0500ms.png`
- `ad123_frame_000001_t2500ms.jpg`
- `screenshot_000004.png`

Rules:

- Prefer explicit timestamp in filename.
- Otherwise infer timestamp from `frame_index * frame_interval_ms`.
- Sort by `frame_index` / `time_ms` explicitly.
- Never rely on filesystem order.
- Validate duplicate timestamps or duplicate frame indices.
- Output `manifest.json`.

Add tests for filename parsing and timestamp inference.

---

## C. Frame Preprocessing

Implement frame preprocessing:

1. Blank/near-blank detection.
2. Blur detection.
3. Perceptual hash deduplication.
4. Optional scene-change detection based on image difference.
5. Keyframe selection.

Keyframe policy — keep a frame if:

- it is the first frame;
- it is the last frame;
- perceptual hash changed enough;
- image difference changed enough;
- OCR text later differs from previous retained frame;
- sensitive visual detector/rule triggers later identify it as important.

At this stage, implement basic image-based deduplication only. Leave hooks for OCR-aware keyframe selection after OCR runs.

Dependencies may include Pillow, imagehash, OpenCV, or pure-Python alternatives. Prefer simple, reliable implementation over excessive dependencies.

Add tests with synthetic images.

---

## D. OCR Engine Interface

```python
class OCREngine:
    def extract(self, frame: FrameRef) -> list[OCRItem]:
        ...
```

Implement:

1. `MockOCREngine` for tests.
2. `PaddleOCREngine`.

`PaddleOCREngine` requirements:

- Lazy import PaddleOCR so tests do not require it.
- Allow device configuration: `cpu`, `gpu:0`. **Default to `cpu` on Windows** — see section S for AMD/ROCm caveats.
- Return text, confidence, bbox, engine name, frame timestamp.
- Preserve raw OCR exactly. Do not normalize away policy text.
- Include a CLI command to OCR one image or a folder.

Example CLI:

```bash
python -m ad_classifier ocr --input ./frames --output ./out/ocr.json --device cpu
```

If PaddleOCR is missing, show a clear error telling the user how to install it.

---

## E. PaddleOCR-VL Fallback Interface

```python
class DocumentParser:
    def parse(self, frame: FrameRef, ocr_items: list[OCRItem]) -> PaddleVLOutput:
        ...
```

Implement:

1. `MockPaddleVLParser`.
2. `PaddleVLParser` shell/CLI adapter with configurable command template.

```yaml
paddlevl:
  enabled: true
  command: "paddlex --pipeline PaddleOCR-VL-native.yaml --input {image_path} --output {output_dir}"
```

The code should:

- run PaddleOCR-VL only when gating rules request it;
- capture stdout/stderr;
- parse JSON output if available;
- otherwise store raw output and mark parse status;
- fail gracefully and continue with PaddleOCR-only evidence.

Gating rules — run PaddleOCR-VL if any condition is true:

- mean OCR confidence below threshold (default `0.70`);
- any OCR item confidence below threshold (default `0.50`);
- total OCR text length above dense-text threshold;
- OCR contains many short fragments;
- frame quality indicates small/blurred/dense text;
- transcript/rules indicate sensitive category;
- config forces PaddleOCR-VL for all frames.

Add tests for gating logic.

---

## F. Whisper Transcript Loading and Alignment

Loaders for common Whisper JSON shapes.

Shape 1 (faster-whisper / openai-whisper):

```json
{
  "segments": [
    {"start": 0.2, "end": 1.7, "text": "hello"}
  ]
}
```

Shape 2:

```json
[
  {"start_ms": 200, "end_ms": 1700, "text": "hello"}
]
```

Support seconds and milliseconds.

Alignment: for each frame, attach transcript segments whose interval intersects `frame_time_ms ± alignment_window_ms` (default 1500 ms). Also provide the full transcript for whole-ad reasoning.

Add tests for alignment.

---

## G. Rules Engine

Deterministic rules over OCR text and transcript text.

Support:

- case-insensitive matching
- regex matching
- category labels
- risk labels
- severity
- review routing
- evidence creation

Default rule examples:

Financial: `no credit check`, `guaranteed approval`, `instant approval`, `bad credit ok`, `payday`, `APR`

Health/medical: `lose * lbs`, `cure`, `miracle`, `clinically proven`, `no prescription`, `before and after`

Investment/crypto: `guaranteed returns`, `risk-free investment`, `double your money`, `crypto`, `forex`

Urgency/deception: `limited spots`, `act now`, `only today`, `secret method`

Make rules configurable via YAML or JSON. Add tests for rule matching and evidence generation.

---

## H. Evidence Bundle Builder

Build a compact evidence bundle for the VLM.

Input: selected frames, OCR results, optional PaddleOCR-VL output, aligned transcript, rules triggered, metadata.

Output:

- chronological frame summaries
- OCR by frame
- PaddleOCR-VL corrections by frame
- nearby transcript by frame
- full transcript
- rules triggered
- selected image paths to send to VLM (capped by `vlm.max_frames_in_bundle`, default 12)

Serializable to JSON.

### H.1 Frame selection when over budget

When kept-keyframe count exceeds `vlm.max_frames_in_bundle`, **deterministic selection** in priority order:

1. Always include: first kept frame, last kept frame.
2. **Rule-trigger frames**: any frame referenced by a `rule_triggers.frame_index` (sorted by severity: `severity=high` before `medium` before `low`).
3. **High OCR text density**: frames with the most OCR characters (proxies for "ad has important text here").
4. **Even time distribution**: from remaining frames, select to evenly span the timeline (greedy: pick the frame furthest from already-selected times).
5. **Tiebreak**: ascending `frame_index`.

Stop when the bundle reaches `max_frames_in_bundle`. The selection is deterministic for a given input — same input must always produce the same bundle (important for reproducibility and for the restartability cache from Section O.1).

Record the selection in `evidence_bundle.json` with a `frame_selection_reason` field per included frame so the agent + auditors can see *why* each frame made the cut.

Tests: budget = 12, with 30 keyframes → exactly 12 selected; first and last frames always present; rule-trigger frames preferred over time-distributed; deterministic across runs.

---

## I. VLM / Gemma Verifier Interface

```python
class VLMVerifier:
    def verify_and_classify(self, bundle: EvidenceBundle) -> VLMVerificationResult:
        ...
```

Implement:

1. `MockVLMVerifier` for tests.
2. `HTTPVLMVerifier` for OpenAI-compatible chat completion endpoints (LM Studio's default protocol).

`HTTPVLMVerifier` requirements:

- Configurable endpoint, model name, timeout, retry policy.
- API key read from env var named in config (LM Studio ignores it; harmless).
- Multimodal request: send images as base64-encoded `image_url` content blocks per the OpenAI vision content schema. LM Studio with a Gemma 3 multimodal model accepts this directly.
- Do not hard-code one provider — the abstraction must allow swapping to other endpoints.

VLM prompt requirements (template lives in `prompts/gemma_ad_verifier.txt`):

- treat frames as one chronological sequence;
- use timestamps;
- classify the whole ad, not individual frames;
- verify OCR plausibility;
- identify missed visual text;
- resolve conflicts between OCR and transcript;
- extract structured marketing entities (section K);
- return strict JSON only;
- cite timestamped evidence.

Allowed decisions: `allow`, `flag`, `review`.

Required JSON fields: `primary_category`, `risk_labels`, `confidence`, `decision`, `needs_human_review`, `evidence`, `ocr_quality`, `marketing_entities`, `conflicts`, `summary`.

The parser must validate VLM JSON. If invalid:

- store raw response;
- return `needs_human_review=true`;
- set `decision=review`;
- include error details.

Add tests for valid and invalid VLM responses.

---

## J. Aggregation and Decisioning

Inputs:

- OCR evidence
- PaddleOCR-VL evidence
- transcript evidence
- rule triggers
- VLM result

Decision policy:

- high-confidence severe rule + supporting evidence → flag or review
- VLM low confidence → review
- VLM/rules disagreement → review
- OCR poor quality in sensitive category → review
- no triggers + high VLM confidence benign → allow

Default thresholds:

- `auto_allow_threshold`: `0.30` risk
- `review_band`: `0.30` to `0.75`
- `auto_flag_threshold`: `0.75` risk

For sensitive categories (see section Q), lower review threshold per `sensitive_review_threshold`.

Final result must include: decision, risk labels, confidence, evidence, debug info, model outputs, marketing entities, **versioning metadata** (`vlm_model`, `vlm_prompt_version`, `embedder_text_model`, `embedder_visual_model`, `pipeline_version`), **and a `related_ads` block** populated from Section A1 layered detection:

```python
class RelatedAds(BaseModel):
    exact_duplicate_of: str | None
    near_duplicate_of: dict | None      # {"ad_id": str, "phash_distance": int}
    semantically_similar: list[RelatedAd]

class RelatedAd(BaseModel):
    ad_id: str
    overall_score: float
    visual_score: float | None
    text_score: float | None
    verdict: Literal[
        "near_duplicate",
        "same_campaign_different_sku",
        "same_campaign_different_offer",
        "similar_messaging_different_brand",
        "related",
        "unrelated",
    ]
    differences: list[FieldDiff]        # structured field-level diff

class FieldDiff(BaseModel):
    field: str                          # "brand", "products", "offers", "ctas", ...
    left: object
    right: object
```

Add tests for allow/flag/review decisions and for `related_ads` population end-to-end.

---

## K. Marketing Entity Extraction

Extend the VLM output and data models with structured marketing entities, extracted in the same Gemma call as classification.

Data model:

```python
class Brand(BaseModel):
    name: str | None
    logo_present: bool
    logo_evidence: list[FrameEvidence]
    tagline: str | None

class Price(BaseModel):
    amount: float
    currency: str
    frame_index: int
    time_ms: int
    discounted_from: float | None
    discount_pct: float | None

class Offer(BaseModel):
    type: Literal["bogo", "free_trial", "percent_off", "flat_off",
                  "bundle", "giveaway", "other"]
    value: str
    expiry_text: str | None
    expiry_resolved: date | None
    promo_code: str | None
    scarcity_signals: list[str]
    urgency_signals: list[str]

class CallToAction(BaseModel):
    text: str
    destination_hint: str | None
    time_ms: int
    frame_index: int

class SocialProof(BaseModel):
    rating: float | None
    rating_count: str | None
    testimonials: list[str]
    badges: list[str]

class Disclaimer(BaseModel):
    text: str
    time_ms: int
    frame_index: int
    is_small_print: bool

class CreativeFormat(BaseModel):
    aspect_ratio: str       # "1:1" | "9:16" | "16:9" | "4:5"
    duration_ms: int
    has_voiceover: bool
    has_on_screen_text: bool

class MarketingEntities(BaseModel):
    brand: Brand
    products: list[str]
    prices: list[Price]
    offers: list[Offer]
    ctas: list[CallToAction]
    social_proof: SocialProof
    disclaimers: list[Disclaimer]
    creative_format: CreativeFormat
```

Extraction rules:

- Every extracted claim must include `frame_index` + `time_ms` evidence.
- Empty/unknown values are `null` or empty list — never fabricated.
- Raw OCR text and transcript must be preserved separately; entities are derived, not authoritative substitutes.

### K.1 Brand normalization

Different sources spell brand names differently: "Jeep" / "JEEP" / "jeep" / "Jeep®" / "Jeep®." A small `brand_normalize(name: str) -> str` utility lives in `ad_classifier/marketing/brand.py`:

- lowercase
- strip trademark symbols (`®`, `™`, `©`)
- collapse whitespace
- strip leading/trailing punctuation
- map known aliases via `brands_aliases.yaml` (e.g., `coca cola → coca-cola`, `coke → coca-cola`)

Called both:

- when writing `ads.brand_name` (always normalized)
- inside the agent's brand filter (so `list_ads(filter={brand: "Jeep"})` matches `ads.brand_name = "jeep"`)

The raw VLM-extracted name is preserved in `marketing_entities.brand_json.name` (source of truth); `ads.brand_name` is the normalized projection used for filters and joins.

Aliases file format:

```yaml
# brands_aliases.yaml
aliases:
  coca-cola: ["coke", "coca cola", "cocacola"]
  pepsi: ["pepsi-cola", "pepsi cola"]
  jeep: []                        # canonical name, no aliases yet
```

Tests in V must cover: case insensitivity, trademark stripping, alias resolution, agent filter round-trip ("show me Jeep ads" matches stored "jeep").

Persistence:

- Save to SQLite `marketing_entities` table (one row per ad, JSON columns for nested structures).
- Project `brand_normalize(brand.name)` to `ads.brand_name` in the same transaction.
- Surface in `GET /api/ads/{id}` responses.

Gemma prompt (section "Gemma Verifier Prompt Template" at the bottom) must instruct the model to output a `marketing_entities` block matching the schema above.

Tests:

- VLM JSON parsing for valid + missing fields + malformed marketing entities.
- DB round-trip of marketing entities.

---

## L. Embeddings & Vector Store

### L.1 Embedding generation

Two embedding modalities per ad:

1. **Text embedding** — concatenate Whisper transcript + all OCR text per ad → embed with `sentence-transformers/all-MiniLM-L6-v2` (384 dim). CPU.
2. **Visual embedding** — embed each kept keyframe with **SigLIP 2** (`google/siglip2-base-patch16-224`, 768 dim). Mean-pool keyframe vectors → one ad-level visual vector. Persist per-keyframe vectors as well for fine-grained search.

SigLIP 2 chosen over CLIP because: (a) better fine-grained discrimination (Wrangler vs Grand Cherokee separates more cleanly), (b) better handling of overlay text in ads, (c) shared image/text embedding space enables **cross-modal text→image search** — the agent can answer "find ads showing red SUVs in dealerships" by encoding the query string with SigLIP's text encoder and searching `keyframes_visual`. Sentence-transformers cannot do this because its text vectors live in a different space.

The `ImageEmbedder` interface is model-agnostic. Swap to CLIP / EVA-CLIP / OpenCLIP with a single config change. Tests mock the embedder so the chosen model does not affect unit tests.

Interfaces:

```python
class TextEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class ImageEmbedder(Protocol):
    def embed(self, paths: list[Path]) -> list[list[float]]: ...
```

Implementations:

- `SentenceTransformerEmbedder`
- `CLIPImageEmbedder`
- `MockTextEmbedder`, `MockImageEmbedder`

Lazy-import heavy deps. Model names configurable.

### L.2 Vector store interface

```python
class VectorStore(Protocol):
    def upsert(self, collection: str, id: str, vector: list[float], payload: dict) -> None: ...
    def search(self, collection: str, vec: list[float], k: int,
               filter: dict | None = None) -> list[VectorHit]: ...
    def delete(self, collection: str, id: str) -> None: ...
    def count(self, collection: str) -> int: ...
```

Two implementations behind the same protocol:

1. **`SqliteVecStore`** — default. Uses the [`sqlite-vec`](https://github.com/asg017/sqlite-vec) extension loaded into the project's main SQLite DB. No extra service. Filter dict translates to SQL `WHERE` clauses. Multi-process safe via WAL.
2. **`QdrantStore`** — scalability target. Connects to a native Qdrant Windows binary (no Docker). Filter dict translates to Qdrant payload filters. Selected via config.

Collections:

- `ads_text` — one vector per ad (sentence-transformers, 384-dim)
- `ads_visual` — one vector per ad (mean-pooled SigLIP 2, 768-dim)
- `keyframes_visual` — per-keyframe vectors (SigLIP 2, 768-dim)

Vector dims are config-driven (`vector_store.text_dim`, `vector_store.visual_dim`); changing the embedder changes the dim, requiring a rebuild of affected collections.

Filter dict spec (must work in both backends):

- exact: `{"category": "finance_banking"}`
- contains: `{"risk_labels__contains": "guaranteed_returns"}`
- range: `{"confidence__gte": 0.7}`

### L.3 Similarity queries

Implement on top of the store:

- `find_similar_ads(ad_id, k)` — combined ranking over `ads_text` + `ads_visual`.
- `find_near_duplicates(ad_id, threshold=0.95)` — uses `keyframes_visual` + phash pre-filter.
- `text_to_ad(query, k)` — embed string → search `ads_text`.
- `image_to_ad(image_path, k)` — embed image → search `ads_visual`.

### L.4 Benchmark CLI

Demonstrates the architectural choice (sqlite-vec at our scale, Qdrant as scale target).

```bash
python -m ad_classifier bench-vectors --backend sqlite-vec --n 1000 --dim 384 --queries 100
python -m ad_classifier bench-vectors --backend qdrant     --n 1000 --dim 384 --queries 100
```

Prints p50 / p95 / p99 query latency. At small N both should look near-identical.

### L.5 Hybrid search

Vector similarity is one of two retrieval modes. The other is BM25 keyword over the `ads_fts` virtual table. Combined retrieval (RRF fusion of both) is specified in **section Y**. Implementations of `VectorStore` only need to expose ANN; fusion lives at a higher layer.

### L.6 Notes on sqlite-vec on Windows

- Stock Python on Windows sometimes ships with `sqlite3` extension loading disabled. The `init-db` command should self-test extension loading and print install guidance (e.g., python.org installer or `pysqlite3-binary`) if it fails.

Tests parametrized over both backends: same suite, both must pass.

---

## M. SQLite Metadata Database

Single SQLite file (`ad_classifier.db`) holds all metadata. Use SQLAlchemy or SQLModel. Enable WAL mode for concurrent API + worker access.

Schema:

```sql
CREATE TABLE ads (
  id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  duration_ms INTEGER,
  width INTEGER,
  height INTEGER,
  fps REAL,
  status TEXT,
  -- denormalized projection columns populated at finalize-time from marketing_entities
  -- so the agent's SQL tool and dashboard list endpoints don't need json_extract
  brand_name TEXT,
  brand_confidence REAL,
  products_text TEXT,
  primary_category TEXT,
  decision TEXT,
  -- dedup signals (Section A1)
  source_hash TEXT,                     -- SHA256 of source mp4
  phash_mean TEXT                       -- mean perceptual hash across kept keyframes
);
CREATE INDEX idx_ads_brand ON ads(brand_name);
CREATE INDEX idx_ads_category ON ads(primary_category);
CREATE INDEX idx_ads_decision ON ads(decision);
CREATE UNIQUE INDEX idx_ads_source_hash ON ads(source_hash) WHERE source_hash IS NOT NULL;
CREATE INDEX idx_ads_phash_mean ON ads(phash_mean);

CREATE TABLE frames (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  frame_index INTEGER NOT NULL,
  time_ms INTEGER NOT NULL,
  path TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  kept BOOLEAN NOT NULL,
  drop_reason TEXT,
  phash TEXT,
  blur_score REAL,
  UNIQUE(ad_id, frame_index)
);

CREATE TABLE ocr_items (
  id INTEGER PRIMARY KEY,
  frame_id INTEGER REFERENCES frames(id) ON DELETE CASCADE,
  engine TEXT NOT NULL,
  text TEXT NOT NULL,
  bbox_json TEXT,
  confidence REAL
);

CREATE TABLE transcript_segments (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL,
  confidence REAL
);

CREATE TABLE rule_triggers (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  rule_id TEXT NOT NULL,
  category TEXT,
  risk_label TEXT,
  severity TEXT,
  evidence_text TEXT,
  time_ms INTEGER,
  frame_index INTEGER
);

CREATE TABLE classifications (
  ad_id TEXT PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
  primary_category TEXT,
  risk_labels_json TEXT,
  confidence REAL,
  decision TEXT,
  needs_human_review BOOLEAN,
  ocr_quality_json TEXT,
  vlm_raw_json TEXT,
  evidence_json TEXT,
  -- versioning: which models / prompts produced this row
  vlm_model TEXT NOT NULL,                 -- e.g. "gemma-3-12b-it"
  vlm_prompt_version TEXT NOT NULL,        -- e.g. "verifier-2026.05.01"
  embedder_text_model TEXT NOT NULL,       -- e.g. "sentence-transformers/all-MiniLM-L6-v2"
  embedder_visual_model TEXT NOT NULL,     -- e.g. "google/siglip2-base-patch16-224"
  pipeline_version TEXT NOT NULL,          -- semver-ish; bumps when stages change
  created_at TIMESTAMP
);
CREATE INDEX idx_classifications_vlm_model ON classifications(vlm_model);
CREATE INDEX idx_classifications_pipeline_version ON classifications(pipeline_version);

CREATE TABLE marketing_entities (
  ad_id TEXT PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
  brand_json TEXT,
  products_json TEXT,
  prices_json TEXT,
  offers_json TEXT,
  ctas_json TEXT,
  social_proof_json TEXT,
  disclaimers_json TEXT,
  creative_format_json TEXT
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  progress REAL,
  message TEXT,
  error TEXT,
  started_at TIMESTAMP,
  finished_at TIMESTAMP
);

-- Campaigns (section X) — many ads belong to a campaign (e.g., "Jeep Freedom Days").
CREATE TABLE campaigns (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  advertiser TEXT,
  brand TEXT,
  theme TEXT,
  start_date DATE,
  end_date DATE,
  created_by TEXT NOT NULL,             -- 'auto' | 'user'
  description TEXT,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE ad_campaigns (
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
  similarity_score REAL,                -- only when auto-assigned by clustering
  assigned_by TEXT NOT NULL,            -- 'auto' | 'user'
  assigned_at TIMESTAMP NOT NULL,
  PRIMARY KEY (ad_id, campaign_id)
);

-- FTS5 virtual table (section Y) — keyword half of hybrid search and the agent's keyword tool.
CREATE VIRTUAL TABLE ads_fts USING fts5(
  ad_id UNINDEXED,
  brand,
  products,
  primary_category,
  transcript_text,
  ocr_text,
  marketing_entities_text,
  tokenize = 'porter unicode61'
);

-- NL Agent (section Z) — conversation memory + tool-call audit log.
CREATE TABLE agent_sessions (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  user_label TEXT,
  context_json TEXT                     -- pinned ad_ids, filters, etc.
);

CREATE TABLE agent_messages (
  id INTEGER PRIMARY KEY,
  session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                   -- 'user' | 'assistant' | 'tool'
  content TEXT NOT NULL,
  tool_name TEXT,                       -- when role='tool'
  tool_args_json TEXT,
  tool_result_json TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_frames_ad ON frames(ad_id);
CREATE INDEX idx_ocr_frame ON ocr_items(frame_id);
CREATE INDEX idx_transcript_ad ON transcript_segments(ad_id);
CREATE INDEX idx_jobs_state ON jobs(state);
CREATE INDEX idx_ad_campaigns_ad ON ad_campaigns(ad_id);
CREATE INDEX idx_ad_campaigns_campaign ON ad_campaigns(campaign_id);
CREATE INDEX idx_campaigns_brand ON campaigns(brand);
CREATE INDEX idx_agent_messages_session ON agent_messages(session_id);
```

Projection write-back at finalize:

When the worker writes `classifications` and `marketing_entities`, it must in the same transaction update:

- `ads.brand_name`, `ads.brand_confidence`, `ads.products_text`, `ads.primary_category`, `ads.decision`
- one row in `ads_fts` with concatenated transcript + OCR text + brand/products/category for hybrid search.

JSON columns remain the source of truth; column projections exist only for fast filter/agent queries.

Provide:

- `init-db` CLI command (create schema, enable WAL, verify sqlite-vec extension loads).
- Migration mechanism (Alembic or hand-written numbered SQL files).
- `Repository` classes per aggregate (AdRepository, FrameRepository, JobRepository, etc.) so the API and worker share access logic.

---

## N. HTTP API (FastAPI)

Expose a FastAPI service. Pydantic models from section A double as request/response schemas. OpenAPI docs at `/docs`.

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST   | `/api/ads/upload`               | multipart upload, returns `{ad_id, job_id}` |
| GET    | `/api/ads`                      | list with filters: `category`, `risk`, `decision`, `brand`, `q`, paginated |
| GET    | `/api/ads/{ad_id}`              | full classification + marketing entities |
| PATCH  | `/api/ads/{ad_id}`              | manual field corrections for curated metadata/classification fields |
| DELETE | `/api/ads/{ad_id}`              | delete ad metadata and cascaded child rows; optionally remove local media artifacts |
| GET    | `/api/ads/{ad_id}/frames`       | keyframes paginated |
| GET    | `/api/ads/{ad_id}/evidence`     | all evidence rows |
| GET    | `/api/ads/{ad_id}/similar?k=10` | vector similarity (text + visual combined) |
| GET    | `/api/search`                   | `?q=...&modality=text\|visual&k=10` |
| GET    | `/api/jobs/{job_id}`            | current state snapshot |
| GET    | `/api/jobs/{job_id}/events`     | Server-Sent Events stream |
| POST   | `/api/jobs/{job_id}/cancel`     | cooperative cancel |
| GET    | `/static/ads/{ad_id}/frames/{n}.png` | static frame image |
| GET    | `/static/ads/{ad_id}/source.mp4`     | original video |

Campaign endpoints are specified in **section X.4**. NL agent endpoints in **section Z.5**.

Requirements:

- CORS middleware with configurable allowlist (frontend dev server e.g. `http://localhost:5173`).
- Upload limits: `max_bytes` (default 200 MB), MIME whitelist (`video/mp4`, `video/quicktime`, `video/webm`).
- Stream upload writes (do not buffer mp4 in memory).
- ffprobe sanity check during upload — reject undecodable files before persisting.
- All responses JSON; errors use RFC 7807 problem-details.
- API never executes pipeline work directly — it only enqueues a job and reads state.
- Ad updates are curated corrections, not pipeline reruns. `PATCH /api/ads/{ad_id}` may update allowed fields such as brand, products, primary category, decision, risk labels, and marketing-entity JSON. It must write the JSON source of truth, update projection columns, and refresh the `ads_fts` row in one transaction. Do not update projection columns alone.
- Ad deletion must be explicit and auditable at API level: `DELETE /api/ads/{ad_id}` removes the `ads` row and relies on `ON DELETE CASCADE` for frames, OCR, transcripts, classifications, marketing entities, jobs, campaigns joins, and agent references where applicable. Local source/frame/audio artifacts are deleted only when the request explicitly opts in, e.g. `?delete_files=true`; otherwise database records are removed and files are left untouched for manual recovery.
- **Path-traversal guard on static endpoints**: `ad_id` path parameters must validate against the regex `^ad_[a-z0-9]{8}$` before any filesystem join. Frame indices and filenames likewise validated. Reject with 400 on mismatch — never `os.path.join(static_root, untrusted)`. Use `paths.py` helpers exclusively; never construct paths inline in route handlers.
- Frame index in `/static/ads/{ad_id}/frames/{n}.png` must be a non-negative integer; the resolved file must be inside `data/frames/{ad_id}/` (verify with `Path.resolve()` containment check after construction).

Add tests using FastAPI's TestClient: upload happy path, rejected MIME, malformed video, list/filter/search, PATCH projection/FTS sync, DELETE cascade, SSE event ordering.

---

## O. Job Orchestration

A separate worker process polls the SQLite `jobs` table and runs the pipeline.

State machine:

```
queued → extracting → transcribing → preprocessing → ocr →
  → paddlevl (optional) → embedding → vlm → finalizing → done
                                                       ↘
                                                        failed | cancelled
```

Worker requirements:

- Single-worker default (`concurrency: 1`) to avoid GPU/VRAM contention with LM Studio.
- Polls every `worker.poll_interval_ms` (default 1000 ms) for new `queued` jobs.
- Updates `jobs.state`, `jobs.progress`, `jobs.message` between sub-stages.
- Catches and stores exceptions in `jobs.error` (short user-facing message only; full traceback to logs), transitions to `failed`.
- Honours cooperative cancel: checks `jobs.state == 'cancelled'` between sub-stages.
- Appends progress events to a per-job event log (in-memory ring buffer + on-disk fallback).

### O.1 Restartability

Each completed sub-stage **caches its output to disk** under the storage layout (Section P): frames, audio.wav, whisper.json, manifest.json, preprocessed.json, ocr.json, evidence_bundle.json, embedding vectors.

On retry of a failed or interrupted job:

- Walk the state machine in order. For each stage, if its output file/row exists and is consistent with config (same `pipeline_version`, same `embedder_*_model`), skip and reuse.
- The first stage with missing or stale output is where the run resumes.
- Downstream stages always re-run from the resume point.
- `--force` invalidates all caches and runs from scratch.
- A bumped `pipeline_version` in code automatically invalidates all caches for the next run on each affected ad.
- Stage outputs older than the most recent config change for that stage (e.g., new VLM model) are treated as stale.

This is "resume-from-failure," not full event sourcing. Good enough for a demo and for re-running ads after a model swap.

SSE stream:

- `GET /api/jobs/{job_id}/events` reads from the event log and pushes new events.
- Each event: `{state, progress, message, ts}`.
- Closes when state reaches a terminal value (`done | failed | cancelled`).

Run:

```bash
python -m ad_classifier api      # FastAPI on :8000
python -m ad_classifier worker   # worker loop
```

Optionally bundle both behind a `tasks.py` runner.

Tests: state transitions, cancellation, progress event ordering, exception capture.

---

## P. Storage Layout

Predictable on-disk paths so the frontend can construct URLs deterministically.

```
data/
  uploads/{ad_id}/source.mp4
  frames/{ad_id}/frame_NNN_tNNNNms.png
  audio/{ad_id}/audio.wav
  whisper/{ad_id}/whisper.json
  out/{ad_id}/result.json
  out/{ad_id}/evidence_bundle.json

ad_classifier.db          # SQLite metadata + sqlite-vec vectors
qdrant_db/                # only when QdrantStore selected
config.yaml
taxonomy.yaml
prompts/gemma_ad_verifier.txt
```

`ad_id` format: `ad_{8-char-base32-of-uuid4}`.

All path construction must live in a single `paths.py` module; never hand-build paths inline.

---

## Q. Category Taxonomy

Demo taxonomy — flat ~15 categories with orthogonal risk labels. Configurable via `taxonomy.yaml` so users can extend without code changes.

```yaml
categories:
  - id: retail_ecommerce
    sensitive: false
  - id: food_beverage
    sensitive: false
  - id: health_wellness
    sensitive: true
  - id: beauty_personal_care
    sensitive: false
  - id: finance_banking
    sensitive: true
  - id: crypto_investment
    sensitive: true
  - id: gambling
    sensitive: true
  - id: mobile_apps_games
    sensitive: false
  - id: streaming_entertainment
    sensitive: false
  - id: automotive
    sensitive: false
  - id: travel_hospitality
    sensitive: false
  - id: education
    sensitive: false
  - id: real_estate
    sensitive: false
  - id: political
    sensitive: true
  - id: other
    sensitive: false

risk_labels:
  - deceptive_urgency
  - unverified_health_claim
  - guaranteed_returns
  - before_after
  - targeting_minors
  - regulated_substance
  - brand_impersonation
  - hidden_disclaimer
  - price_manipulation
  - false_scarcity
```

Behaviour:

- Loaded at startup; the Gemma prompt template is rendered with the allowed labels so the model only outputs values from this list.
- Unknown labels in VLM output are dropped with a warning (recorded in `debug.dropped_labels`).
- Sensitive categories use `decision.sensitive_review_threshold` instead of `auto_allow_threshold`.

---

## R. CLI

The CLI is **tiered**. Build R.1 first, R.2 as needed, R.3 only when implementing or debugging the corresponding stage. Most production use goes through the API, not the CLI — the user flow is `frontend upload → API → worker`, not `CLI ingest`.

### R.1 Operational (required)

The system cannot run without these:

```bash
python -m ad_classifier init-db                     # create schema, enable WAL, load sqlite-vec
python -m ad_classifier api --host 127.0.0.1 --port 8000
python -m ad_classifier worker
```

### R.2 Diagnostic (recommended)

Worth keeping for debugging and demo storytelling:

```bash
python -m ad_classifier test-amd-paddle --image ./frames/frame_000_t0000ms.png
python -m ad_classifier bench-vectors --backend sqlite-vec --n 1000  # the "scalability flex"
python -m ad_classifier agent show-tools             # print agent tool catalog
python -m ad_classifier agent show-schema            # print schema summary fed to Gemma
python -m ad_classifier agent ask "How many ads in Jeep Freedom Days?"
```

### R.3 Per-stage / dev (optional)

Useful while building each stage in isolation. Drop them once the stage is wired into the API and tested. **Do not pre-build all of these** — add a command when you actually want to run that stage from the terminal.

```bash
python -m ad_classifier ingest          --video ./samples/ad.mp4 --ad-id ad123
python -m ad_classifier build-manifest  --frames ./frames --transcript ./whisper.json --out ./out/manifest.json
python -m ad_classifier preprocess      --manifest ./out/manifest.json --out ./out/preprocessed.json
python -m ad_classifier ocr             --manifest ./out/preprocessed.json --out ./out/ocr.json --device cpu
python -m ad_classifier classify        --ad-id ad123 --config ./config.yaml
python -m ad_classifier dedup-check     --video ./samples/ad.mp4
python -m ad_classifier compare-ads     ad_42 ad_43
python -m ad_classifier search hybrid   --query "no credit check loan financing" --filter category=finance_banking --k 10
python -m ad_classifier vectors index   --ad-id ad123
python -m ad_classifier vectors search  --query "no credit check loan"
python -m ad_classifier campaigns discover
python -m ad_classifier campaigns list
python -m ad_classifier agent repl
```

The `classify` command runs the whole cascade from a manifest. The full user flow goes through `ingest` → enqueue job → worker (or `api` + frontend upload).

---

## S. AMD / ROCm Paddle Test Helper

Diagnostic command that checks:

1. ROCm visibility where available.
2. Whether PaddlePaddle is compiled with ROCm.
3. Whether `paddle.device.set_device("gpu:0")` works.
4. Whether a minimal tensor operation runs.
5. Whether PaddleOCR runs on a provided image with `device="gpu:0"`.

Prints a clear table:

- `rocm_smi_available`
- `paddle_import_ok`
- `paddle_version`
- `compiled_with_rocm`
- `gpu_device_set_ok`
- `paddle_run_check_ok`
- `paddleocr_import_ok`
- `paddleocr_inference_ok`

Explains likely causes:

- ROCm not installed or GPU not supported (RDNA3/gfx1100 has limited Windows support).
- Wrong PaddlePaddle wheel.
- PaddleOCR installed but PaddlePaddle is CPU-only.
- PaddleOCR/PaddleX compatibility issue.

**This is a diagnostic, not a requirement.** The default deployment uses `device: cpu` for PaddleOCR. AMD GPU support is best-effort.

Do not make AMD GPU required for normal tests.

---

## T. Config

**Loading and validation:**

- Use **Pydantic Settings** (`pydantic-settings`) to define a `Settings` model that mirrors the YAML structure with explicit types and field validators.
- Load order: `config.yaml` → environment variables (override) → CLI flags (override).
- **Fail fast**: validation runs at startup. Any missing required field, type mismatch, unknown field, or out-of-range value raises and exits with a clear error pointing to the offending key. No partial-config behavior.
- `pipeline_version` is read from the package's `__version__` (e.g., `ad_classifier.__version__`) and stamped into every classification row — not a config field.
- `vlm.prompt_version` is read from a comment header at the top of `prompts/gemma_ad_verifier.txt` (e.g., `# version: verifier-2026.05.01`) at startup; bumping the prompt requires bumping the version header.

Sample `config.yaml`:

```yaml
paths:
  data_root: ./data
  uploads: ./data/uploads
  frames: ./data/frames
  audio: ./data/audio
  whisper: ./data/whisper
  out: ./data/out
  sqlite_path: ./ad_classifier.db
  qdrant_path: ./qdrant_db

ingest:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe
  frame_interval_ms: 500
  audio_sample_rate: 16000

whisper:
  backend: whisper_cpp          # whisper_cpp | faster-whisper | mock
  model: tiny.en                # whisper.cpp: tiny.en/base.en/etc; faster-whisper: tiny/base/small/medium/large-v3
  compute_type: int8            # faster-whisper only
  language: null                # null = auto-detect
  whisper_cpp:
    command: ./tools/whisper.cpp/whisper-cli.exe
    model_path: ./models/whisper/ggml-tiny.en.bin
    use_gpu: true
    device: 0                   # Vulkan0 = AMD Radeon RX 7900 XT on the tested machine
    threads: 8
    extra_args: []

preprocess:
  blur_threshold: 80
  phash_distance_threshold: 6
  image_diff_threshold: 0.08

ocr:
  engine: paddleocr             # paddleocr | mock
  device: cpu
  min_confidence: 0.70

paddlevl:
  enabled: false
  run_on_all_frames: false
  mean_confidence_threshold: 0.70
  item_confidence_threshold: 0.50
  dense_text_char_threshold: 300
  command: "paddlex --pipeline PaddleOCR-VL-native.yaml --input {image_path} --output {output_dir}"

transcript:
  alignment_window_ms: 1500

vlm:
  provider: http
  endpoint: "http://localhost:1234/v1/chat/completions"   # LM Studio default
  model: "gemma-3-12b-it"
  api_key_env: "VLM_API_KEY"
  timeout_seconds: 120
  max_frames_in_bundle: 12

decision:
  auto_allow_threshold: 0.30
  auto_flag_threshold: 0.75
  sensitive_review_threshold: 0.20

embeddings:
  text:
    model: sentence-transformers/all-MiniLM-L6-v2
    device: cpu
  image:
    model: google/siglip2-base-patch16-224
    device: cpu

vector_store:
  backend: sqlite-vec           # sqlite-vec | qdrant
  text_dim: 384                 # must match embeddings.text model
  visual_dim: 768               # must match embeddings.image model
  qdrant:
    url: "http://localhost:6333"

# A1 Duplicate / similar-ad detection
dedup:
  skip_on_exact: true                  # short-circuit on file-hash match
  skip_on_near_duplicate: false        # demo default false; conservative
  phash_distance_threshold: 4

similarity:
  related_threshold: 0.85
  near_duplicate_threshold: 0.95
  same_campaign_threshold: 0.85
  related_top_k: 5
  modality_weights:
    visual: 0.5
    text: 0.5
  verdicts:
    near_duplicate:
      min_overall: 0.95
      requires_no_field_diff: true
    same_campaign_different_sku:
      min_overall: 0.85
      brand_match: true
      differs_in: ["products"]
    same_campaign_different_offer:
      min_overall: 0.85
      brand_match: true
      differs_in: ["offers"]
    similar_messaging_different_brand:
      min_overall: 0.85
      modality: text
      brand_match: false
    related:
      min_overall: 0.70
    unrelated:
      min_overall: 0.0

taxonomy:
  path: ./taxonomy.yaml

api:
  host: 127.0.0.1
  port: 8000
  cors_origins:
    - http://localhost:5173
  upload:
    max_bytes: 209715200        # 200 MB
    allowed_mime:
      - video/mp4
      - video/quicktime
      - video/webm

worker:
  poll_interval_ms: 1000
  concurrency: 1

# Campaigns auto-discovery
campaigns:
  discover:
    lookback_days: 90
    min_cluster_size: 3
    min_mean_similarity: 0.75
    clusterer: hdbscan          # hdbscan | agglomerative
    name_template: "{brand} {month} {year}"

# Hybrid search
hybrid_search:
  oversample: 4                 # multiplier for k when retrieving from each source
  rrf_k: 60
  weights:
    bm25: 1.0
    text_vec: 1.0
    visual_vec: 0.5

# NL Query Agent
agent:
  enabled: true
  tool_call_format: openai_tools   # openai_tools | json_tagged | mock
  max_session_turns: 20
  tool_row_cap: 50
  history_turns_in_prompt: 10
  schema_summary_path: ./prompts/agent_schema_summary.txt   # auto-generated at startup
  system_prompt_path: ./prompts/gemma_agent_system.txt
  read_only_pragma: true
```

---

## U. Documentation

README must cover:

- architecture diagram in text (ASCII)
- install instructions (Python, ffmpeg, optional Qdrant binary, optional Datasette)
- example input video
- CLI examples
- how to run with mock components
- how to install PaddleOCR
- how to configure PaddleOCR-VL
- how to point at a local Gemma endpoint in LM Studio (model loading, vision projector, port `1234`)
- how to run the API + worker + frontend (reference frontend stack: Vite + React + TS + Tailwind + shadcn/ui; auto-generate the TS client from `/openapi.json` via `openapi-typescript-codegen`)
- **how to use the NL agent** — sample questions, what each tool does, how to read tool-call traces
- **how to discover and curate campaigns** — auto-discovery + manual API
- how to inspect the database with Datasette: `pip install datasette && datasette serve ad_classifier.db -o`
- how to test AMD/ROCm Paddle support
- output JSON example
- known limitations

### U.1 API request / response examples

The README must include concrete `curl` + JSON examples for every primary endpoint so a frontend developer (or AI assistant scaffolding the UI) can generate code without reading the OpenAPI spec by hand.

**Upload + start classification**

```bash
curl -X POST http://localhost:8000/api/ads/upload \
  -F "file=@samples/finance_short.mp4"
```

```json
{
  "ad_id": "ad_a3b9k2x7",
  "job_id": "job_01HF7Z8K9NQX",
  "status": "queued"
}
```

**Stream job progress (SSE)**

```bash
curl -N http://localhost:8000/api/jobs/job_01HF7Z8K9NQX/events
```

```text
data: {"type": "state", "state": "extracting",  "progress": 0.10, "message": "frame 6/45"}
data: {"type": "state", "state": "ocr",         "progress": 0.55, "message": "frame 9/14 keyframes"}
data: {"type": "state", "state": "vlm",         "progress": 0.90, "message": "calling Gemma"}
data: {"type": "state", "state": "done",        "progress": 1.00, "message": null}
```

**List ads with filters**

```bash
curl "http://localhost:8000/api/ads?category=finance_banking&decision=review&limit=20"
```

```json
{
  "items": [
    {
      "ad_id": "ad_a3b9k2x7",
      "brand_name": "fastloan",
      "primary_category": "finance_banking",
      "decision": "review",
      "confidence": 0.62,
      "ingested_at": "2026-05-06T14:32:11Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

**Get ad detail (full classification + marketing entities + related)**

```bash
curl http://localhost:8000/api/ads/ad_a3b9k2x7
```

```json
{
  "ad_id": "ad_a3b9k2x7",
  "primary_category": "finance_banking",
  "decision": "review",
  "confidence": 0.62,
  "risk_labels": ["deceptive_urgency", "guaranteed_returns"],
  "marketing_entities": { "brand": {"name": "fastloan", "...": "..."}, "...": "..." },
  "related_ads": {
    "exact_duplicate_of": null,
    "near_duplicate_of": null,
    "semantically_similar": [
      {"ad_id": "ad_xx12yz34", "overall_score": 0.87, "verdict": "similar_messaging_different_brand"}
    ]
  },
  "evidence": [ {"time_ms": 2400, "source": "ocr", "text": "no credit check", "...": "..."} ]
}
```

**Find similar ads**

```bash
curl "http://localhost:8000/api/ads/ad_a3b9k2x7/similar?k=5"
```

```json
{
  "items": [
    {"ad_id": "ad_xx12yz34", "overall_score": 0.87, "visual_score": 0.82,
     "text_score": 0.91, "verdict": "similar_messaging_different_brand",
     "differences": [{"field": "brand", "left": "fastloan", "right": "quickcash"}]}
  ]
}
```

**Hybrid search**

```bash
curl "http://localhost:8000/api/search?q=no+credit+check+loan&modality=hybrid&k=10"
```

**Ask the NL agent**

```bash
curl -X POST http://localhost:8000/api/agent/sessions
# returns {"session_id": "sess_01HF80..."}

curl -N -X POST http://localhost:8000/api/agent/sessions/sess_01HF80.../query \
  -H "Content-Type: application/json" \
  -d '{"message": "How many ads in Jeep Freedom Days mention financing?"}'
```

```text
data: {"type": "tool_call", "name": "get_campaign", "args": {"name": "Jeep Freedom Days"}}
data: {"type": "tool_result", "name": "get_campaign", "rows": 10, "truncated": false}
data: {"type": "tool_call", "name": "hybrid_search", "args": {"query": "financing apr loan", "filter": {"campaign_id": "c_jeep_freedom_2026"}}}
data: {"type": "tool_result", "name": "hybrid_search", "rows": 4, "truncated": false}
data: {"type": "token", "text": "4 of the 10 ads in "}
data: {"type": "token", "text": "Jeep Freedom Days mention financing..."}
data: {"type": "done"}
```

**Discover campaigns**

```bash
curl -X POST http://localhost:8000/api/campaigns/discover
```

```json
{
  "proposals": [
    {"name": "Jeep Freedom Days", "brand": "jeep", "ad_count": 10,
     "mean_similarity": 0.84, "ad_ids": ["ad_aa...", "ad_bb..."]}
  ]
}
```

**Common error response (RFC 7807)**

```json
{
  "type": "https://example.com/probs/invalid-mime",
  "title": "Unsupported file type",
  "status": 415,
  "detail": "Expected video/mp4|video/quicktime|video/webm; got text/plain",
  "instance": "/api/ads/upload"
}
```

These examples should be auto-tested by the API test suite (TestClient) so they can never silently drift from reality.

---

## V. Tests

Cover:

- filename parsing
- manifest building
- transcript loading
- frame/transcript alignment
- dedup/keyframe logic
- OCR interface using mock
- PaddleOCR-VL gating
- rules engine
- VLM JSON parsing (valid + invalid + missing marketing entities)
- final decision aggregation
- marketing entity extraction parsing + DB round-trip
- embedding generation with mocks
- vector store CRUD (parametrized over `SqliteVecStore` and `QdrantStore`)
- similarity queries
- SQLite migrations
- HTTP API (TestClient): upload, list, detail, similar, SSE
- worker state machine + cancellation
- ingest stage with mock ffmpeg/Whisper
- campaign auto-detection clustering (synthetic vectors with known clusters)
- campaign user CRUD via API
- FTS5 indexing + maintenance on classification updates and ad deletion
- hybrid search RRF correctness against synthetic adversarial cases
- NL agent: each tool in isolation; full agent loop with mock LM Studio; SSE event ordering; read-only enforcement; truncation reporting
- `compare_ads` tool: known synthetic vectors + structured field diffs → expected verdicts
- A1 dedup layers: file-hash short-circuit, phash near-duplicate, vector similarity verdicts
- A1 verdict assignment: most-specific verdict wins per priority order
- SigLIP 2 embedder swap (mocked), vector_store dims align with embedding model
- brand normalization: case insensitivity, trademark stripping, alias resolution, agent filter round-trip
- projection write-back: brand_name / products_text / decision populated from marketing entities
- CLI smoke tests where practical

Use mocks for heavy models (PaddleOCR, SigLIP 2, sentence-transformers, Gemma).

### V.1 Test fixtures

Commit a small, deliberate set of fixtures under `tests/fixtures/` and `samples/`:

**Synthetic image fixtures** (generated by a `conftest.py` helper, not committed):
- 3 blank/near-blank frames (different luma)
- 3 blurred frames (Gaussian blur applied to a base image)
- 5 frames identical except for small color shift (phash dedup boundary cases)
- 2 frames with high contrast text overlay (OCR happy path)
- 2 frames with small disclaimer text (OCR hard case for VL gating)

**Sample mp4s** (committed under `samples/`):
- `samples/finance_short.mp4` — 8s, deliberate "no credit check / instant approval" overlay → triggers financial rules + sensitive review
- `samples/health_short.mp4` — 10s, "lose 20 lbs in 30 days / before-after" → triggers health rules
- `samples/benign_short.mp4` — 6s, generic retail product, no risk signals → expected `decision=allow`
- `samples/jeep_a.mp4` and `samples/jeep_b.mp4` — same campaign, different SUV → exercises A1.3 similar-ad detection + `compare_ads` verdict `same_campaign_different_sku`

Each sample mp4 has an `expected.json` next to it with the canonical `FinalAdClassification` shape (with regex/contains fields where exact text would be brittle). The end-to-end smoke test asserts each sample's classification matches its `expected.json`.

**Whisper JSON fixtures**:
- one in Shape 1 (segments wrapper, seconds) → for unit-testing the loader
- one in Shape 2 (flat array, milliseconds) → same
- one with overlapping segments → alignment edge case

**Vector fixtures** (created in `conftest.py`, not committed):
- 100 known synthetic vectors with planted clusters → test campaign auto-discovery clustering
- adversarial pairs for hybrid search RRF (one source ranks doc high, the other low)
- vectors with known cosine distances → verify `compare_ads` verdict assignment

**Agent fixtures**:
- pre-canned mock LM Studio responses for: simple list, simple count, multi-tool loop, malformed tool call (retry path), `sql_readonly` write attempt (must fail).

Fixtures must be small enough that the full test suite runs in under 30 seconds without GPU and without LM Studio.

---

## W. Acceptance Criteria

The task is complete when:

1. `ingest` turns a sample mp4 into frames + audio + whisper.json end-to-end.
2. `classify` runs end-to-end using mock OCR, mock embeddings, and mock VLM.
3. PaddleOCR integration is implemented with lazy imports, CPU default.
4. PaddleOCR-VL fallback exists and is gated.
5. Whisper transcript alignment works.
6. Marketing entities are extracted and persisted.
7. Embeddings are computed and stored in the configured vector store.
8. Similarity search returns ranked results in both backends.
9. SQLite schema is created via `init-db`, with WAL enabled and sqlite-vec loaded.
10. FastAPI exposes upload + list + detail + similar + SSE; OpenAPI at `/docs`.
11. Worker process consumes jobs and updates progress live.
12. Final classification result is strict JSON.
13. Tests cover the main pipeline; pass without GPU and without an LM Studio instance.
14. README explains local usage.
15. **Campaign auto-discovery** runs on demand and produces non-empty proposals on a corpus with a deliberately-shared brand. User CRUD on campaigns works via API.
16. **Hybrid search** combines BM25 + vector results with RRF and respects filters consistently across both retrievers.
17. **NL agent** answers `"How many ads in campaign {X}?"` and `"Show me ads similar to {ad_id}"` end-to-end, with tool-call audit trail in `agent_messages`. Read-only enforcement is verified.
18. **A1 dedup detection** triggers on identical re-uploads (file-hash) and near-duplicate creatives (phash); the post-embedding `related_ads` block is populated for at least one fixture pair.
19. **`compare_ads` tool** returns the documented `{overall_score, visual_score, text_score, differences, verdict}` shape and selects the correct verdict from the config table for each test case.
20. **SigLIP 2** is the default image embedder in config and code; vector dims align with model output.
21. The code is formatted (ruff/black) and tests pass.

After implementing:

- Show the final file tree.
- Summarize important design decisions.
- List commands to run tests.
- List commands to run a local example end-to-end (ingest → classify → api).
- List any dependencies the user must install manually (ffmpeg, optional Qdrant binary, optional PaddleOCR).

---

## X. Campaigns

A campaign groups multiple ads under one named promotion (e.g., "Jeep Freedom Days" containing 10 vehicle ads). The NL agent (section Z) relies on this concept; dashboards filter by it.

### X.1 Data model

```python
class Campaign(BaseModel):
    id: str                              # "c_jeep_freedom_2026"
    name: str                            # "Jeep Freedom Days"
    advertiser: str | None               # "Stellantis"
    brand: str | None                    # "Jeep"
    theme: str | None                    # "summer sales event"
    start_date: date | None
    end_date: date | None
    created_by: Literal["auto", "user"]
    description: str | None
    created_at: datetime

class AdCampaign(BaseModel):
    ad_id: str
    campaign_id: str
    similarity_score: float | None       # only when auto-assigned
    assigned_by: Literal["auto", "user"]
    assigned_at: datetime
```

Persisted in `campaigns` and `ad_campaigns` (section M).

### X.2 Auto-detection

Implement on-demand campaign discovery (not run during ingest):

1. Pull all ads with `brand_name IS NOT NULL` from the last N days (configurable, default 90).
2. Group by `brand_name`.
3. Within each brand group, cluster ad-level visual embeddings (`ads_visual` collection) with HDBSCAN. Fallback to agglomerative clustering if HDBSCAN unavailable.
4. For each cluster of ≥ 3 ads with mean pairwise CLIP similarity ≥ 0.75, propose a campaign:
   - name: derived from common offer text (`offers.value`) or shared scarcity/urgency phrases; fall back to `"{brand} {start_month} {year}"`.
   - brand: cluster's brand.
   - start_date / end_date: min / max `ads.ingested_at` in cluster.
   - description: top common rule_triggers + product list.
5. Write to `campaigns` with `created_by='auto'`, link members in `ad_campaigns` with `assigned_by='auto'` and `similarity_score`.
6. Auto-discoveries do not overwrite user-curated campaigns. If an ad is already in a user campaign, skip it.

### X.3 Manual curation

Users can create, rename, merge, split, and delete campaigns and assign/unassign ads via API (section N additions below).

### X.4 API endpoints (extends section N)

| Method | Path | Purpose |
|---|---|---|
| GET    | `/api/campaigns`                          | list campaigns with filters: `brand`, `created_by`, `q` |
| POST   | `/api/campaigns`                          | create user campaign |
| GET    | `/api/campaigns/{id}`                     | detail + ad list |
| PATCH  | `/api/campaigns/{id}`                     | rename / edit metadata |
| DELETE | `/api/campaigns/{id}`                     | delete (cascades `ad_campaigns`) |
| POST   | `/api/campaigns/{id}/ads`                 | bulk assign ad_ids |
| DELETE | `/api/campaigns/{id}/ads/{ad_id}`         | unassign one ad |
| POST   | `/api/campaigns/discover`                 | run auto-detection (returns proposed campaigns + counts) |
| POST   | `/api/campaigns/discover/accept`          | accept a subset of proposals |

### X.5 Tests

- HDBSCAN clustering with synthetic CLIP-like vectors and known clusters.
- Brand grouping correctness.
- User campaigns shielded from auto-discovery.
- Cascade behavior on ad deletion.

---

## Y. Hybrid Search (FTS5 + sqlite-vec + RRF)

Local replacement for Redis FT.HYBRID. Combines BM25 keyword search and vector ANN with reciprocal rank fusion. Runs entirely in-process against the existing SQLite DB.

### Y.1 Components

- **BM25 keyword**: SQLite FTS5 virtual table `ads_fts` (created in section M).
- **Vector ANN**: `VectorStore.search` over `ads_text` and/or `ads_visual` collections (section L).
- **Fusion**: Reciprocal Rank Fusion in Python with configurable `k` constant (default 60).

### Y.2 API

```python
class HybridSearch:
    def search(
        self,
        query_text: str,
        query_text_vec: list[float] | None = None,
        query_visual_vec: list[float] | None = None,
        k: int = 10,
        filter: dict | None = None,
        weights: dict | None = None,        # e.g. {"bm25": 1.0, "text_vec": 1.0, "visual_vec": 0.5}
        rrf_k: int = 60,
    ) -> list[HybridHit]:
        ...
```

Behaviour:

1. Run each enabled retriever (BM25, text vector, visual vector) with the same `filter` and an oversample factor (e.g. retrieve 4 × k from each).
2. Compute per-retriever ranks.
3. RRF combine: `score(d) = Σ w_i / (rrf_k + rank_i(d))`.
4. Return top-k merged hits with per-retriever ranks and the fused score.

### Y.3 FTS5 maintenance

- `ads_fts` is contentless and managed manually.
- Insert at `finalize` worker stage from concatenated transcript + OCR + marketing entities text.
- `DELETE FROM ads_fts WHERE ad_id = ?` on ad deletion (handled by repository).
- `INSERT OR REPLACE` on classification updates.

### Y.4 CLI

```bash
python -m ad_classifier search hybrid \
  --query "no credit check loan financing" \
  --filter category=finance_banking \
  --k 10
```

### Y.5 Tests

- BM25 only with a known corpus.
- Vector only with mock vectors.
- RRF correctness on adversarial cases (one source ranks doc high, the other low).
- Filter consistency (same filter applied to both retrievers).

### Y.6 Scale path

When the corpus grows past ~100k ads or hybrid latency becomes user-perceptible, swap to **Qdrant native binary** (sparse + dense vectors) or **Postgres + pgvector + tsvector**. Both are drop-in via the `VectorStore` protocol plus an FTS adapter; no application code change.

---

## Z. NL Query Agent (Tool-calling Gemma)

A conversational agent that answers natural-language questions about the database. Powered by Gemma function-calling via LM Studio. **This is a primary demo feature.**

### Z.1 Tool catalog

The agent calls tools, not raw SQL. Each tool has a strict schema; the underlying queries are parameterized templates.

```python
TOOLS = [
    list_ads(filter, limit=20, offset=0),
        # filter keys: brand, category, decision, risk_label, campaign_id, date_from, date_to, q
    get_ad_detail(ad_id),
    count_ads(filter),
    list_campaigns(filter, limit=20),
        # filter keys: brand, created_by, q
    get_campaign(campaign_id_or_name),
        # returns campaign + member ads
    full_text_search(query, k=10, filter=None),
    vector_similarity(ad_id_or_text, k=10, modality="text|visual", filter=None),
    hybrid_search(query, k=10, filter=None),
    aggregate(group_by, metric, filter=None),
        # group_by: brand|category|decision|risk_label|campaign
        # metric: count|avg_confidence|sum_duration_ms
    compare_ads(ad_id_a, ad_id_b),
        # returns: {overall_score, visual_score, text_score, differences[], verdict}
        # combines vector cosine (per modality) + structured field diff (brand,
        # products, offers, ctas, disclaimers) + verdict from similarity.verdicts
        # config table. Lets the agent answer "are these two the same ad?" with
        # both a quantitative score AND a qualitative description of what differs.
    sql_readonly(sql),
        # escape hatch; read-only connection; capped at 50 rows; logged
]
```

Each tool returns JSON capped at ~50 rows. Truncation is reported in the tool result so the agent can ask for refinement instead of dumping the DB.

### Z.2 Conversation flow

1. User sends a message via `POST /api/agent/query` (or follows up in an existing session).
2. Agent loads session history from `agent_messages` (last N turns) and the system prompt with the tool catalog and schema summary.
3. Calls Gemma via LM Studio with OpenAI-style `tools` parameter.
4. Loops: model emits a tool call → server executes → result appended → model called again → eventually final assistant text.
5. Each step (user, assistant, tool) is persisted to `agent_messages`.
6. Final assistant text streamed to client via SSE.

Reference resolution ("that campaign", "the second one") is the model's responsibility, supported by recent message history in the prompt.

### Z.3 Guardrails

- **Read-only DB connection** for the agent (separate SQLAlchemy engine with `query_only=ON` pragma on SQLite, or `default_transaction_read_only=on` on Postgres if swapped).
- **Schema summary** baked into the system prompt — the agent sees the full table list, columns, and types.
- **Tool output cap** of 50 rows; agent must paginate or refine if truncated.
- **Session limit**: max N turns per session (default 20) to prevent runaway loops.
- **PII in messages**: do not log full mp4 paths in agent_messages; redact to `ad_id` only.
- **Audit**: every tool call recorded with args and result hash.

### Z.4 Prompt template

Saved as `prompts/gemma_agent_system.txt`:

```text
You are a helpful analyst answering questions about a local database of classified video ads.

You have read-only access to the following schema:
{SCHEMA_SUMMARY}

You can call these tools:
{TOOL_CATALOG}

Rules:
- Prefer structured tools (list_ads, count_ads, get_campaign, aggregate) over sql_readonly when possible.
- Always cite ad_ids and campaign_ids in your answer when referencing specific records.
- If a tool returns truncated results, ask the user to narrow the filter or call again with pagination.
- Never fabricate ad_ids, brand names, or counts. If you don't know, call a tool.
- For counting questions, use count_ads or aggregate, not list_ads.
- For "similar to X" questions, use vector_similarity.
- For free-form questions mixing keywords and meaning, use hybrid_search.
- Keep answers under 200 words unless the user asks for detail.
- Reply in plain text. No markdown unless the user requests a table.
```

Schema summary and tool catalog are rendered into the prompt at startup from the live DB and tool registry — never hand-maintained.

### Z.5 API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST   | `/api/agent/sessions`                  | create session, returns `{session_id}` |
| GET    | `/api/agent/sessions`                  | list sessions |
| GET    | `/api/agent/sessions/{id}`             | session metadata + last N messages |
| POST   | `/api/agent/sessions/{id}/query`       | send message; SSE stream of assistant tokens + tool-call events |
| DELETE | `/api/agent/sessions/{id}`             | delete session and messages |

SSE events emitted during a query:
- `{"type": "tool_call", "name": "...", "args": {...}}`
- `{"type": "tool_result", "name": "...", "rows": N, "truncated": bool}`
- `{"type": "token", "text": "..."}`
- `{"type": "done"}`

The frontend chat panel displays tool calls inline so users see *how* the agent answered, not just the final text.

### Z.6 CLI

```bash
python -m ad_classifier agent ask "How many cars are in Jeep Freedom Days?"
python -m ad_classifier agent repl                   # interactive REPL
python -m ad_classifier agent show-tools             # print tool catalog
python -m ad_classifier agent show-schema            # print schema summary as fed to Gemma
```

### Z.7 Tests

- Each tool tested in isolation against a fixture DB (with mocked vector store + LLM).
- Mock LM Studio response for the full agent loop: user → tool_call → tool_result → final.
- SSE event ordering for `/query`.
- Read-only enforcement: attempting `INSERT`/`UPDATE`/`DELETE` via `sql_readonly` must fail.
- Truncation reporting when a tool exceeds 50 rows.
- Session persistence and reload.

### Z.8 Token usage observability

`agent_messages.tokens_in` and `agent_messages.tokens_out` are populated for every assistant turn (LM Studio reports `usage` in its OpenAI-compatible responses). Expose two read endpoints and one CLI:

```
GET  /api/agent/usage                       # totals + per-day buckets, last 30 days
GET  /api/agent/sessions/{id}/usage         # totals for one session
```

```bash
python -m ad_classifier agent usage          # human-readable summary, last 7 days
python -m ad_classifier agent usage --json   # machine-readable
```

Underlying SQL (used by both):

```sql
SELECT
  date(created_at) AS day,
  COUNT(*) FILTER (WHERE role = 'assistant') AS assistant_turns,
  SUM(tokens_in)  AS tokens_in,
  SUM(tokens_out) AS tokens_out,
  COUNT(*) FILTER (WHERE role = 'tool') AS tool_calls
FROM agent_messages
WHERE created_at >= date('now', '-30 days')
GROUP BY 1
ORDER BY 1 DESC;
```

Useful both for cost awareness when LM Studio is loaded and for catching runaway loops (a session with 200 tool calls is a bug).

### Z.9 Notes on Gemma function-calling via LM Studio

LM Studio supports OpenAI-style `tools` parameter for models that advertise function-calling. Gemma 3 12B Instruct works in practice. If the served model emits malformed tool calls:

- Validate the JSON; on parse failure, return a `tool_error` to the model with a brief format reminder and let it retry once.
- After 2 retries, fall back to a conservative response: "I couldn't run that query reliably. Try rephrasing."

Make the tool-call format strategy configurable: `openai_tools` (default), `json_tagged` (model emits `<tool_call>...</tool_call>` blocks), or `mock` (for tests).

---

# Follow-Up Prompt for Codex After First Implementation

Use this after Codex produces the first version:

```md
Review the implementation for production gaps.

Focus on:
1. places where OCR text may be silently overwritten;
2. missing timestamp propagation;
3. weak error handling around PaddleOCR/PaddleOCR-VL;
4. invalid VLM JSON handling;
5. tests that rely on heavy models;
6. places where filesystem order is used incorrectly;
7. missing evidence in final decisions;
8. sensitive-category thresholds;
9. config values that should not be hard-coded;
10. marketing entity hallucinations not grounded in OCR/transcript;
11. embedding path leaks (per-keyframe vectors not deleted with their ad);
12. SSE streams that never close on terminal job states;
13. upload endpoint memory usage on large mp4;
14. CORS misconfigurations;
15. SQLite WAL not enabled on connection.
16. Projection columns (`ads.brand_name`, `products_text`, etc.) drifting from the JSON source of truth.
17. `ads_fts` rows not deleted when an ad is deleted.
18. Auto-discovered campaigns overwriting user-created ones.
19. NL agent calling `sql_readonly` for tasks that have a structured tool — guide it via prompt.
20. Tool results not capped at 50 rows leaking large payloads into LLM context.
21. Agent session history growing unbounded — enforce `max_session_turns`.
22. Schema summary in agent prompt drifting from real schema — must regenerate at startup.

Make minimal patches. Add or update tests for every bug found. Then run the test suite and report the result.
```

---

# Gemma Verifier Prompt Template

Save this as `prompts/gemma_ad_verifier.txt`:

```text
You are an ad-classification verifier and structured-data extractor.

You receive a chronological evidence bundle for one ad. The bundle may include:
- selected image frames;
- frame timestamps;
- OCR text from PaddleOCR;
- optional PaddleOCR-VL corrections or layout output;
- Whisper transcript segments;
- deterministic rule triggers;
- metadata.

Important:
- Treat all frames as one time-ordered ad sequence.
- Do not classify each frame independently.
- Use timestamps.
- Use OCR and transcript as evidence, but verify them against the images when possible.
- Do not silently accept OCR if it appears wrong.
- Do not silently overwrite OCR. If you correct OCR, report both raw OCR and corrected text.
- Spoken claims and written claims are both policy-relevant.
- Disclaimers, small text, prices, health claims, financial claims, and CTAs are important.
- For marketing entities (brand, prices, offers, CTAs, social proof, disclaimers): every value must be grounded in an actual frame or transcript segment. Never fabricate. If you cannot ground it, leave the field null or empty.
- If evidence is ambiguous, choose decision="review".
- Return JSON only. No markdown.

Allowed primary_category values:
{ALLOWED_CATEGORIES}

Allowed risk_labels values:
{ALLOWED_RISK_LABELS}

Sensitive categories (lower review threshold):
{SENSITIVE_CATEGORIES}

Tasks:
1. Determine the primary ad category.
2. Identify policy/risk labels.
3. Verify OCR quality.
4. Identify missing or suspicious text.
5. Resolve conflicts between OCR, transcript, and visible content.
6. Extract marketing entities (brand, products, prices, offers, CTAs, social proof, disclaimers, creative format).
7. Produce timestamped evidence.
8. Decide allow, flag, or review.

Decision definitions:
- allow: no meaningful risk detected and confidence is high.
- flag: clear policy/risk issue with strong evidence.
- review: ambiguous, low confidence, conflicting evidence, poor OCR quality, or sensitive category uncertainty.

Return exactly this JSON shape:

{
  "primary_category": "string",
  "risk_labels": ["string"],
  "confidence": 0.0,
  "decision": "allow|flag|review",
  "needs_human_review": true,
  "ocr_quality": {
    "overall": "good|mixed|poor",
    "possible_errors": [
      {
        "time_ms": 0,
        "frame_index": 0,
        "raw_ocr": "string",
        "corrected_text": "string",
        "confidence": 0.0,
        "reason": "string"
      }
    ],
    "missed_text": [
      {
        "time_ms": 0,
        "frame_index": 0,
        "text": "string",
        "location": "string",
        "confidence": 0.0,
        "reason": "string"
      }
    ]
  },
  "evidence": [
    {
      "time_ms": 0,
      "frame_index": 0,
      "source": "ocr|paddlevl|transcript|visual|rule",
      "text": "string",
      "reason": "string",
      "confidence": 0.0
    }
  ],
  "marketing_entities": {
    "brand": {
      "name": "string|null",
      "logo_present": false,
      "logo_evidence": [
        {"time_ms": 0, "frame_index": 0, "reason": "string"}
      ],
      "tagline": "string|null"
    },
    "products": ["string"],
    "prices": [
      {
        "amount": 0.0,
        "currency": "string",
        "frame_index": 0,
        "time_ms": 0,
        "discounted_from": null,
        "discount_pct": null
      }
    ],
    "offers": [
      {
        "type": "bogo|free_trial|percent_off|flat_off|bundle|giveaway|other",
        "value": "string",
        "expiry_text": "string|null",
        "expiry_resolved": "YYYY-MM-DD|null",
        "promo_code": "string|null",
        "scarcity_signals": ["string"],
        "urgency_signals": ["string"]
      }
    ],
    "ctas": [
      {
        "text": "string",
        "destination_hint": "string|null",
        "time_ms": 0,
        "frame_index": 0
      }
    ],
    "social_proof": {
      "rating": null,
      "rating_count": null,
      "testimonials": ["string"],
      "badges": ["string"]
    },
    "disclaimers": [
      {
        "text": "string",
        "time_ms": 0,
        "frame_index": 0,
        "is_small_print": true
      }
    ],
    "creative_format": {
      "aspect_ratio": "1:1|9:16|16:9|4:5",
      "duration_ms": 0,
      "has_voiceover": true,
      "has_on_screen_text": true
    }
  },
  "conflicts": [
    {
      "description": "string",
      "sources": ["string"],
      "resolution": "string"
    }
  ],
  "summary": "string"
}
```
