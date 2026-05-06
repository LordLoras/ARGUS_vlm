# AdScope Local

Local-first multimodal ad categorization, marketing-entity extraction, campaign tracking, hybrid search, and a management UI over one SQLite database.

The Python package and CLI are named `ad-classifier` / `ad_classifier`. The product name used in docs and the frontend is `AdScope Local`.

## What Runs Locally

- FastAPI backend on `http://localhost:8000`
- SQLite metadata database with WAL, FTS5, and sqlite-vec
- ffmpeg / ffprobe for video frames and audio
- whisper.cpp or faster-whisper for transcripts
- PaddleOCR CPU by default
- LM Studio OpenAI-compatible Gemma endpoint for VLM verification
- MiniLM text embeddings and SigLIP 2 visual embeddings
- Vite React frontend on `http://localhost:5173`

No cloud services and no Docker are required.

## Current Status

Implemented:

- Ingest, exact/near duplicate checks, manifest, preprocessing, OCR, PaddleOCR-VL gating, rules, evidence bundles
- VLM verifier client with parse-failure fallback
- Final aggregation, marketing-entity persistence, projection columns, FTS refresh
- MiniLM and SigLIP 2 embedding interfaces and sqlite-vec storage
- Hybrid search and similar-ad enrichment
- Campaign discovery and campaign API routes
- FastAPI upload, ad, job/SSE, search, and campaign endpoints
- SQLite-backed worker state machine
- React management UI in [frontend](./frontend)
- AMD/Paddle ROCm diagnostic command

Not yet implemented:

- Phase 9 NL agent backend tool loop and `/api/agent/*` routes
- The LM Studio vision request needs debugging; the last real run reached VLM and received HTTP 400 from LM Studio

## Do Not Reinstall Torch

The `.venv` contains a manually installed GPU PyTorch build for this Windows AMD machine.

Do not run:

```powershell
pip install torch
pip install -U torch
pip install torchvision torchaudio
```

Torch, torchvision, and torchaudio are intentionally omitted from [pyproject.toml](./pyproject.toml). Reinstalling them can replace the ROCm wheel with a CPU build.

Verify the environment:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier version
```

Expected shape:

```text
ad-classifier 0.1.0
torch 2.9.1+rocm7.2.1  backend=CUDA/ROCm  gpu=True
```

## Setup

Use the existing `.venv` when possible:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ad_classifier version
```

If project dependencies need reinstalling, preserve torch:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install --no-deps "transformers==4.57.6" "tokenizers==0.22.1" "sentence-transformers==3.0.1"
.\.venv\Scripts\python.exe -m pip install -e ".[dev,clustering,ocr,whisper]"
```

Create a local config:

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

`config.yaml` is ignored by Git. The default local model is:

```yaml
vlm:
  endpoint:
    endpoint: "http://localhost:1234/v1/chat/completions"
    model: "google/gemma-4-26b-a4b"
```

## Model And Tool Paths

The default Whisper backend is whisper.cpp:

```yaml
whisper:
  backend: whisper_cpp
  whisper_cpp:
    command: ./tools/whisper.cpp/whisper-cli.exe
    model_path: ./models/whisper/ggml-tiny.en.bin
```

Ignored local runtime paths:

```text
tools/whisper.cpp/
models/whisper/
```

Download the embedding models once from Python:

```powershell
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')"
.\.venv\Scripts\python.exe -c "from transformers import AutoModel, AutoProcessor; AutoProcessor.from_pretrained('google/siglip2-base-patch16-224'); AutoModel.from_pretrained('google/siglip2-base-patch16-224')"
```

## Backend Commands

Initialize the database:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier init-db
```

Run the API:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier api --host 127.0.0.1 --port 8000
```

Run the worker:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier worker
```

Run both plus the frontend:

```powershell
.\start.bat
```

## API Examples

Upload and enqueue:

```powershell
curl.exe -X POST http://localhost:8000/api/ads/upload -F "file=@samples/020475556.mp4"
```

List ads:

```powershell
curl.exe "http://localhost:8000/api/ads?limit=20"
```

Read one ad:

```powershell
curl.exe http://localhost:8000/api/ads/ad_4600130f
```

Watch a job over SSE:

```powershell
curl.exe -N http://localhost:8000/api/jobs/job_fcc7ff8ee7e4/events
```

Hybrid search:

```powershell
curl.exe "http://localhost:8000/api/search?q=financing&mode=hybrid&k=10"
```

Campaign discovery:

```powershell
curl.exe -X POST http://localhost:8000/api/campaigns/discover
```

## Frontend

The UI is in [frontend](./frontend). It talks to FastAPI only and has no backend imports or SQLite access.

```powershell
cd .\frontend
npm install
npm run codegen
npm run dev
```

`npm run codegen` reads `http://localhost:8000/openapi.json`, so start the backend first. The app defaults to `VITE_API_BASE_URL=http://localhost:8000`.

Main pages:

- `/library`: table, filters, detail drawer, edit/delete, related ads
- `/upload`: upload, worker progress over SSE, result panel
- `/search`: keyword/text/hybrid search
- `/campaigns`: campaign cards and discovery action
- `/agent`: ready UI for Phase 9 agent endpoints

## Datasette

Inspect the database directly during development:

```powershell
.\.venv\Scripts\python.exe -m datasette serve .\ad_classifier.db -o
```

## Diagnostics

Torch:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier version
```

Paddle ROCm best-effort check:

```powershell
.\.venv\Scripts\python.exe -m ad_classifier paddle-rocm-check
.\.venv\Scripts\python.exe -m ad_classifier paddle-rocm-check --image .\data\frames\ad_xxxxxxxx\frame_000000_t000000ms.png
```

CPU PaddleOCR is the supported default. AMD GPU PaddleOCR support is diagnostic only.

## Testing

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For linting the current polish changes:

```powershell
.\.venv\Scripts\python.exe -m ruff check ad_classifier\api\app.py ad_classifier\cli\__init__.py ad_classifier\diagnostics\paddle_rocm.py tests\diagnostics\test_paddle_rocm.py
.\.venv\Scripts\python.exe -m black --check ad_classifier\api\app.py ad_classifier\cli\__init__.py ad_classifier\diagnostics\paddle_rocm.py tests\diagnostics\test_paddle_rocm.py
```

`ruff check .` currently reports legacy findings outside this phase's changes; treat that as a cleanup task before enforcing repo-wide lint in CI.

Frontend:

```powershell
cd .\frontend
npm run build
```

## Sample Output

[samples/expected-output.sample.json](./samples/expected-output.sample.json) shows the intended output shape for the included sample clip. The real VLM call still needs LM Studio payload debugging; until then, real runs may persist the parse-failure fallback classification.

## Architecture

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
  -> aggregation
  -> text and visual embeddings
  -> SQLite persistence, FTS5, sqlite-vec
  -> FastAPI, worker, frontend
```

The system categorizes ads. Risk labels are descriptive observation tags for querying and analysis, not gating signals.
