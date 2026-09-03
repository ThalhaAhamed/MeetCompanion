# MeetStream Companion 🎙️🧠

> **Persistent AI Meeting Companion** — deploys a voice agent into your meetings via **MeetStream MIA**, remembers everything across every call using **PostgreSQL + pgvector**, and exposes that memory back to the live agent through **MCP (Model Context Protocol)** — plus a web dashboard to browse it all.

Most meeting bots hand you a transcript and forget everything the moment the call ends. MeetStream Companion is different: it deploys a bot that joins your call, records and transcribes it, runs the transcript through an LLM to extract structured memory (decisions, commitments, action items, concerns), and makes that memory queryable — both by a **live in-meeting AI agent** ("what did we decide about pricing three weeks ago?") and by a **web dashboard** for browsing meetings, searching memory, and managing the agent's configuration.

---

## 🌟 Key Features

- **Live in-meeting AI agent** — MeetStream's MIA agent joins your Google Meet / Zoom / Teams call, listens, and can speak or respond in chat with full historical context pulled from past meetings.
- **Persistent hybrid RAG memory** — every meeting's transcript and extracted memories are embedded and indexed with **Reciprocal Rank Fusion** (vector similarity + Postgres full-text keyword search), so exact terms (names, dates) aren't lost to embedding-only ranking.
- **MCP server with 8 tools** — 4 read tools (search memory, get a meeting, list/count previous meetings, list action items) and 4 write tools (add a memory, add a note, create an action item, update an action item), all org-scoped and audit-logged.
- **Automated memory extraction** — post-call transcripts are analyzed by an LLM (Groq / OpenAI) into categorized memories (decisions, requirements, commitments, concerns, facts, unresolved questions) and tracked action items.
- **Web dashboard** — browse meetings by day, view transcripts/summaries/decisions/action items, launch and stop bots, search memory, upload company-knowledge documents, and configure the live agent (system prompt, voice, model, MCP wiring) — all from the browser.
- **Company knowledge RAG** — upload PDFs/docs/notes as a separate knowledge base the agent can also draw on.
- **Secure multi-tenant architecture** — every table is scoped by `organization_id`; HMAC-signed webhooks with replay protection; secrets are redacted server-side before any MeetStream API response reaches the browser.

---

## 🏗️ Architecture Overview

```
                          MeetStream Platform
             ┌───────────────┬─────────────────┬──────────────┐
             │  Bots (Calls) │  MIA Agent (AI) │ Transcript    │
             └───────┬───────┴────────┬────────┴──────┬───────┘
                     │                │               │
                 Webhooks       MCP (HTTP)       Webhooks
                     │                │               │
                     ▼                ▼               ▼
          ┌───────────────────────────────────────────────────────┐
          │               FastAPI Companion Server                │
          │                                                        │
          │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
          │  │ Webhook API  │  │ MCP Server  │  │ Meeting API  │  │
          │  └───────┬──────┘  └──────┬──────┘  └──────┬───────┘  │
          │          │                │                │          │
          │          ▼                ▼                ▼          │
          │  ┌─────────────────────────────────────────────────┐  │
          │  │                   Services                       │  │
          │  │  • MeetStream Client   • Memory Extractor        │  │
          │  │  • Ingestion Pipeline  • Embedding Service       │  │
          │  └────────────────────────┬────────────────────────┘  │
          │                           │                            │
          │                           ▼                            │
          │  ┌─────────────────────────────────────────────────┐  │
          │  │           PostgreSQL 17 + pgvector               │  │
          │  │  • meetings, participants   • memories           │  │
          │  │  • transcript_segments      • action_items       │  │
          │  │  • meeting_memory_embeddings (vector 384)        │  │
          │  │  • company_knowledge_embeddings                  │  │
          │  └─────────────────────────────────────────────────┘  │
          └────────────────────────────────────────────────────────┘
                           ▲
                           │ REST API
                           │
                  ┌─────────────────┐
                  │  React Dashboard │  (frontend/, Vite dev server on :3000)
                  └─────────────────┘
```

