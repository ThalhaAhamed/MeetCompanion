# MeetStream Companion 🎙️🧠

> **Persistent AI Meeting Companion** powered by **MeetStream MIA**, **PostgreSQL/pgvector**, and **Model Context Protocol (MCP)**.

MeetStream Companion joins your Google Meet, Zoom, and Microsoft Teams calls via MeetStream Infrastructure Agents (MIA), remembers all past conversations, automatically extracts decisions and action items, and answers questions during live meetings with full historical context.

---

## 🌟 Key Features

1. **MeetStream MIA Agent Integration**: Realtime & Pipeline AI voice agents that speak and interact inside live video calls.
2. **Dual-Source Meeting Memory RAG**: Indexes both raw timestamped transcript chunks and structured extracted memories (decisions, requirements, commitments, facts) with metadata filtering.
3. **Model Context Protocol (MCP) Server**: Exposes 4 secure read-only tools to the MIA agent via Streamable HTTP (`/mcp`):
   - `search_meeting_memory`
   - `get_meeting`
   - `get_previous_meetings`
   - `get_action_items`
4. **Automated Memory Extraction**: Analyzes post-call transcripts using LLMs (OpenAI GPT-4.1 / Groq / Anthropic) into categorized memories and tracked action items.
5. **Secure Multi-Tenant Architecture**: Strict organization-level isolation with server-enforced scoping, HMAC-SHA256 webhook verification, and replay protection.
6. **Company Knowledge RAG**: Supplementary document RAG for querying company policies, onboarding guides, and documentation.

---

## 🏗️ Architecture Overview

```
                          MeetStream Platform
             ┌───────────────┬─────────────────┬──────────────┐
             │  Bots (Calls) │  MIA Agent (AI) │ Transcript   │
             └───────┬───────┴────────┬────────┴──────┬───────┘
                     │                │               │
                 Webhooks         MCP (HTTP)     Webhooks
                     │                │               │
                     ▼                ▼               ▼
          ┌───────────────────────────────────────────────────────┐
          │               FastAPI Companion Server               │
          │                                                       │
          │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
          │  │ Webhook API  │  │ MCP Server  │  │ Meeting API  │  │
          │  └───────┬──────┘  └──────┬──────┘  └──────┬───────┘  │
          │          │                │                │          │
          │          ▼                ▼                ▼          │
          │  ┌─────────────────────────────────────────────────┐  │
          │  │                   Services                      │  │
          │  │  • MeetStream Client   • Memory Extractor       │  │
          │  │  • Ingestion Pipeline  • Embedding Service      │  │
          │  └────────────────────────┬────────────────────────┘  │
          │                           │                           │
          │                           ▼                           │
          │  ┌─────────────────────────────────────────────────┐  │
          │  │           PostgreSQL 17 + pgvector              │  │
          │  │  • meetings           • memories                │  │
          │  │  • transcript_segs    • action_items            │  │
          │  │  • meeting_memory_embeddings (vector 384)       │  │
          │  │  • company_knowledge_embeddings                 │  │
          │  └─────────────────────────────────────────────────┘  │
          └───────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Docker & Docker Compose (for PostgreSQL + pgvector)
- MeetStream API Key ([app.meetstream.ai](https://app.meetstream.ai))

### 2. Setup Environment
```bash
# Copy template and configure API keys
cp .env.example .env
```

Edit `.env`:
```env
MEETSTREAM_API_KEY=your_meetstream_api_key
OPENAI_API_KEY=your_openai_api_key
MCP_AUTH_TOKEN=your_mcp_secret_token
```

### 3. Start Database
```bash
docker compose up -d
python scripts/setup_db.py
```

### 4. Start Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🛠️ MCP Tools Reference

| Tool | Purpose | Key Parameters |
|---|---|---|
| `search_meeting_memory` | Semantic search across all previous meetings | `query`, `customer_name`, `speaker`, `limit` |
| `get_meeting` | Retrieve full meeting transcript & summary | `meeting_id`, `title` |
| `get_previous_meetings` | List recent meetings | `customer_name`, `project_name`, `limit` |
| `get_action_items` | List tasks & commitments | `owner`, `status`, `limit` |

---

## 🧪 Testing

Run the full automated test suite (17+ unit, integration, and security tests):

```bash
python -m pytest tests/ -v
```

Run the interactive pipeline demonstration:

```bash
python scripts/test_memory_pipeline.py
```
