<div align="center">

<img src="assets/branding/logo-icon.png" alt="Meet Companion" width="120" />

# Meet Companion

**Make meeting data smarter.**

Your open-source AI meeting companion. Choose your own AI models, storage and infrastructure.

</div>

---

Meet Companion sends an AI assistant into your meetings, then turns what was said
into something you can actually use afterwards: decisions, commitments and action
items you can search, organise and ask questions about.

It is built on top of [MeetStream](https://meetstream.ai), which provides the bot
that joins calls and produces transcripts.

The point of this project is that **you own the infrastructure**. Nothing is
hard-wired to a vendor:

- Bring your own LLM — OpenAI, Anthropic, Gemini, Groq, a local Ollama model, or
  any OpenAI-compatible endpoint.
- Bring your own database — a local SQLite file by default, PostgreSQL if you
  want it.
- Run it entirely on your own machine. With Ollama and SQLite, no data leaves
  your computer and no API key is required.

## Features

- **Meeting capture** — launch a bot into Google Meet, Zoom or Teams, or import
  bots that already ran on your MeetStream account.
- **Memory extraction** — transcripts are turned into structured decisions,
  commitments, requirements, concerns and action items.
- **Semantic search** — hybrid vector and keyword search across everything ever
  said, not just keyword matching.
- **Notebook** — a real workspace: nested folders, notes, tags, favourites,
  filtering and sorting.
- **Ask AI** — ask questions about your own notes. Answers are grounded in
  retrieved content and the model is instructed never to invent details.
- **In-call recall** — an MCP server lets the in-meeting agent query your past
  meetings live, so it can answer "what did we decide last time?" during a call.

## Quick start

Requires Python 3.12+ and Node 20+.

```bash
git clone https://github.com/ThalhaAhamed/MeetCompanion.git
cd MeetCompanion

python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt

npm --prefix frontend install
```

Start the backend:

```bash
.venv/Scripts/python -m uvicorn app.main:app --port 8000 --reload
```

And the frontend, in a second terminal:

```bash
npm --prefix frontend run dev
```

Open <http://localhost:3000>. On first run you are walked through choosing an AI
provider and where to store your data. **No `.env` file is required** — the
defaults work, and everything is configurable from the UI.

### Running fully offline

Install [Ollama](https://ollama.com), pull a model, and pick *Ollama (local)*
during setup:

```bash
ollama pull llama3.1
```

With Ollama and the default SQLite storage, Meet Companion makes no outbound
calls except to MeetStream when you actually launch a bot.

## Configuration

Everything can be set in the UI. For container or CI deployments, environment
variables take precedence over anything saved in the UI, and the Settings screen
marks those fields read-only rather than pretending to save them.

Copy `.env.example` to `.env` to configure by file. Every value has a working
default; the ones you are most likely to want:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/meet-companion.db` | Storage. Point at `postgresql+asyncpg://…` for Postgres. |
| `LLM_PROVIDER` | `ollama` | `openai`, `anthropic`, `gemini`, `ollama`, `groq`, `openai_compatible` |
| `LLM_MODEL` | per provider | Model name. |
| `LLM_API_KEY` | — | Required for hosted providers; not needed for Ollama. |
| `LLM_BASE_URL` | per provider | Override for proxies, gateways or self-hosted endpoints. |
| `MEETSTREAM_API_KEY` | — | Only needed to send bots into live meetings. |
| `MCP_AUTH_TOKEN` | — | Change before exposing the server beyond your machine. |

Configuration saved through the UI lives in `data/config.json`, alongside the
SQLite database. Both are gitignored — `config.json` holds API keys.

## Supported providers

**LLM** — OpenAI · Anthropic · Google Gemini · Ollama · Groq · any
OpenAI-compatible API (vLLM, LM Studio, OpenRouter, together.ai)

**Database** — SQLite (default, zero setup) · PostgreSQL with pgvector

**Embeddings** run locally via `sentence-transformers`; they never require an API
key and never leave the machine.

**Meeting bots** — MeetStream.

## Architecture

```
                    UI  (React + Vite + Tailwind)
                     │
                    API  (FastAPI)
                     │
        Services / domain logic
                     │
            Provider abstractions
        ┌────────────┼─────────────┐
       LLM        Database      MeetStream
        │             │
  OpenAI            pgvector  (PostgreSQL)
  Anthropic         in-process cosine  (SQLite)
  Gemini
  Ollama
  Groq
  OpenAI-compatible
```

Two ideas carry most of the weight:

**Providers are interfaces, not conditionals.** Adding an LLM vendor means
writing one adapter in `app/providers/llm/` and registering it. No application
code changes. Each adapter also declares which configuration fields it needs,
and that metadata drives the setup forms — which is why Ollama never shows an
API key box.

**The database is swapped, not abstracted away.** Only two operations actually
differ between databases: similarity search and keyword search. Those live in
`app/providers/database/`, selected from the live connection's dialect. On
Postgres they use pgvector and full-text search; elsewhere similarity is
computed with numpy and keywords are scored by term matching. Everything else is
ordinary SQLAlchemy that runs anywhere, using portable column types from
`app/models/types.py`.

```
app/
├── api/            HTTP endpoints
├── providers/      LLM and database adapters
├── services/       application logic
├── database/       repositories
├── models/         ORM models and portable column types
├── rag/            chunking, indexing, retrieval
├── mcp/            MCP server for in-call tool use
└── runtime_config  configuration persisted from the UI
```

## Development

```bash
.venv/Scripts/python -m pytest          # backend tests
npm --prefix frontend run lint          # frontend lint
npm --prefix frontend run build         # production build
```

The test suite is hermetic: it runs against a throwaway SQLite file and needs no
Postgres, no Docker and no network.

### Using PostgreSQL

```bash
docker compose up -d
export DATABASE_URL=postgresql+asyncpg://meet:meet_dev_password@localhost:5432/meet_companion
```

The schema, indexes and pgvector extension are created automatically at startup.

## Contributing

Contributions are welcome. A few things worth knowing:

- Adding an LLM provider is a single file in `app/providers/llm/` plus a
  registry entry and a descriptor. Look at `ollama.py` for the smallest example.
- Anything database-specific belongs behind `SearchBackend`; if you find
  yourself writing dialect checks elsewhere, that is a sign it belongs there.
- Keep secrets out of API responses. `app/runtime_config.py` masks them, and
  there are tests asserting they are never returned in full.
- Run the tests before opening a pull request.

## Roadmap

- Local transcription provider, so meeting capture can run without MeetStream
- Rich-text and Markdown rendering in the notebook editor
- Re-indexing task for notes and meetings after changing embedding models
- Export (Markdown, JSON) for notes and meetings

## License

No license file is present yet. Until one is added, all rights are reserved by
the copyright holder — if you intend to use this, open an issue to ask.