Because this runs locally in development, a **Cloudflare Tunnel** exposes the backend to the public internet so MeetStream can deliver webhooks and the live agent can reach the MCP server — see [How it works locally](#-how-it-works-locally) below.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.12 (the project's `.venv` targets this — the system default may differ)
- Node.js 18+ (for the frontend)
- Docker Desktop (for PostgreSQL + pgvector)
- A [MeetStream](https://app.meetstream.ai) account and API key
- An LLM API key (Groq is free-tier and works well; OpenAI also supported)

### 2. Configure environment
```bash
cp .env.example .env
```
Fill in `.env` with your real values: `MEETSTREAM_API_KEY`, `MEETSTREAM_AGENT_CONFIG_ID` (create a MIA agent in the MeetStream dashboard first), `GROQ_API_KEY` or `OPENAI_API_KEY`, and `MCP_AUTH_TOKEN` (any random string — this authenticates the MCP server).

### 3. One-command startup (Windows / PowerShell)
```powershell
.\start.ps1
```
This single script brings up **everything**: Docker + Postgres, the FastAPI backend, a fresh Cloudflare quick tunnel, re-points the MeetStream agent's MCP URL at that tunnel automatically, installs frontend dependencies on first run, and launches the dashboard — opening your browser at `http://localhost:3000`.

Stop everything with:
```powershell
.\stop.ps1
```
(Postgres is left running since it's cheap to keep up and holds your data — stop it separately with `docker compose down` if you want.)

### Manual startup (any OS)
```bash
docker compose up -d
python scripts/setup_db.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
```bash
cd frontend
npm install
npm run dev
```
You'll also need a tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`) and to set `MCP_SERVER_URL` in `.env` to that tunnel's `/mcp` URL, then PUT it to your agent config via `PUT /api/agent` (see below) — `start.ps1` automates all of this.

---

## 📖 How to Use It

### From the dashboard (`http://localhost:3000`)
1. **Day view** — pick a date to see every meeting and document from that day. Click **Launch bot** and paste a meeting link (Google Meet / Zoom / Teams) to deploy the agent into a live call.
2. Click into a meeting to see its **Summary**, **Decisions & Memories**, **Action Items** (editable status), **Transcript**, and live **Bot** status — with a **Stop bot** button while it's still recording.
3. **Search memory** — semantic + keyword search across every indexed meeting, ranked by match %.
4. **Agent** — view and edit the live MIA agent's system prompt, first message, voice, model, and response settings; changes are pushed straight to MeetStream.
5. Upload company documents (PDF/DOCX/TXT/MD/CSV) from the Day view's Documents panel to add them to the company-knowledge RAG.

### From a live meeting
Once a bot with the configured agent joins a call, it can be asked things like *"What did we decide about the pricing tier last week?"* or *"How many meetings did we have yesterday?"* — it answers using the MCP tools below, which query the same memory the dashboard shows you.

### From the API directly
```bash
# Deploy a bot into a meeting
curl -X POST http://localhost:8000/api/meetings \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://meet.google.com/xxx-xxxx-xxx", "title": "Sync"}'

# Search meeting memory
curl -X POST http://localhost:8000/api/search/memory \
  -H "Content-Type: application/json" \
  -d '{"query": "pricing decisions"}'
```
Full interactive API docs are available at `http://localhost:8000/docs` while the server is running.

---

## 🛠️ MCP Tools Reference

Exposed at `POST /mcp` (JSON-RPC 2.0) and individually at `POST /mcp/tools/{tool_name}`, authenticated with `Authorization: Bearer <MCP_AUTH_TOKEN>`.

**Read tools**

| Tool | Purpose | Key Parameters |
|---|---|---|
| `search_meeting_memory` | Hybrid semantic + keyword search across all previous meetings | `query`, `customer_name`, `speaker`, `limit` |
| `get_meeting` | Full details, summary, participants, and memories for one meeting | `meeting_id` or `title` |
| `get_previous_meetings` | List and accurately **count** recent meetings, with a real date range filter | `date_from`, `date_to`, `customer_name`, `project_name`, `limit` |
| `get_action_items` | List open or completed action items | `owner`, `status`, `limit` |

**Write tools** (used by the live agent to persist what it hears)

| Tool | Purpose |
|---|---|
| `add_meeting_memory` | Record a structured memory (decision, requirement, concern, fact, etc.) |
| `add_meeting_note` | Record a quick free-form note that doesn't fit a specific memory type |
| `create_action_item` | Create a tracked task/commitment with an owner and due date |
| `update_action_item` | Update an existing action item's status, owner, due date, or notes |

---

## 🖥️ How It Works Locally

Everything in this project runs on your own machine — nothing is deployed. The only thing that reaches the public internet is a **Cloudflare Tunnel**, which forwards traffic back to your local backend so MeetStream's cloud service can deliver webhooks and the live agent can call the MCP server. This means:

- The tunnel's URL changes every time it restarts — `start.ps1` handles regenerating it and re-pointing the agent config automatically.
- The whole system only works while your machine is on and `start.ps1` (or the manual equivalent) is running.
- Postgres runs in Docker purely because it's the simplest way to get Postgres + the pgvector extension on Windows without a native install — the backend itself runs directly via the local Python venv, not in Docker.

For anything beyond local development (a teammate needs access, or you want it to keep working when your laptop is off), the real fix is deploying the backend somewhere with a stable public URL (Render, Railway, Fly.io, a VPS) rather than tunneling a dev server.

---

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

Run the interactive pipeline demonstration:
```bash
python scripts/test_memory_pipeline.py
```

---

## 📁 Project Structure

```
app/
  api/          REST endpoints (meetings, documents, agent, search, action items, webhooks, health)
  mcp/          MCP server (JSON-RPC + REST tool endpoints) and tool implementations
  services/     MeetStream API client, LLM memory extraction, embedding service, ingestion pipeline
  rag/          Hybrid vector+keyword search (meeting memory) and company knowledge RAG
  database/     SQLAlchemy repositories (org-scoped data access)
  models/       ORM models and Pydantic schemas
frontend/       React + Vite dashboard
migrations/     SQL schema (Postgres + pgvector)
tests/          Unit, integration, and security tests
start.ps1       One-command dev environment bootstrap (Windows)
stop.ps1        Stops the backend/frontend/tunnel
```
