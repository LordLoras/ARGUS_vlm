# AdScope Local

Local-first multimodal ad classification, marketing-entity extraction, campaign tracking, and natural-language search over a local SQLite database.

`AdScope Local` is the recommended project name. The Python package and CLI still use the practical internal name `ad-classifier` / `ad_classifier`.

No cloud services are required by default. No Docker is required. The target deployment is Windows with local models, local files, and one SQLite database.

## Current Status

This repository is in early implementation.

Implemented now:

- Python package scaffold
- Dependency pins that preserve the pre-installed ROCm PyTorch wheel
- Torch diagnostics
- SQLite schema migration
- WAL-enabled database initialization
- sqlite-vec load check
- Read-only SQLite connection helper for the future agent
- Initial `AdRepository` and `JobRepository`
- Working `init-db` CLI
- PaddleOCR CPU smoke test
- `whisper.cpp` Vulkan runtime copied locally and tested on RX 7900 XT

Not implemented yet:

- Video ingest pipeline
- API server
- Worker process
- VLM classification
- Embeddings/vector search
- Natural-language agent
- Frontend

Use [STATUS.md](./STATUS.md) as the implementation agenda.

## Hardware And Runtime Notes

This repo is tuned for the current local Windows machine:

- GPU: AMD Radeon RX 7900 XT
- Torch: `2.9.1+rocm7.2.1`
- Whisper: `whisper.cpp` with Vulkan, using `Vulkan0`
- OCR: PaddleOCR on CPU by default
- Database: SQLite with WAL, FTS5, and sqlite-vec
- VLM: Gemma through LM Studio, planned for later phases

## Do Not Reinstall Torch

The `.venv` already contains a manually installed GPU PyTorch build.

Do not run:

```powershell
pip install torch
pip install -U torch
pip install torchvision torchaudio
```

Torch, torchvision, and torchaudio are intentionally omitted from [pyproject.toml](./pyproject.toml). Reinstalling them can replace the ROCm wheel with a CPU wheel.

Verify torch with:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier version
```

Expected shape:

```text
ad-classifier 0.1.0
torch 2.9.1+rocm7.2.1  backend=CUDA/ROCm  gpu=True
```

## Local Model And Tool Paths

The example config defaults to `whisper_cpp`:

```yaml
whisper:
  backend: whisper_cpp
  model: tiny.en
  whisper_cpp:
    command: ./tools/whisper.cpp/whisper-cli.exe
    model_path: ./models/whisper/ggml-tiny.en.bin
    use_gpu: true
    device: 0
```

The local runtime files are intentionally ignored by Git:

```text
tools/whisper.cpp/
models/whisper/
```

`tiny.en` is installed for smoke tests. For better production transcription accuracy, use `small.en` or `medium.en` and update `config.example.yaml` / `config.yaml` accordingly.

## Setup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ad_classifier version
```

If you need to reinstall project dependencies, preserve torch:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install --no-deps "transformers==4.40.2" "sentence-transformers==3.0.1"
.\.venv\Scripts\python.exe -m pip install -e ".[dev,clustering,ocr,whisper]"
```

Then re-check:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ad_classifier version
```

## Configuration

The default config template is [config.example.yaml](./config.example.yaml).

For local overrides:

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

`config.yaml` is ignored by Git.

Important fields:

- `paths.sqlite_path`: SQLite database location
- `whisper.backend`: `whisper_cpp`, `faster-whisper`, or `mock`
- `whisper.whisper_cpp.command`: local `whisper-cli.exe`
- `whisper.whisper_cpp.model_path`: local GGML model
- `ocr.device`: defaults to `cpu`
- `vector_store.backend`: defaults to `sqlite-vec`
- `api.cors_origins`: frontend allowlist, default `http://localhost:5173`

## Commands Available Today

Show version and torch status:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier version
```

Create or migrate the database:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier init-db
```

Use a custom database path:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier init-db --db-path .\data\dev\ad_classifier.db
```

Show CLI help:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier --help
```

Planned commands, not implemented yet:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier api
.\.venv\Scripts\python.exe -m ad_classifier worker
```

## Whisper.cpp Smoke Test

The copied Vulkan build has been tested with the RX 7900 XT. Use any local WAV, MP3, OGG, or FLAC file for a quick check.

```powershell
$audio = "C:\path\to\sample.wav"
.\tools\whisper.cpp\whisper-cli.exe `
  -m .\models\whisper\ggml-tiny.en.bin `
  -f $audio `
  -l en `
  -t 8 `
  -dev 0
```

The log should include:

