# ARGUS — Ad Retrieval, Graphing & Understanding System

Local-first multimodal ad classification with structured marketing-entity extraction, embeddings + hybrid search, campaign tracking, and an interactive NL agent — all backed by a single SQLite database.

## Quick Start

```powershell
# 1. Clone and create venv
git clone https://github.com/LordLoras/adscope-local.git
cd adscope-local
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install core dependencies (no GPU required for CPU-only)
pip install -e .
pip install -e ".[dev]"

# 3. Install optional components as needed:
pip install -e ".[ocr]"        # PaddleOCR (CPU-only on Windows)
pip install -e ".[whisper]"    # faster-whisper transcription
pip install paddlepaddle       # required BEFORE paddleocr on Windows

# 4. (Optional) GPU embeddings — requires PyTorch with CUDA/ROCm
#    See "GPU Embeddings" section below. Skip this for CPU-only.

# 5. Create config from template
Copy-Item .\config.example.yaml .\config.yaml

# 6. Download embedding models (first run caches them automatically)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# 7. Initialize database and start
python -m ad_classifier init-db
.\start.bat
```

The API runs on `http://localhost:8000`, the frontend on `http://localhost:5173`.

## Architecture

```
video upload
  → ffmpeg frame extraction + audio
  → whisper transcript
  → frame preprocessing (blank/blur/dedup/scene detection)
  → PaddleOCR (CPU default)
  → optional PaddleOCR-VL (hard frames)
  → transcript alignment
  → deterministic rules engine
  → evidence bundle construction
  → VLM verification + classification (remote or local)
  → final aggregation + marketing-entity extraction
  → text embeddings (MiniLM) + optional visual embeddings (SigLIP 2)
  → SQLite persistence, FTS5, sqlite-vec
  → FastAPI + React frontend
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit. Key sections:

### VLM Endpoint (local or remote)

```yaml
vlm:
  # Flip between local LM Studio and a remote endpoint:
  mode: local   # or "remote"

  local:
    endpoint: "http://127.0.0.1:1234/v1"
    model: "Qwen3.6-27B-Q4_K_M"
    response_format: json_object   # safer for small/quantized local models

  remote:
    endpoint: "https://ai.ipdy.io/v1/"
    model: "unsloth/Qwen3.6-35B-A3B-GGUF"
    api_key_env: "VLM_API_KEY"
    response_format: json_schema   # stronger validation for capable remote models
```

Switching `mode` changes both the VLM and the NL agent endpoint — no need to duplicate settings.

### Visual Embeddings (optional)

```yaml
image_embedder:
  enabled: true    # set to false to skip SigLIP 2 (no torch required)
  model: google/siglip2-base-patch16-224
  device: cpu      # or "cuda" if torch + GPU available
```

When `enabled: false`, the pipeline skips visual embeddings entirely. Text embeddings (MiniLM) still work without torch.

### OCR

```yaml
ocr:
  device: cpu     # PaddleOCR device; AMD GPU is best-effort on Windows
  lang: en
```

PaddleOCR lazy-loads and will error at runtime if not installed. For testing without PaddleOCR, the mock OCR engine is used in unit tests.

## GPU Embeddings (Optional)

The pipeline works fully on CPU. Visual embeddings (SigLIP 2) require PyTorch with GPU support.

**If you have an NVIDIA GPU:**

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

**If you have an AMD GPU (ROCm on Windows):**

The `.venv` may already contain a pre-installed GPU PyTorch build. Do NOT reinstall torch:

```powershell
# Verify existing torch
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"

# If torch is missing, install the ROCm wheel manually, then:
pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

**⚠️ Do not run `pip install torch` — it will replace the GPU wheel with a CPU build.**

Set `image_embedder.enabled: true` and `image_embedder.device: cuda` (or `rocm`) in config.

## Frontend

```powershell
cd frontend
npm install
npm run codegen   # requires backend running at localhost:8000
npm run dev
```

Pages:
- `/library` — ad table with filters, detail drawer, edit/delete
- `/upload` — upload with SSE progress, result panel
- `/search` — keyword / hybrid / vector search
- `/campaigns` — campaign cards and discovery
- `/agent` — NL agent chat (Phase 9)

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/ads/upload` | POST | Upload video, create job |
| `/api/ads` | GET | List ads (filter by brand, category, status, q) |
| `/api/ads/{id}` | GET | Ad detail + classification + marketing entities |
| `/api/ads/{id}/frames` | GET | Frame metadata |
| `/api/ads/{id}/evidence` | GET | Classification + rule evidence |
| `/api/ads/{id}/similar` | GET | Similar ads by embedding |
| `/api/ads/{id}` | PATCH | Update projection fields |
| `/api/search` | GET | FTS / vector / hybrid search |
| `/api/campaigns` | GET | List campaigns |
| `/api/campaigns/discover` | POST | Run campaign clustering |
| `/api/jobs/{id}/events` | GET (SSE) | Real-time job progress |

## CLI Commands

```powershell
python -m ad_classifier init-db        # Create/migrate the SQLite database
python -m ad_classifier api            # Start the FastAPI server
python -m ad_classifier worker         # Start the pipeline worker
python -m ad_classifier version        # Show version + torch status
```

## Testing

```powershell
python -m pytest tests/ -q                                     # all unit tests
python -m pytest tests/ -k "not paddleocr" -q                 # skip PaddleOCR tests
RUN_PADDLEOCR_SMOKE=1 python -m pytest tests/ -k paddleocr   # OCR smoke test (needs PaddleOCR)
```

## Project Structure

```
ad_classifier/
  api/           FastAPI routes and SSE
  cli/           CLI commands (init-db, api, worker)
  config.py      Pydantic config from YAML
  db/            SQLite repos, migrations, FTS5, sqlite-vec
  dedup/         SHA256 + pHash + vector dedup
  diagnostics/   Environment and GPU checks
  embeddings/    MiniLM text + SigLIP 2 visual embedders
  ingest/        ffmpeg, whisper, frame extraction
  marketing/     OCR normalization, offer extraction, brand resolution
  models/        Pydantic models for all pipeline objects
  pipeline/      Evidence bundles, aggregation, rules engine
  search/         FTS5 + vector + hybrid search with RRF
  vlm/            VLM verifier, cleanup, correction, schema, prompt
  worker/         Pipeline runner and stage orchestration
frontend/         Vite + React + TypeScript + Tailwind + shadcn/ui
```

## Troubleshooting

**VLM returns empty response / disconnects:** Check the llama.cpp server timeout. Add `--timeout 600` and `--n-predict 8192` to the server launch command. The generation poll timeout (`should_stop`) kills long-running requests by default.

**PaddleOCR import error:** Run `pip install paddlepaddle paddleocr`. On Windows, install `paddlepaddle` first.

**SigLIP/torch import error:** Either install torch with GPU support, or set `image_embedder.enabled: false` in config to skip visual embeddings entirely.

**`json_schema` response format not working with local model:** Switch to `response_format: json_object` in your local endpoint config. Smaller quantized models often fail with `json_schema` structured output.