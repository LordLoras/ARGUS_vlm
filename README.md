<div align="center">

![ARGUS banner](frontend/banner.png)

# ARGUS

**Ad Retrieval, Graphing & Understanding System**

Local-first multimodal ad analysis for video ads, marketing-entity extraction,
campaign discovery, hybrid retrieval, and a read-only natural-language agent.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-FTS5%20%2B%20sqlite--vec-473B5E?logo=sqlite&logoColor=white)](https://www.sqlite.org)

</div>

---

## Overview

ARGUS ingests local video advertisements and turns them into searchable,
structured records. It samples frames, extracts audio and transcripts, runs OCR,
collects deterministic rule evidence, asks a vision-language model to verify the
ad, writes marketing entities, and indexes both text and visual embeddings.

The system is designed for analyst workflows:

- classify ads against a configurable taxonomy
- extract brands, products, prices, offers, CTAs, disclaimers, contact points,
  social proof, and creative format
- search by keyword, text embedding, visual embedding, or hybrid retrieval
- search visual frames with SigLIP 2, including queries such as `red car`,
  `candidate podium`, `small disclaimer`, or `product hero shot`
- group related ads into campaigns
- ask a tool-calling natural-language agent questions over the local database

ARGUS is categorization-only. It does not gate, approve, block, escalate, or
route ads for review. Risk labels are descriptive observation tags for analysis
and search.

---

## What Is Included

This repository contains the ARGUS backend, worker, React frontend, SQLite
migrations, search tooling, and the Windows `whisper-cli.exe` binary under
`tools/whisper.cpp/`.

The repository does not include:

- Whisper `.bin` model files
- a running VLM or downloaded VLM weights
- ffmpeg / ffprobe
- Python, Node.js, or Git
- PyTorch GPU wheels
- PaddleOCR runtime model caches

This matters because a fresh clone can start the app code, but full ingestion
needs the external binaries and model files described below.

---

## Architecture

```text
Video upload
  -> ffmpeg frame/audio extraction
  -> whisper transcript
  -> frame preprocessing and keyframe selection
  -> OCR and optional hard-frame parsing
  -> deterministic rules
  -> evidence bundle
  -> VLM verification and marketing-entity extraction
  -> aggregation and persistence
  -> FTS5 + sqlite-vec indexing
  -> FastAPI, SSE, React UI, and read-only NL agent
```

Data lives in one SQLite database plus local artifact directories under `data/`.
The default deployment does not require Docker or cloud services.

---

## Core Components

| Area | Implementation |
|---|---|
| API | FastAPI with JSON endpoints and SSE job streams |
| Worker | Restartable local pipeline stages |
| Storage | SQLite in WAL mode |
| Full-text search | SQLite FTS5 |
| Vector search | sqlite-vec |
| Text embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Visual embeddings | `google/siglip2-base-patch16-224` |
| OCR | PaddleOCR by default |
| Transcript | bundled whisper.cpp CLI, faster-whisper, or mock backend |
| VLM | OpenAI-compatible local or remote endpoint |
| Frontend | Vite, React, TypeScript, Tailwind-style CSS |

---

## Installation

### 1. Prerequisites

ARGUS is primarily developed for Windows 11.

Install or verify:

- Git
- Python 3.11+ (`python --version`)
- Node.js 18+ (`node --version`)
- ffmpeg and ffprobe on `PATH` (`ffmpeg -version`)
- LM Studio, llama.cpp server, vLLM, or another OpenAI-compatible VLM endpoint

### 2. Clone ARGUS

```powershell
git clone https://github.com/LordLoras/ARGUS_vlm.git
cd ARGUS_vlm
```

### 3. Create the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Install OCR separately on Windows. Installing `paddlepaddle` first usually gives
clearer errors if the Paddle stack has a platform issue:

```powershell
python -m pip install paddlepaddle
python -m pip install paddleocr
```

You can also install the OCR extra after that:

```powershell
python -m pip install -e ".[ocr,dev]"
```

### 4. PyTorch and Embeddings

Do not run this in a production ARGUS environment unless you intentionally want
to replace the existing GPU build:

```powershell
pip install torch torchvision torchaudio
```

PyTorch is intentionally not listed as a direct dependency in `pyproject.toml`.
Windows GPU wheels are hardware-specific, and a normal `pip install` can replace
a working AMD/NVIDIA GPU wheel with a CPU build.

MiniLM text embeddings and SigLIP 2 visual embeddings both rely on PyTorch:

- `sentence-transformers/all-MiniLM-L6-v2` is used for text vectors.
- `google/siglip2-base-patch16-224` is used for image vectors and text-to-image
  visual queries.

After your torch build is already installed, add the embedding packages without
letting pip resolve and replace torch:

```powershell
python -m pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

If you do not have torch installed yet, use mock embeddings for tests or set
`image_embedder.enabled: false` in `config.yaml` until the GPU stack is ready.
Typed visual search still loads SigLIP 2, so avoid `visual` and `visual_hybrid`
search modes until torch and transformers are installed.

### 5. AMD ROCm on Windows

For an AMD GPU on Windows, install PyTorch from AMD's official ROCm Windows
instructions for your driver, GPU, and Python version:

<https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html>

Practical notes:

- Python 3.12 is commonly used by current AMD Windows ROCm wheels. If the AMD
  install page lists Python 3.12 for your wheel, create the venv with Python
  3.12 instead of Python 3.11.
- Install torch first, then install ARGUS dependencies.
- Do not use `--upgrade` on packages that depend on torch unless you are ready
  to reinstall the AMD wheel.
- If torch imports but reports CPU only, ARGUS will still run CPU jobs, but
  MiniLM and SigLIP 2 will be slow and visual vector search may feel unusable.

Verify the active torch build:

```powershell
@'
import torch

print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
'@ | python -
```

For ROCm Windows wheels, `torch.cuda.is_available()` is still the expected check
because PyTorch exposes the ROCm backend through the CUDA API surface.

### 6. Whisper Setup

`tools/whisper.cpp/whisper-cli.exe` is included in the repository. The Whisper
model file is not included.

Create the model directory:

```powershell
New-Item -ItemType Directory -Force .\models\whisper
```

Download a whisper.cpp GGML model from:

<https://huggingface.co/ggerganov/whisper.cpp>

For example, place one of these files under `models\whisper\`:

- `ggml-large-v3-turbo.bin` for better transcription quality
- `ggml-base.en.bin` or `ggml-small.en.bin` for lighter local testing
- `ggml-tiny.en.bin` for quick smoke tests

Then point `config.yaml` at it:

```yaml
whisper:
  backend: whisper_cpp
  whisper_cpp:
    command: ./tools/whisper.cpp/whisper-cli.exe
    model_path: ./models/whisper/ggml-large-v3-turbo.bin
    use_gpu: true
```

The bundled whisper.cpp CLI can use GPU acceleration depending on the included
build and your local driver stack. If transcription fails, set `use_gpu: false`
first to confirm the model path and audio extraction are correct.

### 7. VLM Setup

ARGUS expects an OpenAI-compatible chat completion endpoint for VLM
classification and marketing-entity extraction. LM Studio is the easiest local
option:

1. Open LM Studio.
2. Download a vision-capable model.
3. Start the local server.
4. Confirm it is listening on `http://127.0.0.1:1234/v1`.

Configure ARGUS:

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

```yaml
vlm:
  mode: local
  local:
    endpoint: "http://127.0.0.1:1234/v1"
    model: "your-vision-model"
    response_format: json_object
```

When `agent.inherit_vlm` is enabled, the NL agent uses the same active VLM
endpoint as the classifier.

### Optional GLM-OCR

PaddleOCR remains the grounded raw OCR engine. You can turn it off with
`ocr.enabled: false`, but the only raw OCR backend supported here is local
PaddleOCR.

GLM-OCR is optional and is intended for text-heavy frames, end cards, article
graphics, and CTA screens. It is stored separately with engine `glm_ocr` in
`ocr_items` and included in search text when `glm_ocr.include_in_search: true`.
It is not included in the classifier VLM bundle unless
`glm_ocr.include_in_vlm_bundle: true`.

For a local llama.cpp server:

```yaml
glm_ocr:
  enabled: true
  mode: local
  local:
    endpoint: "http://127.0.0.1:5050/v1"
    model: "glm-ocr"
```

Keep `temperature: 0` for OCR. Treat GLM-OCR numeric/legal fine print as
advisory unless PaddleOCR, transcript, or another frame corroborates it.

### 8. Initialize and Run

```powershell
python -m ad_classifier init-db
.\start.bat
```

Default local services:

| Service | URL |
|---|---|
| API | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| Frontend | `http://localhost:5173` |

---

## GPU Usage

Different parts of ARGUS use different acceleration paths:

| Component | Uses GPU when |
|---|---|
| VLM classification | Your LM Studio / llama.cpp / vLLM server is configured for GPU |
| GLM-OCR | Your configured local/remote GLM-OCR server is configured for GPU |
| Whisper transcript | `whisper.whisper_cpp.use_gpu: true` and the bundled CLI works with your driver |
| PaddleOCR | Usually CPU by default in this project |
| MiniLM text embeddings | `text_embedder.device: cuda` and torch GPU is available |
| SigLIP 2 visual embeddings | `image_embedder.device: cuda` and torch GPU is available |
| Visual vector search | A typed visual query loads SigLIP 2; GPU is used if the image embedder is on `cuda` |

Visual vector search does not add tokens to the agent context. Vectors are stored
physically in SQLite/sqlite-vec. The agent only receives selected search results,
metadata, and citations returned by its tools.

---

## Visual Search

ARGUS stores one ad-level visual vector and per-keyframe visual vectors. The
per-frame index lets visual queries return the best matching frames rather than
only a whole-ad score.

Useful query examples:

- `red car`
- `candidate podium`
- `small disclaimer`
- `news article screenshot`
- `product hero shot`
- `doctor office`
- `mobile app screen`
- `before and after comparison`

For existing ads processed before per-frame indexing was added, backfill visual
frame vectors with:

```powershell
python -m ad_classifier reindex-visual-frames
```

---

## API Highlights

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/ads/upload` | Upload a video and create a job |
| `GET` | `/api/ads` | List ads with filters |
| `GET` | `/api/ads/{id}` | Fetch ad detail, classification, and entities |
| `GET` | `/api/ads/{id}/frames` | Fetch frame metadata |
| `GET` | `/api/ads/{id}/evidence` | Fetch evidence and rule triggers |
| `GET` | `/api/ads/{id}/similar` | Retrieve similar ads |
| `GET` | `/api/search` | Keyword, text vector, visual, or hybrid search |
| `POST` | `/api/campaigns/discover` | Discover campaign clusters |
| `GET` | `/api/jobs/{id}/events` | Stream job progress |
| `GET` | `/api/agent/sessions/{id}/events` | Stream agent responses |

---

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Primary pages:

| Page | Path |
|---|---|
| Library | `/library` |
| Upload | `/upload` |
| Search | `/search` |
| Campaigns | `/campaigns` |
| Agent | `/agent` |

---

## Testing

```powershell
python -m pytest tests/ -q
npm run build --prefix frontend
```

Focused search/vector checks:

```powershell
python -m pytest tests/search tests/vectors tests/agent/test_tools.py -q
```

---

## Repository Layout

```text
ad_classifier/
  api/            FastAPI routes and SSE endpoints
  agent/          Tool-calling NL agent
  cli/            Operational and diagnostic commands
  db/             SQLite connection, migrations, repositories
  dedup/          Hash, perceptual hash, and vector similarity
  embeddings/     Text and image embedders
  ingest/         ffmpeg and transcript extraction
  marketing/      Marketing-entity normalization and enrichment
  pipeline/       OCR, rules, evidence, aggregation
  search/         FTS, query expansion, RRF, visual retrieval
  vectors/        sqlite-vec storage
  vlm/            VLM verifier, cleanup, correction, validation
  worker/         Pipeline orchestration
frontend/
  src/            React application
  logo.png        ARGUS icon asset
  banner.png      ARGUS banner asset
```

---

## Troubleshooting

**The VLM returns malformed JSON.** Use `response_format: json_object` for local
quantized models. Reserve strict schema mode for endpoints that reliably support
structured output.

**Visual search returns only whole-ad matches.** Run
`python -m ad_classifier reindex-visual-frames` for ads processed before the
per-frame index existed.

**PaddleOCR fails to import.** Install `paddlepaddle` before `paddleocr` on
Windows, then reinstall the OCR extra if needed.

**SigLIP or sentence-transformers tries to change torch.** Reinstall those
packages with `--no-deps` and verify the existing torch build before running the
worker.

**Visual search fails when the rest of the app works.** Typed visual queries load
the SigLIP 2 model through transformers and torch. Confirm the embedding
packages are installed, then verify torch can see the GPU or switch the image
embedder to CPU.

**The agent cannot answer a search question.** Confirm the API has initialized
sqlite-vec tables and the agent is using the configured vector store factory.
