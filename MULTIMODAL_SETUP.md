# Multimodal RAG Setup Guide

LightRAG with multimodal support — PDFs uploaded via the WebUI have their images, charts, and tables described by a vision model and ingested into the knowledge graph alongside text.

## Prerequisites

- Docker + Docker Compose
- An OpenAI-compatible API key (model must support vision, e.g. `gpt-4.1-nano`, `gpt-4o`)
- NVIDIA GPU + drivers (Linux GPU path only)

---

## 1. Clone and configure

```bash
git clone https://github.com/avadhutc/LightRAG.git
cd LightRAG
cp env.example .env
```

Open `.env` and set at minimum:

```env
# LLM — must be a vision-capable model
LLM_BINDING=openai
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_BINDING_API_KEY=sk-...
LLM_MODEL=gpt-4.1-nano

# Embedding
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_BINDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIM=3072

# Multimodal — route PDFs through Docling, enable VLM image analysis
LIGHTRAG_PARSER=pdf:docling-iteP,docx:native-iteP,*:legacy-R
DOCLING_ENDPOINT=http://docling:5001
VLM_PROCESS_ENABLE=true
```

> `docling-iteP` means: image (`i`) + table (`t`) + equation (`e`) modality analysis, paragraph chunking (`P`).
> `DOCLING_ENDPOINT=http://docling:5001` uses the Docker Compose service name — do not change this to `localhost`.

---

## 2. Start containers

### CPU (Windows / Linux)

```bash
docker compose up -d
```

### GPU (Linux + NVIDIA)

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

> For CUDA 12.1 GPUs edit `docker-compose.gpu.yml` and change the image tag to `docling-serve-cu121:main`.

Two containers start:
- `lightrag` — LightRAG API + WebUI on port 9621
- `docling` — Docling document parser on port 5001 (internal only)

Check both are running:

```bash
docker compose ps
curl http://localhost:9621/health
curl http://localhost:5001/health
```

---

## 3. Upload a PDF via WebUI

Open **http://localhost:9621** in your browser.

1. Go to **Documents → Upload**
2. Drop any PDF
3. Monitor progress in the Documents tab

What happens internally:
1. PDF is sent to Docling for parsing → extracts text blocks, images, tables, equations
2. Each image/chart/table is described by the VLM (`gpt-4.1-nano`)
3. All content (text + VLM descriptions) is chunked and entity-extracted into the knowledge graph

You can watch it live:

```bash
docker compose logs lightrag -f
```

Look for lines like:
```
[docling] Parsing doc-xxx file.pdf (may take a few minutes)
[sidecar] wrote 41 blocks ... (11 tables, 68 drawings, 0 equations)
Analyzing multimodal: doc-xxx
Chunk 23 of 85 extracted 7 Ent + 11 Rel doc-xxx-mm-drawing-001
```

---

## 4. Query the knowledge graph

Use the WebUI chat, or query the API directly:

```bash
curl -s -X POST http://localhost:9621/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What do the charts show about AI investment trends?", "mode": "hybrid"}'
```

The response will draw on both text and VLM-described image content.

---

## 5. Standalone script (optional)

`process_document.py` runs the full multimodal pipeline outside of Docker, writing directly to the same `./data/rag_storage` directory.

### Setup (once per machine)

```bash
uv sync --extra api
uv pip install docling
```

On **Windows without Developer Mode**, apply two patches to fix venv bugs:

```powershell
# Fix 1: raganything uses asdict() which misses runtime LLM config
# Fix 2: raganything fallback returns 2-tuple but caller expects 3
# Fix 3: huggingface_hub symlink fails with WinError 1314
.venv\Scripts\python.exe patch_packages.py
```

### Run

```powershell
.venv\Scripts\python.exe process_document.py "path\to\file.pdf" --parser docling --output output
```

The script reads `LLM_BINDING_API_KEY` and `LLM_BINDING_HOST` from `.env`.

---

## Environment variable reference

| Variable | Required | Example | Notes |
|---|---|---|---|
| `LLM_BINDING_API_KEY` | Yes | `sk-...` | OpenAI or compatible key |
| `LLM_MODEL` | Yes | `gpt-4.1-nano` | Must support vision |
| `EMBEDDING_MODEL` | Yes | `text-embedding-3-large` | |
| `EMBEDDING_DIM` | Yes | `3072` | Must match the model |
| `VLM_PROCESS_ENABLE` | Yes | `true` | Master switch for image analysis |
| `LIGHTRAG_PARSER` | Yes | `pdf:docling-iteP,docx:native-iteP,*:legacy-R` | Routes PDFs to Docling |
| `DOCLING_ENDPOINT` | Yes | `http://docling:5001` | Internal Docker service name |
| `VLM_LLM_MODEL` | No | `gpt-4o` | Override VLM model separately from LLM |

---

## Troubleshooting

**Docling parse fails with HTTP 404**
Wrong image. Ensure `docker-compose.yml` uses `ghcr.io/docling-project/docling-serve:main`, not `ghcr.io/ds4sd/docling-serve:latest` (different API version).

**No images extracted from PDF**
Check `LIGHTRAG_PARSER` includes the `i` flag (e.g. `pdf:docling-iteP`). Without `i`, images are skipped even with `VLM_PROCESS_ENABLE=true`.

**VLM role not configured**
If `VLM_LLM_*` variables are not set, the VLM role inherits from `LLM_BINDING` / `LLM_MODEL`. Ensure that model is vision-capable.

**process_document.py: `role_llm_funcs` KeyError**
Run `patch_packages.py` to fix the `asdict()` bug in `raganything/modalprocessors.py`.

**process_document.py: `not enough values to unpack`**
Run `patch_packages.py` to fix the 2-tuple → 3-tuple fallback return bug in `raganything/modalprocessors.py`.