```text
Vulkan0 = AMD Radeon RX 7900 XT
use gpu    = 1
whisper_backend_init_gpu: using Vulkan0 backend
```

Once Phase 4 adds real ingest tests, a small tracked sample audio fixture should live under `samples/`.

## PaddleOCR Smoke Test

The normal test suite skips heavy OCR inference. To run the optional CPU smoke test:

```powershell
$env:RUN_PADDLEOCR_SMOKE = "1"
.\.venv\Scripts\python.exe -m pytest tests\pipeline\test_paddleocr_cpu_smoke.py -q
```

PaddleOCR is CPU-first on this Windows AMD setup.

## Tests And Quality Checks

Run the default suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run formatting and lint checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m black --check .
```

Current expected result:

```text
9 passed, 1 skipped
```

## Database

`init-db` creates:

- `ads`
- `frames`
- `ocr_items`
- `transcript_segments`
- `rule_triggers`
- `classifications`
- `marketing_entities`
- `jobs`
- `campaigns`
- `ad_campaigns`
- `ads_fts`
- `agent_sessions`
- `agent_messages`

The connection helper enables:

- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`
- `PRAGMA query_only = ON` for read-only agent connections

Inspect a database with Datasette:

```powershell
.\.venv\Scripts\python.exe -m datasette serve .\ad_classifier.db -o
```

## Planned Architecture

```text
video upload
  -> ffprobe and ffmpeg
  -> sampled frames and audio
  -> whisper.cpp transcript
  -> frame preprocessing
  -> PaddleOCR
  -> optional PaddleOCR-VL
  -> transcript alignment
  -> deterministic rules
  -> evidence bundle
  -> Gemma VLM verification
  -> aggregation and review decision
  -> embeddings and hybrid search
  -> SQLite persistence
  -> API, worker, frontend, and NL agent
```

The backend and frontend stay decoupled. The frontend will consume JSON/SSE from FastAPI and should not import backend code or touch SQLite directly.

## API Plan

The planned FastAPI surface includes:

- `POST /api/ads/upload`
- `GET /api/ads`
- `GET /api/ads/{ad_id}`
- `PATCH /api/ads/{ad_id}`
- `DELETE /api/ads/{ad_id}`
- `GET /api/ads/{ad_id}/frames`
- `GET /api/ads/{ad_id}/evidence`
- `GET /api/ads/{ad_id}/similar`
- `GET /api/search`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/events`
- campaign endpoints
- agent endpoints

`PATCH` is for curated corrections. It must update JSON source-of-truth fields, projection columns, and FTS rows in one transaction.

`DELETE` removes the database record and cascaded child rows. Local media artifact deletion should be explicit, not automatic.

## Frontend Plan

The planned frontend stack:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- SSE client for job and agent streams

Primary pages:

- All Ads management page with search, filters, sorting, pagination, edit, and delete
- Upload and job progress page
- Ad detail page or drawer
- Hybrid search page
- Campaign management page
- Agent chat page

## Project Name

Recommended name: `AdScope Local`.

Why:

- It describes the product without sounding like a generic script.
- `Scope` fits classification, evidence review, campaign discovery, and search.
- `Local` communicates the main architectural promise.
- The internal Python name can remain `ad-classifier`, which is clear for packaging and commands.

Other reasonable options:

- `AdLens Local`
- `CreativeScope`
- `AdSift`
- `AdVault`

I would use `AdScope Local` for the README/product and keep `ad-classifier` for the package until there is a reason to rename the Python distribution.

## Repository Map

```text
ad_classifier/
  cli/                 Typer CLI
  db/                  SQLite connection, migrations, repositories
  diagnostics/         Torch and environment checks
  models/              Pydantic models
  pipeline/            Planned pipeline stages
  ingest/              Planned ffmpeg and Whisper backends
  vectors/             Planned vector-store implementations
  vlm/                 Planned Gemma verifier clients
  api/                 Planned FastAPI app
  worker/              Planned job worker

tests/
  cli/
  db/
  diagnostics/
  models/
  pipeline/

config.example.yaml
taxonomy.yaml
STATUS.md
Prompt.md
AGENTS.md
```

## Development Rules

- Keep code local-first.
- Do not add cloud dependencies by default.
- Do not add Docker as a requirement.
- Do not list torch, torchvision, or torchaudio in `pyproject.toml`.
- Lazy-import heavy dependencies such as PaddleOCR, torch, transformers, and sentence-transformers.
- Preserve raw OCR exactly; store corrections separately.
- Keep evidence timestamped and source-tagged.
- Enforce read-only SQLite access for the natural-language agent.
- Keep projection columns in sync with JSON source-of-truth in the same transaction.
