<div align="center">

# ARGUS

**Ad Retrieval, Graphing & Understanding System**

Local-first multimodal ad classification · marketing-entity extraction ·
campaign tracking · hybrid search · NL agent

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20%2B%20FTS5%20%2B%20sqlite--vec-473B5E?logo=sqlite&logoColor=white)](https://www.sqlite.org)

</div>

---

## What It Does

Upload a TV ad, promo clip, or any video commercial and ARGUS will:

1. **Extract frames & transcript** — ffmpeg + whisper.cpp (Vulkan GPU)
2. **OCR every frame** — PaddleOCR reads prices, offers, brand names, phone numbers
3. **Classify & verify with a VLM** — sends frames + OCR + transcript to a vision-language model (local or remote) that returns structured JSON
4. **Extract marketing entities** — brand, products, prices, offers, CTAs, financing terms, disclaimers, creative format, contact points
5. **Embed & index** — MiniLM text embeddings + SigLIP 2 visual embeddings → sqlite-vec with hybrid search
6. **Track campaigns** — auto-cluster similar ads by brand and visual similarity
7. **Answer questions** — NL agent with tool-calling loop over the database

No cloud services. No Docker. One SQLite file. One command to start.

---

## Architecture

```
    ┌─────────────────────────────────────────────────────┐
    │                   FastAPI + SSE                       │
    │          http://localhost:8000/api                   │
    └──────────────────────┬──────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────┐
    │               Pipeline Worker                       │
    │                                                     │
    │  ffmpeg ──► frames + audio                          │
    │  whisper.cpp ──► transcript                        │
    │  PaddleOCR ──► text + bounding boxes               │
    │  Rules engine ──► deterministic triggers           │
    │  VLM (local/remote) ──► classification + entities  │
    │  MiniLM + SigLIP 2 ──► embeddings                  │
    │  sqlite-vec ──► hybrid search                      │
    └──────────────────────┬──────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────┐
    │             SQLite (WAL mode)                        │
    │  ads · frames · ocr_items · classifications         │
    │  marketing_entities · transcript_segments           │
    │  rule_triggers · campaigns · agent_sessions         │
    │  FTS5 full-text · sqlite-vec vectors                │
    └─────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** (3.12 required for AMD GPU — see below)
- **ffmpeg** in PATH (for video frame extraction)
- **Windows** (tested on 11; Linux/macOS should work with path adjustments)
- A **VLM endpoint** — any OpenAI-compatible server (llama.cpp, LM Studio, vLLM, etc.)

### 1. Clone and install

```powershell
git clone https://github.com/LordLoras/adscope-local.git
cd adscope-local

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install everything (core + OCR + dev tools):
pip install -e ".[ocr,dev]"
pip install paddlepaddle      # must install BEFORE paddleocr on Windows
```

### 2. Whisper.cpp (included)

A Vulkan-accelerated `whisper-cli.exe` is bundled in `tools/whisper.cpp/`. It works on AMD and NVIDIA GPUs out of the box — no extra drivers beyond your GPU vendor's latest Vulkan runtime.

Download a model from [whisper.cpp releases](https://huggingface.co/ggerganov/whisper.cpp/tree/main):

```powershell
# Recommended: large-v3-turbo (best accuracy)
mkdir models\whisper
curl -L -o models\whisper\ggml-large-v3-turbo.bin `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# Or the tiny model for quick testing (75 MB)
curl -L -o models\whisper\ggml-tiny.en.bin `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
```

> **Note:** For automatic model download, you can use `huggingface-cli`:
> ```powershell
> pip install huggingface_hub
> huggingface-cli download ggerganov/whisper.cpp ggml-large-v3-turbo.bin --local-dir models\whisper
> ```

### 3. Configure

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

Edit `config.yaml`. The key section is the VLM endpoint:

```yaml
vlm:
  # Switch between local and remote with one flag:
  mode: local

  local:
    endpoint: "http://127.0.0.1:1234/v1"
    model: "Qwen3.6-27B-Q4_K_M"
    response_format: json_object    # safer for quantized local models

  remote:
    endpoint: "https://your-server.com/v1/"
    model: "unsloth/Qwen3.6-35B-A3B-GGUF"
    api_key_env: "VLM_API_KEY"
    response_format: json_schema   # stronger validation for capable remote models
```

When `mode: remote`, both the VLM and the NL agent use the remote endpoint automatically.

### 4. Initialize the database and start

```powershell
# Create the SQLite database
python -m ad_classifier init-db

# Start API + worker + frontend (or run each separately)
.\start.bat
```

- **API**: http://localhost:8000
- **Frontend**: http://localhost:5173
- **API docs**: http://localhost:8000/docs

---

## GPU Embeddings (Optional)

The pipeline works fully on CPU. Visual embeddings (SigLIP 2) are optional and require PyTorch:

```yaml
image_embedder:
  enabled: false   # set to true when torch is installed
  device: cpu      # "cuda" works for both NVIDIA and AMD (with ROCm wheels)
```

Set `device: cuda` on any GPU — NVIDIA CUDA and AMD ROCm both work with the appropriate PyTorch wheel.

### NVIDIA GPU

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

### AMD GPU (ROCm on Windows)

**Requires Python 3.12.** AMD's PyTorch ROCm wheels for Windows are only available for Python 3.12. Follow the official guide at [AMD ROCm PyTorch for Windows](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html) to install the correct build.

**Do not run `pip install torch`** — it will replace the GPU wheel with a CPU build. If torch is already installed in `.venv`, leave it alone.

```powershell
# Verify existing torch
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"

# Install embedding dependencies without touching torch:
pip install --no-deps sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1
```

Then set `image_embedder.enabled: true` and `image_embedder.device: cuda` in config.

---

## VLM Setup

ARGUS needs a vision-capable VLM that accepts OpenAI-format chat completions with `image_url` content blocks.

### Local (llama.cpp or compatible)

Any OpenAI-compatible inference server works — llama.cpp server, LM Studio, vLLM, ollama, etc. The endpoint must support the `/v1/chat/completions` format with `image_url` content blocks.

1. Start your inference server (e.g., llama.cpp with Vulkan or CUDA support)
2. Set `vlm.mode: local` and point `vlm.local.endpoint` to your server
3. Make sure the model is vision-capable (Qwen2.5-VL, Qwen3.6-VL, Gemma 3, etc.)

**Model compatibility:** The Qwen family (Qwen2.5-VL, Qwen3.6-VL) works best — it follows instructions reliably and produces structured JSON output. Other instruct-tuned vision models may work but field names and response shapes can vary, especially at lower quantizations. Higher quant (Q5_K_M, Q6_K, Q8_0) produces significantly more accurate and consistent results than IQ3 or Q4.

**For llama.cpp servers:** use `response_format: json_object` — `json_schema` structured output is unreliable with smaller/quantized models.

### Remote

Set `vlm.mode: remote` and point the endpoint to your server. Tested with:
- Unsloth-hosted Qwen3.6-35B-A3B (llama.cpp backend)
- OpenAI-compatible endpoints

---

## Configuration Reference

| Section | Key | Default | Description |
|---|---|---|---|
| `paths` | `data_root` | `./data` | Root for all data dirs |
| `whisper` | `backend` | `whisper_cpp` | `whisper_cpp` (bundled, Vulkan), `faster-whisper` (pip extra), or `mock` |
| `whisper` | `model` | `tiny.en` | Whisper model name |
| `ocr` | `device` | `cpu` | PaddleOCR device (CPU recommended on Windows) |
| `vlm` | `mode` | `local` | `local` or `remote` — flips both VLM and agent |
| `vlm` | `max_frames_in_bundle` | `12` | Max frames sent to VLM per request |
| `vlm` | `image_max_dim` | `512` | Max pixel dimension for VLM frames |
| `vlm.local` | `endpoint` | `http://127.0.0.1:1234/v1` | Local inference server endpoint |
| `vlm.remote` | `endpoint` | — | Remote VLM endpoint URL |
| `vlm.remote` | `api_key_env` | — | Environment variable name for API key |
| `image_embedder` | `enabled` | `true` | Set `false` to skip visual embeddings (no torch needed) |
| `agent` | `inherit_vlm` | `true` | Agent uses the active VLM endpoint automatically |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ads/upload` | Upload video, create processing job |
| `GET` | `/api/ads` | List ads (filter by brand, category, status, q) |
| `GET` | `/api/ads/{id}` | Ad detail + classification + marketing entities |
| `GET` | `/api/ads/{id}/frames` | Frame metadata for an ad |
| `GET` | `/api/ads/{id}/evidence` | Classification + rule evidence |
| `GET` | `/api/ads/{id}/similar` | Similar ads by embedding |
| `PATCH` | `/api/ads/{id}` | Update projection fields |
| `DELETE` | `/api/ads/{id}` | Delete ad and artifacts |
| `GET` | `/api/search` | FTS / vector / hybrid search |
| `POST` | `/api/campaigns/discover` | Run campaign clustering |
| `GET` | `/api/jobs/{id}/events` | Real-time job progress (SSE) |

Full interactive docs at `http://localhost:8000/docs`.

---

## Frontend

```powershell
cd frontend
npm install
npm run codegen   # requires backend at localhost:8000
npm run dev
```

| Page | Path | Description |
|---|---|---|
| Library | `/library` | Ad table with filters, detail drawer, edit/delete |
| Upload | `/upload` | Video upload with real-time progress via SSE |
| Search | `/search` | Keyword, vector, and hybrid search |
| Campaigns | `/campaigns` | Campaign cards and discovery |
| Agent | `/agent` | NL agent chat interface |

---

## Testing

```powershell
python -m pytest tests/ -q                      # all unit tests
python -m pytest tests/ -k "not paddleocr" -q  # skip PaddleOCR tests
```

---

## Project Structure

```
ad_classifier/
  api/                FastAPI routes and SSE
  cli/                CLI commands (init-db, api, worker, version)
  config.py           Pydantic config from YAML
  db/                 SQLite repos, migrations, FTS5, sqlite-vec
  dedup/              SHA256 + pHash + vector dedup
  diagnostics/        Environment and GPU checks
  embeddings/         MiniLM text + SigLIP 2 visual embedders
  ingest/             ffmpeg, whisper, frame extraction
  marketing/          OCR normalization, offer extraction, brand resolution
  models/             Pydantic models for all pipeline objects
  pipeline/           Evidence bundles, aggregation, rules engine
  search/             FTS5 + vector + hybrid search with RRF
  vlm/                VLM verifier, cleanup, correction, schema, prompt
  worker/             Pipeline runner and stage orchestration
frontend/              Vite + React + TypeScript + Tailwind + shadcn/ui
tools/whisper.cpp/    whisper-cli.exe with Vulkan DLLs (shipping-bundled)
config.example.yaml   Full config template with comments
taxonomy.yaml         Ad categories and risk labels
```

---

## Troubleshooting

**VLM returns empty response / disconnects:** Check logs for `vlm_request_error` or `vlm_empty_response` warnings. These indicate the inference server cancelled generation mid-response.

**PaddleOCR import error:** `pip install paddlepaddle paddleocr`. On Windows, install `paddlepaddle` first.

**SigLIP/torch import error:** Set `image_embedder.enabled: false` in config to skip visual embeddings, or install torch with GPU support.

**`json_schema` not working with local model:** Switch to `response_format: json_object` for quantized models. The `json_schema` format requires frontier models.