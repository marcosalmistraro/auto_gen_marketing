# Marketing Collateral Generator

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![ChromaDB](https://img.shields.io/badge/Vector%20store-ChromaDB-ffb300)
![Groq](https://img.shields.io/badge/LLM-Groq-f55036)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./License)

Automated generation of tailored **B2B marketing articles** from company PDFs. Upload documents for a **sender** (the company pitching) and a **receiver** (the target client); the system extracts their text, tables and images, indexes everything, and generates a structured, on-brand article that bridges the sender's offering with the receiver's industry context.

The output is **structured JSON** (title, subtitle, sections, call-to-action, image references, theme colour) that drops directly into a publishing layout template.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Running Locally](#running-locally)
- [API Endpoints](#api-endpoints)
- [Design Notes](#design-notes)
- [License](#license)

---

## Features

- **PDF ingestion**: extracts text, tables (serialised to Markdown) and embedded images from uploaded PDFs with PyMuPDF.
- **Vision descriptions**: each image is described by a vision LLM at upload time, so images become semantically searchable as text.
- **Semantic indexing**: text, tables and image descriptions are embedded with `BAAI/bge-small-en-v1.5` (fastembed) and stored in ChromaDB, one collection per company.
- **Hybrid retrieval**: if the combined context fits the token budget it is sent in full; otherwise RAG selects the most relevant passages per company.
- **Structured generation**: a Groq-hosted LLM returns an article as JSON, enforced at two layers (Groq JSON-schema mode + Pydantic validation).
- **Image store**: raw image bytes and their descriptions are persisted in SQLite, keyed by UUID, and served back through the API.
- **Streamlit UI**: upload PDFs, generate and preview articles, and inspect/delete indexed companies.

## Architecture

The prototype runs fully locally; each component has a documented production (AWS) equivalent.

| Layer | Component | Role |
|---|---|---|
| API | FastAPI | REST layer: `/upload`, `/generate`, `/companies`, `/image`, `/health` |
| PDF extraction | PyMuPDF | Text blocks, tables (Markdown), raw image bytes |
| Embeddings | BGE-small-en (fastembed) | 384-dim vectors for text and image descriptions |
| Vector store | ChromaDB | Per-company collections; full-context and RAG retrieval |
| Image store | SQLite | Raw image bytes + vision descriptions, keyed by UUID |
| Vision + generation LLM | Groq | Image descriptions and structured article generation |
| Frontend | Streamlit | Browser UI for upload, generation and management |

## How It Works

1. **Upload** (`POST /upload`): a PDF is parsed into text, tables and images. Text and tables are chunked and embedded; each image is described by the vision LLM, stored in SQLite, and its description embedded so it is retrievable alongside text.
2. **Generate** (`POST /generate`): all stored context for both companies is gathered. If it fits within `RAG_THRESHOLD_TOKENS` it is passed in full; otherwise the most relevant chunks are retrieved per company. The LLM produces a structured article grounded in that context, with image placeholders referencing stored images.
3. **Render**: the returned JSON is ready for a layout engine, which resolves `image_placeholder` IDs to bytes via `GET /image/{image_id}`.

## Repository Structure

```
auto_gen_marketing/
├── app/                              # FastAPI backend
│   ├── main.py                       #   API endpoints
│   ├── config.py                     #   Settings from environment
│   ├── models/schemas.py             #   Pydantic request/response + article schema
│   ├── services/
│   │   ├── pdf_extractor.py          #   PyMuPDF text/table/image extraction
│   │   ├── vector_store.py           #   ChromaDB embedding + retrieval
│   │   ├── image_store.py            #   SQLite image persistence
│   │   └── generator.py              #   Groq vision + article generation
│   └── utils/chunker.py              #   Word-based chunking + token estimate
├── streamlit/                        # Streamlit frontend (separate deployable)
│   ├── app.py
│   └── requirements.txt
├── data/                             # Local data (gitignored; chroma/, images.db, samples)
├── Dockerfile                        # Backend container
├── requirements.txt                  # Backend dependencies
├── License
└── .gitignore
```

## Requirements

- Python 3.11
- A [Groq](https://groq.com/) API key
- Backend dependencies in `requirements.txt`; frontend dependencies in `streamlit/requirements.txt`

## Configuration

The backend reads configuration from environment variables (loaded from a local `.env` file in development; `.env` is gitignored and must never be committed).

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | - (required) | Groq API key |
| `LLM_MODEL` | `qwen/qwen3.8-27b` | Model used for article generation |
| `VISION_MODEL` | `qwen/qwen3.8-27b` | Model used for image descriptions |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model name |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `SQLITE_PATH` | `./data/images.db` | SQLite image database path |
| `MAX_CHUNK_TOKENS` | `512` | Max words per chunk |
| `CHUNK_OVERLAP` | `50` | Word overlap between chunks |
| `RAG_THRESHOLD_TOKENS` | `80000` | Above this estimated token count, switch from full context to RAG |

Example `.env`:

```properties
GROQ_API_KEY=your_groq_api_key_here
LLM_MODEL=qwen/qwen3.8-27b
VISION_MODEL=qwen/qwen3.8-27b
```

The Streamlit app points at the backend via `API_URL` (environment variable or `st.secrets`), defaulting to `http://localhost:8000`.

## Running Locally

**Backend (FastAPI):**

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Provide GROQ_API_KEY via .env or the environment, then:
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are then available at `http://localhost:8000/docs`.

**Frontend (Streamlit):**

```bash
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

**Docker (backend):**

```bash
docker build -t marketing-collateral-api .
docker run -p 8000:8000 --env-file .env marketing-collateral-api
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload a PDF for a `company_id` and `role` (`sender`/`receiver`); extracts, embeds and stores content |
| `POST` | `/generate` | Generate a structured article for a sender/receiver pair |
| `GET` | `/image/{image_id}` | Fetch raw image bytes by UUID |
| `GET` | `/companies` | List indexed companies with chunk and image counts |
| `DELETE` | `/companies/{company_id}` | Remove a company's vectors and images |
| `GET` | `/health` | Health check |

## Design Notes

Rationale for the main technical choices - PyMuPDF over pdfplumber/pypdf, SQLite for image storage, ChromaDB for vectors, vision-LLM descriptions over multimodal (CLIP) embeddings, and the two-layer JSON output enforcement - is documented in [`INTERVIEW_NOTES.md`](./INTERVIEW_NOTES.md).

## License

This project is licensed under the MIT License. See the [License](./License) file for details.
