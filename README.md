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
| Transcript | whisper.cpp, faster-whisper, or mock backend |
| VLM | OpenAI-compatible local or remote endpoint |
| Frontend | Vite, React, TypeScript, Tailwind-style CSS |

---

## Quick Start

### Prerequisites

- Windows 11 is the primary target environment.
- Python 3.11+.
- Node.js for the frontend.
- `ffmpeg` and `ffprobe` available on `PATH`.
- An OpenAI-compatible vision-language model endpoint, such as LM Studio,
  llama.cpp server, vLLM, or a compatible remote server.

### Install

```powershell
git clone https://github.com/LordLoras/adscope-local.git
cd adscope-local

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e ".[ocr,dev]"
```

### Important PyTorch Warning

Do **not** run `pip install torch`, `pip install torchvision`, or
`pip install torchaudio` in this project unless you are intentionally replacing
the pre-installed GPU build.

This repository expects PyTorch to be managed separately because Windows GPU
wheels for AMD/NVIDIA hardware are deployment-specific. When installing
embedding packages, use `--no-deps` so pip does not replace the GPU wheel:

```powershell
pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

### Configure

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

Then edit `config.yaml` for your local VLM endpoint:

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

### Initialize and Run

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

**The agent cannot answer a search question.** Confirm the API has initialized
sqlite-vec tables and the agent is using the configured vector store factory.
