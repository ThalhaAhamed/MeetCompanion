<div align="center">

<img src="assets/branding/logo-icon.png" alt="Meet Companion logo" width="112" />

# Meet Companion

**A bot joins your call. What was said comes back as decisions, action items and searchable notes — on your machine, with the AI model and database you choose.**

[![Release](https://img.shields.io/github/v/release/ThalhaAhamed/MeetCompanion?label=release&color=3b4873)](https://github.com/ThalhaAhamed/MeetCompanion/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/ThalhaAhamed/MeetCompanion/ci.yml?label=CI)](https://github.com/ThalhaAhamed/MeetCompanion/actions)
![Platforms](https://img.shields.io/badge/Windows%20%7C%20macOS%20%7C%20Linux-3b4873)
[![License: MIT](https://img.shields.io/badge/license-MIT-e3b1bc)](LICENSE)

[Quick start](#-quick-start) · [Demo](#-demo) · [Architecture](#%EF%B8%8F-architecture) · [Docker](#-docker) · [Configuration](#%EF%B8%8F-configuration) · [FAQ](#-faq)

</div>

<div align="center">
<img src="docs/media/meeting-to-note.gif" alt="A pasted transcript becomes a summary, action items, memories and a note" width="900" />
</div>

The bot comes from [MeetStream](https://meetstream.ai) (Google Meet, Zoom, Teams); paste a transcript instead and no account is needed. Everything after the transcript runs here, on infrastructure you own: **Markdown notes with live checkboxes**, **semantic search**, **Ask AI** with sources — and the in-call agent can recall "what did we decide last time?" *during* the next meeting.

## 🚀 Quick start

**[⬇ Download the latest release](https://github.com/ThalhaAhamed/MeetCompanion/releases/latest)** (Windows, macOS, Linux) — open it, follow the five-step setup, done. Local SQLite and a local Ollama model need no keys.

```bash
docker compose up -d      # self-hosted → http://localhost:8000
```

## 📥 Installation

| Platform | File | First launch |
|---|---|---|
| **Windows** | `MeetCompanion-Windows-Setup.exe` | SmartScreen: **More info → Run anyway** |
| **macOS** | `…-macOS-arm64.dmg` / `…-x64.dmg` | **Right-click → Open** once |
| **Linux** | `…-Linux-x86_64.AppImage` | `chmod +x`, run |
| **Source** | Python 3.12 + Node 22 | `python scripts/dev.py` — [docs/development.md](docs/development.md) |

> [!TIP]
> No `.env`, no database setup, no migrations: first launch configures everything; the app creates and upgrades its own schema. Data locations: [docs/installation.md](docs/installation.md).

## 💡 Why Meet Companion?

- **Bring your own AI** — OpenAI, Anthropic, Gemini, Groq, xAI, local [Ollama](https://ollama.com), or any OpenAI-compatible endpoint.
- **Your data stays where you put it** — SQLite by default; PostgreSQL, Supabase, Neon or Railway when you want it. Embeddings are computed locally.
- **Notes, not a feed** — each meeting is a Markdown note under `Meetings / year / month` with live checkboxes.
- **Fully offline is real** — Ollama + SQLite: nothing leaves your computer, no API key.

## ✨ Features

- 🎥 **Capture** — a bot in Google Meet, Zoom or Teams; paste a transcript; import past bots.
- 🧠 **Extraction** — decisions, commitments, requirements, concerns, questions, action items with owners and due dates.
- 📓 **Notebook** — folders, tags, favourites, search; Markdown with an editor behind it.
- ✅ **Action items in sync** — tick a box in a note and the task completes; `- [ ] call Bob` becomes a real task.
- 🔍 **Semantic search** — hybrid vector + keyword across everything ever said.
- 💬 **Ask AI** — grounded in notes, meetings and documents (PDF, Word, Markdown, CSV), with sources; never invents.
- 🕸️ **Knowledge graph** — meetings, people, decisions and action items, explorable.
- 🎙️ **In-call recall** — a built-in [MCP](https://modelcontextprotocol.io) server the agent queries live.
- 👥 **Workspaces** — share by join code; owners set what members may add, edit, delete, export, invite.

## 📸 Screenshots

<div align="center">
<img src="docs/screenshots/dashboard.png" alt="Dashboard" width="900" />
<img src="docs/screenshots/settings-database.png" alt="Database settings with Connected status" width="900" />
<img src="docs/screenshots/agent.png" alt="Agent configuration" width="900" />
</div>

## 🎬 Demo

<div align="center">
<img src="docs/media/ask-ai.gif" alt="Ask AI answers with sources" width="900" />
<img src="docs/media/knowledge-graph.gif" alt="Selecting a graph node and filtering by type" width="900" />
<img src="docs/media/workspaces.gif" alt="Member permissions and switching workspaces" width="900" />
</div>

First-run wizard: [docs/installation.md](docs/installation.md).

## 🏗️ Architecture

```
Desktop (Electron) / Browser ─▶ React UI ─▶ FastAPI (auth gate, permissions) ─▶ Services ─▶ Providers
MeetStream agent ─▶ MCP server ─┘                                                        ├─ LLM adapters (7 vendors)
MeetStream webhooks (HMAC) ─▶ /api/webhooks ─┘                                            ├─ SQLite (numpy) · PostgreSQL (pgvector)
                                                                                          └─ MeetStream API
```

**Request flow:** signed session or desktop device key → per-workspace permission → repository scoped to `organization_id` (no row is ever read by id alone). **Meeting data flow:** transcript → segments → LLM extraction to memories and action items (validated JSON, rule-based fallback) → local 384-d embeddings → Markdown note → hybrid search, Ask AI and MCP tools. **Providers are interfaces:** a new LLM is one adapter in `app/providers/llm/`; only similarity and keyword search differ per database (`app/providers/database/`). Schema is Alembic-managed, upgraded at startup. Detail: [docs/architecture.md](docs/architecture.md).

## 🗂️ Project structure

```
app/          api/ (routers) · services/ (pipeline) · providers/ (llm/, database/) · database/ · models/ · migrations/ · mcp/ · rag/
frontend/src/ pages/ · components/ · api.js        desktop/  Electron + PyInstaller        tests/  pytest + vitest        docs/
```

## 🐳 Docker

```bash
docker compose up -d                      # SQLite in a volume
docker compose --profile postgres up -d   # plus pgvector Postgres
```

First visit runs onboarding; config, database and embedding model live in the `data` volume. Set `LLM_PROVIDER`, `LLM_API_KEY`, `DATABASE_URL` to skip onboarding. Image runs in production mode and is booted in CI on every push. Bots need your server reachable (tunnel or public host): [docs/live-meetings.md](docs/live-meetings.md).

## ⚙️ Configuration

Set in **Settings**, saved to `data/config.json`; a set **environment variable always wins** and shows read-only in the UI.

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | The AI for extraction and Ask AI |
| `DATABASE_URL` | `postgresql://…` for a shared or hosted database (default: SQLite) |
| `MEETSTREAM_API_KEY` · `MCP_SERVER_URL` | Bots, and the public URL MeetStream reaches you on |
| `ALLOW_SELF_SIGNUP` | `false` on a public server: only owners add members |

All variables: [docs/configuration.md](docs/configuration.md).

## 🧰 Technology stack

Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · SQLite / PostgreSQL + pgvector · React 19 · Vite · Tailwind CSS 4 · Electron + PyInstaller · local ONNX embeddings (`all-MiniLM-L6-v2`) · MeetStream bots · MCP. Why each: [docs/development.md#tech-stack](docs/development.md#tech-stack).

## 📦 Dependencies

Pinned in [`requirements.txt`](requirements.txt), [`frontend/package.json`](frontend/package.json), [`desktop/package.json`](desktop/package.json). No vendor SDKs (every LLM adapter is plain `httpx`); `pip-audit` in CI; the 90 MB embedding model downloads on first use.

## 🧪 Running tests

```bash
.venv/Scripts/python -m pytest      # 246 backend tests, throwaway SQLite, no network
npm --prefix frontend test          # 15 vitest tests
npm --prefix frontend run lint      # oxlint
```

## 🔁 CI/CD

**Every push** ([`ci.yml`](.github/workflows/ci.yml)): backend suite on SQLite **and** PostgreSQL + pgvector, frontend lint/tests/build, `pip-audit`, Docker image built and booted. **Every `v*` tag** ([`release.yml`](.github/workflows/release.yml)): PyInstaller freeze, Windows/macOS/Linux installers attached to a GitHub release.

## 🗺️ Roadmap

- [ ] Code-signed Windows and macOS builds · [ ] MySQL / MariaDB · [ ] Re-indexing after changing embedding models · [ ] Desktop auto-update

## 🩺 Troubleshooting

| Symptom | Fix |
|---|---|
| Meeting stuck at *Extracting…* | MeetStream cannot reach you: set a public `MCP_SERVER_URL` or tunnel, re-activate the agent |
| *Processed without AI (…)* | The bracket says why; fix the provider in Settings, then **Reprocess** |
| Database *Not reachable* | The banner shows the driver's message; Neon/Supabase strings paste as-is |

More: [docs/troubleshooting.md](docs/troubleshooting.md).

## ❓ FAQ

**Does my data leave my machine?** Only where you point it; SQLite + Ollama, nothing leaves — [docs/security.md](docs/security.md).
**Do I need MeetStream?** Only to send a bot into a call. Upload, search and Ask AI work without it.
**Can my team share a workspace?** Yes — a shared Postgres, a join code, owner-set permissions — [docs/workspaces.md](docs/workspaces.md).
**Is it free?** MIT, no accounts, no telemetry; you pay only the provider you choose, or nothing with Ollama + SQLite.

## 📚 Documentation

[Installation](docs/installation.md) · [Configuration](docs/configuration.md) · [Live meetings](docs/live-meetings.md) · [Workspaces & export](docs/workspaces.md) · [Security & privacy](docs/security.md) · [Troubleshooting](docs/troubleshooting.md) · [Developers](docs/development.md) · [Architecture](docs/architecture.md) · [Agent guide](AGENTS.md) · [Security policy](SECURITY.md)

## 🤝 Contributing

Issues, pull requests, providers and docs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Run the tests first; commits follow [Conventional Commits](https://www.conventionalcommits.org/).

## 📄 License

[MIT](LICENSE). Built on [MeetStream](https://meetstream.ai), [fastembed](https://github.com/qdrant/fastembed), FastAPI, SQLAlchemy, React, Vite, Tailwind, Electron.
