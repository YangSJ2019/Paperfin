<div align="center">

# Paperfin

**A Jellyfin-style poster wall for your academic paper library.**

Import papers from arXiv or any PDF URL, watch your reading list grow as
a beautiful dark-themed gallery, and let an LLM write a structured summary
and a 0–100 quality score for each one.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Node](https://img.shields.io/badge/node-18%2B-brightgreen)

</div>

---

## Features

- 📚 **Poster wall** — drop PDFs into a folder or paste an arXiv URL; each
  paper gets a first-page thumbnail and slots into a responsive grid.
- 🧠 **Structured LLM summaries** — separate `contribution / method / result`
  paragraphs plus topical tags, not a one-line abstract. Output language is
  configurable (English by default; Simplified Chinese ships in the box).
- ⭐ **Quality score** — 4-axis rubric (innovation, rigor, clarity,
  significance) weighted into a single 0–100 number, rendered as a radar chart.
- 🔗 **URL import** — paste any `arxiv.org/abs/...`, `arxiv.org/pdf/...`, or
  direct PDF link; the backend streams the download, dedups by arxiv id +
  content hash, and runs the full pipeline.
- 🔌 **Model-agnostic** — flip `LLM_PROVIDER=anthropic` for Claude / Bedrock /
  MiniMax / LiteLLM, or `LLM_PROVIDER=openai` for ChatGPT / DeepSeek / Zhipu
  / Groq / Ollama / vLLM. Same `chat_json(system, user, schema)` contract
  inside the app; choose whichever model you have an account with.
- 🎛 **Single-user, local-first** — no login, no cloud dependencies beyond the
  LLM API you configure. SQLite file lives next to the PDFs.
- 🚀 **Optional auto-start** — ships with macOS LaunchAgent templates for a
  background service that survives reboots.

## Screenshots

> _TODO: add screenshots of the poster wall and detail view._

## Architecture

```mermaid
flowchart LR
    FE["React + Vite + TW<br/>(poster wall + UI)"]
    BE["FastAPI + SQLModel<br/>─ pipeline (scrape / import)<br/>─ services/pdf_parser<br/>─ services/metadata_extractor<br/>─ services/summarizer<br/>─ services/quality<br/>─ services/url_ingest<br/>─ services/llm (provider dispatch)"]
    LLM["Claude / ChatGPT / DeepSeek<br/>or anything speaking Anthropic or OpenAI API"]

    FE <-- "HTTP /api" --> BE
    BE --> LLM
```

- **Backend**: Python 3.11+, FastAPI, SQLModel, SQLite, PyMuPDF, pypdf,
  Anthropic SDK, OpenAI SDK.
- **Frontend**: React 18 + Vite + TypeScript + TailwindCSS + React Query +
  Recharts.
- **Storage**: SQLite in `backend/data/paperfin.db`, PDFs in
  `backend/data/papers/`, thumbnails in `backend/data/thumbnails/`.

> **Two wire protocols supported out of the box.** Pick one with
> `LLM_PROVIDER` in `.env`:
>
> - `anthropic` — talks the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)
>   (`POST /v1/messages`). Works with Claude, Amazon Bedrock Claude,
>   [MiniMax's `/anthropic` endpoint](https://api.minimaxi.com/anthropic),
>   [LiteLLM](https://github.com/BerriAI/litellm), etc.
> - `openai` — talks the OpenAI Chat Completions API
>   (`POST /v1/chat/completions`). Works with OpenAI, DeepSeek, Zhipu,
>   Groq, and every local inference server that exposes the OpenAI shape
>   (Ollama, vLLM, text-generation-webui, …).

---

## Quick start

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11 or newer |
| Node | 18 or newer |
| An LLM API key | Any endpoint speaking the Anthropic Messages API **or** the OpenAI Chat Completions API (Claude, ChatGPT, DeepSeek, MiniMax, a local Ollama / vLLM, …) |

### 1. Backend

```bash
cd backend
cp .env.example .env            # fill in LLM_PROVIDER / LLM_API_KEY / LLM_MODEL
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:8000`, so the React
app can call relative URLs without CORS setup.

### 3. Import a paper

- **From URL**: click **Import URL** in the top right, paste an arXiv link
  (`https://arxiv.org/abs/2005.11401`) or any direct PDF URL.
- **From disk**: drop `*.pdf` files into `backend/data/papers/` and click
  **Scan library**.

Processing takes ~20–40 s per paper (two LLM calls: summary + quality score).

---

## Configuration

All config lives in `backend/.env` (see `.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` (Messages API) or `openai` (Chat Completions API) | `anthropic` |
| `LLM_API_KEY` | API key for the chosen provider | *(required)* |
| `LLM_BASE_URL` | Override endpoint URL — e.g. a DeepSeek or LiteLLM URL | *(SDK default)* |
| `LLM_MODEL` | Model name to send | `claude-opus-4-7` |
| `SUMMARY_LANGUAGE` | Language for summaries + scoring rationales. `en` or `zh` | `en` |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional, boosts rate limits *(M3)* | *(empty)* |
| `DATA_DIR` | Where PDFs, thumbnails, SQLite live | `./data` |
| `SCAN_INTERVAL_HOURS` | Default subscription interval *(M4)* | `6` |
| `LOG_LEVEL` | Python logging level | `INFO` |

> **Legacy `ANTHROPIC_*` variables still work.** Existing `.env` files that
> set `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` are
> read as fall-backs when the new `LLM_*` names aren't set; no edits
> required to keep running.

### Provider examples

**Claude (official Anthropic):**

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key
LLM_MODEL=claude-opus-4-7
```

**OpenAI:**

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o
```

**DeepSeek (OpenAI-shape):**

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

**MiniMax (Anthropic-shape endpoint):**

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.minimaxi.com/anthropic
LLM_MODEL=MiniMax-M2.7
```

**Local Ollama (OpenAI-shape):**

```env
LLM_PROVIDER=openai
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5
```

### Changing summary language

Set `SUMMARY_LANGUAGE=zh` in `.env` and restart the backend to get
Simplified Chinese output from the summarizer and rubric reasoner. You can
also re-summarize an existing paper from the detail page to pick up the
new language without rescanning.

---

## Auto-start as a background service (macOS, optional)

Skip this if you only run Paperfin while developing.

```bash
# Render plist templates into ~/Library/LaunchAgents and load them.
./scripts/install-launchagents.sh

# Everyday control
cd backend
./agentctl.sh status     # are the agents alive?
./agentctl.sh logs backend
./agentctl.sh restart all
./agentctl.sh kick backend   # reload config after editing .env
./agentctl.sh stop all       # also disables auto-start at login
```

The LaunchAgents are configured with `KeepAlive`, so they're restarted if
they crash, and with `RunAtLoad` so they come up at login.

Uninstall:

```bash
cd backend && ./agentctl.sh stop all
rm ~/Library/LaunchAgents/ai.paperfin.*.plist
```

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/api/papers` | List papers (filters: `min_score`, `source`, `status`, `sort`, `limit`) |
| GET | `/api/papers/{id}` | Full detail |
| GET | `/api/papers/{id}/pdf` | Stream the PDF (inline, for iframes) |
| GET | `/api/papers/{id}/thumbnail` | First-page JPEG |
| POST | `/api/papers/scan` | Queue a scan of `data/papers/` |
| POST | `/api/papers/import-url` | Import one paper by URL |
| POST | `/api/papers/{id}/resummarize` | Re-run summarizer + scorer on an existing paper |
| DELETE | `/api/papers/{id}` | Delete the record |

Interactive Swagger docs: `http://localhost:8000/docs`.

---

## Project layout

```
paperfin/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI + CORS + lifespan
│   │   ├── config.py                 # Pydantic Settings
│   │   ├── db.py                     # SQLModel engine, init_db
│   │   ├── pipeline.py               # scan_local_directory / process_url
│   │   ├── api/papers.py             # REST endpoints
│   │   ├── models/                   # Paper / Subscription / Author / Institution
│   │   └── services/
│   │       ├── pdf_parser.py         # pypdf + PyMuPDF
│   │       ├── llm.py                # Anthropic-SDK wrapper, chat_json()
│   │       ├── metadata_extractor.py # title / authors / abstract
│   │       ├── summarizer.py         # structured summary (language from .env)
│   │       ├── quality.py            # 4-axis LLM rubric → 0-100
│   │       └── url_ingest.py         # arXiv URL parser + PDF download
│   ├── data/                         # user-generated, gitignored
│   ├── run.sh                        # dev launcher (sanitizes shell env)
│   ├── agentctl.sh                   # LaunchAgent controller
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx                   # Router + header
│   │   ├── pages/
│   │   │   ├── Library.tsx           # Poster wall
│   │   │   └── PaperDetail.tsx       # Summary + radar + inline PDF
│   │   ├── components/
│   │   │   ├── PaperCard.tsx
│   │   │   └── ImportDialog.tsx
│   │   └── lib/api.ts                # Typed API client
│   └── package.json
├── launchd/                          # macOS LaunchAgent templates
│   ├── ai.paperfin.backend.plist.template
│   └── ai.paperfin.frontend.plist.template
├── scripts/
│   └── install-launchagents.sh       # renders templates + loads them
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

---

## Roadmap

- ✅ **M1** — local poster wall, URL import, LLM summary & quality score,
  configurable summary language, optional auto-start.
- 🚧 **M2** — arXiv subscriptions (`cat:cs.LG AND abs:"diffusion"` style
  queries, cron-driven fetch, per-subscription min-quality filter).
- 🚧 **M3** — Semantic Scholar enrichment (author h-index, venue, citation
  count) → fills the `author / institution / venue` axes of the quality radar.
- 🚧 **M4** — Settings UI for LLM config and scoring weights; tag / venue
  facets on the poster wall; subscription management UI.

## Design notes

- **Idempotent scans** — every PDF is hashed (SHA-256). Reprocessing the
  same file is free; thumbnails are named by hash.
- **Deterministic dedup** — URL imports check `arxiv_id` *before* download
  (saves bandwidth + LLM tokens) and `content_hash` *after* (catches the
  same paper via different URLs).
- **LLM safety** — every LLM call goes through
  `app/services/llm.chat_json`, which injects the target Pydantic schema
  into the system prompt, validates the JSON response, and retries
  transient parse/network errors with exponential backoff.
- **Failure isolation** — a paper that fails mid-pipeline gets
  `status=FAILED` with the error in the `error` column; the scan keeps
  going.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Issues and PRs welcome —
particularly for the roadmap items above and for additional paper source
integrations.

## License

Licensed under the [MIT License](./LICENSE).

© Tencent. Paperfin is an open-source project maintained by Tencent.
