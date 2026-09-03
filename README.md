# MeetStream Companion 🎙️🧠

**[▶ Try it now](https://frontend-production-1102c.up.railway.app)** — sign in with an existing account, or ask a member to add you from the Members page.

> **Persistent AI Meeting Companion** — deploys a voice agent into your meetings via **MeetStream MIA**, remembers everything across every call using **PostgreSQL + pgvector**, and exposes that memory back to the live agent through **MCP (Model Context Protocol)** — plus a hosted web dashboard the whole team can sign into.

Most meeting bots hand you a transcript and forget everything the moment the call ends. MeetStream Companion is different: it deploys a bot that joins your call, records and transcribes it, runs the transcript through an LLM to extract structured memory (decisions, commitments, action items, concerns), and makes that memory queryable — both by a **live in-meeting AI agent** ("MeetStream Companion, what did we decide about pricing three weeks ago?") and by a **web dashboard** for browsing meetings, searching memory, and managing the agent's configuration.

The backend and frontend are deployed on Railway (not a local-only dev tool), and the dashboard is gated by real per-member accounts rather than being wide open.

---

## 🌟 Key Features

- **Live in-meeting AI agent, name-gated** — MeetStream's MIA agent joins your Google Meet / Zoom / Teams call and stays silent until addressed by name (e.g. "MeetStream Companion, ..."), then answers using full historical context pulled from past meetings.
- **Persistent hybrid RAG memory** — every meeting's transcript and extracted memories are embedded and indexed with **Reciprocal Rank Fusion** (vector similarity + Postgres full-text keyword search), so exact terms (names, dates) aren't lost to embedding-only ranking.
- **MCP server with 9 tools** — a date-resolution tool, 4 read tools (search memory, get a meeting, list/count previous meetings, list action items) and 4 write tools (add a memory, add a note, create an action item, update an action item), all org-scoped and audit-logged. Tool output is rendered as plain natural language, not raw JSON, so it reads cleanly if it ever reaches meeting chat.
- **On-demand chat sharing** — the agent has a `share_in_chat` tool it only calls when a speaker explicitly asks it to post something to the meeting chat; it never dumps tool output into chat automatically.
- **Chat-based join greeting** — when the bot joins, it posts an intro to the meeting chat explaining who it is, how to address it, and what it can do (realtime voice models don't reliably self-introduce out loud, so this is deliberately chat-based, not spoken).
- **Automated memory extraction** — post-call transcripts are analyzed by an LLM (Groq / OpenAI) into categorized memories (decisions, requirements, commitments, concerns, facts, unresolved questions) and tracked action items.
- **Web dashboard with real accounts** — a Members page for adding/removing who can sign in; no self-serve signup, an existing member has to add you; removing someone revokes their session immediately, not just future logins.
- **Multi-agent management** — create, switch between, and activate multiple MIA agent configs from the dashboard; activating an agent auto-repairs its MCP/database wiring if it was ever set up outside this app (e.g. directly in MeetStream's dashboard).
- **Masked credentials panel** — Agent Settings shows which provider credentials are configured (MeetStream API key, memory-extraction LLM, MCP auth token) without ever exposing full secret values.
- **Company knowledge RAG** — upload PDFs/docs/notes as a separate knowledge base the agent can also draw on.
- **Secure multi-tenant architecture** — every table is scoped by `organization_id`; HMAC-signed webhooks with replay protection; secrets are redacted server-side before any MeetStream API response reaches the browser.

---

## 🏗️ Architecture Overview

```
                              MeetStream Platform
        ┌────────────────┬──────────────────┬─────────────────┐
        │   Bots (Calls) │   MIA Agent (AI) │    Transcript    │
        └───────┬────────┴────────┬─────────┴────────┬────────┘
                │                 │                   │
             Webhooks      MCP + chat-relay        Webhooks
                │           (both HTTP)                │
                ▼                 ▼                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                FastAPI Backend  ·  Railway service            │
   │                                                                 │
   │  ┌────────────┐ ┌─────────────┐ ┌────────────┐ ┌─────────────┐│
   │  │ Webhook API│ │ MCP Server  │ │ Meeting API│ │ Auth/Members││
   │  │            │ │ (9 tools +  │ │            │ │     API     ││
   │  │            │ │ chat-relay) │ │            │ │             ││
   │  └──────┬─────┘ └──────┬──────┘ └─────┬──────┘ └──────┬──────┘│
   │         │              │              │               │       │
   │         ▼              ▼              ▼               ▼       │
   │  ┌───────────────────────────────────────────────────────┐   │
   │  │                        Services                        │   │
   │  │  • MeetStream Client   • Memory Extractor              │   │
   │  │  • Embedding Service   • Ingestion Pipeline             │   │
   │  └────────────────────────────┬────────────────────────────┘   │
   │                               ▼                                │
   │  ┌───────────────────────────────────────────────────────┐   │
   │  │                PostgreSQL 17 + pgvector                 │   │
   │  │  • users (members)          • memories, action_items   │   │
   │  │  • meetings, participants   • meeting_memory_embeddings │   │
   │  │  • transcript_segments      • company_knowledge_embeds  │   │
   │  └───────────────────────────────────────────────────────┘   │
   └─────────────────────────────────────────────────────────────┘
                                ▲
                                │ REST API (session-cookie authenticated)
                                │
                 ┌───────────────────────────────┐
                 │   React Dashboard · Railway     │
                 │   Day view · Search · Agent ·   │
                 │   Members · sign-in gate        │
                 └───────────────────────────────┘
```

The MCP Server handles both the 9 read/write memory tools and the `share_in_chat` chat-relay call (the agent's only path to post into meeting chat, and only on explicit request) — both are called by MeetStream's MIA agent over HTTP, authenticated by the same bearer token. In production, the backend and frontend are separate Railway services with stable public URLs — no tunnel involved. Local development still uses a **Cloudflare Tunnel** to give MeetStream a public URL to reach your dev machine's MCP server and webhooks; see [Local development](#-local-development) below.

---

## 🚀 Using the Hosted App

The dashboard is already deployed — you don't need to run anything locally just to use it.

1. Open the frontend URL (ask whoever set up your organization's deployment for the link).
2. Sign in with an account an existing member has already created for you, or have a member add you from the **Members** page — there's no self-serve signup.
3. From there: launch bots into meetings, browse history, search memory, and manage agents from the dashboard as described below.

Removing a member from the Members page kills their session immediately, so access control is real, not just a UI convenience.

---

## 🛠️ Deploying Your Own Instance

### 1. Prerequisites
- A [MeetStream](https://app.meetstream.ai) account and API key
- An LLM API key for memory extraction (Groq is free-tier and works well; OpenAI/Anthropic also supported)
- A host that can run a Docker container with a stable public URL and a Postgres+pgvector database (Railway is what this project is set up for; Render/Fly.io/a VPS would also work)

### 2. Required environment variables
Set these on your backend service (see `app/config.py` for the full list):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (with pgvector extension available) |
| `MEETSTREAM_API_KEY` | Your MeetStream account API key |
| `MEETSTREAM_AGENT_CONFIG_ID` | Fallback MIA agent config id (the dashboard can override which agent is active without this) |
| `MCP_SERVER_URL` | This backend's own public `/mcp` URL — MeetStream's agent calls back into it |
| `MCP_AUTH_TOKEN` | Any random string — authenticates MCP tool calls and the `share_in_chat` chat-relay endpoint |
| `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Whichever `LLM_PROVIDER` you set, for memory extraction |
| `CORS_ORIGINS` | JSON list including your deployed frontend's origin |
| `API_KEY_SALT` | Used to sign member session cookies — set this to a real secret in production |

Deploy the backend from the repo root (it builds from the top-level `Dockerfile`) and the frontend from `frontend/` with `VITE_API_BASE_URL` set to the backend's public origin at build time.

There's no self-serve signup or shared passphrase — a brand-new deployment has zero members and no way to create one through the UI, so bootstrap the very first account directly against the database once:
```bash
python scripts/create_first_member.py "Your Name" you@example.com yourpassword
```
Every member after that is added from the **Members** page by someone already signed in.

### 3. Local development
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
You'll also need a tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`) so MeetStream can reach your local `/mcp` endpoint and deliver webhooks — set `MCP_SERVER_URL` to that tunnel's `/mcp` URL and push it to your agent config via `PUT /api/agent`. On Windows, `.\start.ps1` automates all of the above (Docker, backend, a fresh tunnel, re-pointing the agent, and the frontend dev server); `.\stop.ps1` tears it down. Run `python scripts/create_first_member.py` once locally too, same as above.

---

## 📖 How to Use It

### From the dashboard
1. **Day view** — pick a date to see every meeting and document from that day. Click **Launch bot** and paste a meeting link (Google Meet / Zoom / Teams) to deploy the agent into a live call. The Title field is just a label for this dashboard — it does not change what the bot is named or addressed as in the meeting.
2. Click into a meeting to see its **Summary**, **Decisions & Memories**, **Action Items** (editable status), **Transcript**, and live **Bot** status — with a **Stop bot** button while it's still recording.
3. **Search memory** — semantic + keyword search across every indexed meeting, ranked by match %.
4. **Agent** — view and edit the live MIA agent's system prompt, voice, model, and response settings; create additional agents and switch which one is active; see masked provider credentials.
5. **Members** — see who can sign into the hub, add someone directly, or remove someone (revokes their session immediately).
6. Upload company documents (PDF/DOCX/TXT/MD/CSV) from the Day view's Documents panel to add them to the company-knowledge RAG.

### From a live meeting
Once a bot joins, it stays silent until addressed by its configured name (e.g. *"MeetStream Companion, what did we decide about the pricing tier last week?"* or *"MeetStream Companion, how many meetings did we have yesterday?"*) — it answers using the MCP tools below, drawing on the same memory the dashboard shows you. Ask it to *"share that in chat"* and it'll post a clean, plain-language version of its answer into the meeting chat — it never does this unprompted.

### From the API directly
```bash
# Deploy a bot into a meeting
curl -X POST https://<your-backend-url>/api/meetings \
  -H "Content-Type: application/json" \
  -b "hub_session=<your session cookie>" \
  -d '{"meeting_url": "https://meet.google.com/xxx-xxxx-xxx", "title": "Sync"}'

# Search meeting memory
curl -X POST https://<your-backend-url>/api/search/memory \
  -H "Content-Type: application/json" \
  -b "hub_session=<your session cookie>" \
  -d '{"query": "pricing decisions"}'
```
Most `/api/*` routes require an authenticated member session (sign in via `POST /api/auth/login` first) — the `/mcp/*` routes the agent itself calls use a separate bearer token (`MCP_AUTH_TOKEN`) instead. Full interactive API docs are available at `/docs` on your backend URL.

---

## 🛠️ MCP Tools Reference

Exposed at `POST /mcp` (JSON-RPC 2.0) and individually at `POST /mcp/tools/{tool_name}`, authenticated with `Authorization: Bearer <MCP_AUTH_TOKEN>`. Every tool's response is rendered as plain natural-language text, not raw JSON — it's what the agent reads and, on request, what can end up in meeting chat.

**Read tools**

| Tool | Purpose | Key Parameters |
|---|---|---|
| `get_current_datetime` | Resolve the actual current date/time — the model has no built-in sense of "today" | *(none)* |
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

The agent also has a `share_in_chat` custom function (posts a message to the meeting chat, only on explicit request) that isn't part of the MCP tool set above — it's registered directly on the MIA agent config.

---

## 🖥️ Local Development Notes

Local dev still runs everything on your own machine, tunneled to the internet. The only thing that reaches the public internet is a **Cloudflare Tunnel**, which forwards traffic back to your local backend so MeetStream's cloud service can deliver webhooks and the live agent can call the MCP server. This means:

- The tunnel's URL changes every time it restarts — `start.ps1` handles regenerating it and re-pointing the agent config automatically.
- The whole local setup only works while your machine is on and `start.ps1` (or the manual equivalent) is running — that's exactly why the production deployment doesn't use a tunnel at all; see [Deploying Your Own Instance](#-deploying-your-own-instance) above.
- Postgres runs in Docker purely because it's the simplest way to get Postgres + the pgvector extension on Windows without a native install — the backend itself runs directly via the local Python venv, not in Docker.

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
  api/          REST endpoints (meetings, documents, agent, members, auth, search, action items, webhooks, health)
  mcp/          MCP server (JSON-RPC + REST tool endpoints) and tool implementations
  middleware/   Per-member session gate (auth_gate.py)
  services/     MeetStream API client, LLM memory extraction, embedding service, ingestion pipeline
  rag/          Hybrid vector+keyword search (meeting memory) and company knowledge RAG
  database/     SQLAlchemy repositories (org-scoped data access)
  models/       ORM models and Pydantic schemas
frontend/       React + Vite dashboard (Day view, Search, Agent settings, Members, sign-in gate)
migrations/     SQL schema (Postgres + pgvector) - additive columns are patched in at startup, see app/main.py
tests/          Unit, integration, and security tests
start.ps1       One-command local dev environment bootstrap (Windows)
stop.ps1        Stops the local backend/frontend/tunnel
```
