<div align="center">

<img src="assets/branding/logo-icon.png" alt="Meet Companion" width="128" />

# Meet Companion

### Make meeting data smarter.

[![Latest release](https://img.shields.io/github/v/release/meetstream-ai/companion?include_prereleases&label=release&color=3b4873)](https://github.com/meetstream-ai/companion/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/meetstream-ai/companion/total?color=7b87be)](https://github.com/meetstream-ai/companion/releases)
[![Stars](https://img.shields.io/github/stars/meetstream-ai/companion?style=flat&color=a7a5cb)](https://github.com/meetstream-ai/companion/stargazers)
[![Build](https://img.shields.io/github/actions/workflow/status/meetstream-ai/companion/release.yml?label=build)](https://github.com/meetstream-ai/companion/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-e3b1bc)](LICENSE)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-3b4873)

**Open Source • Bring Your Own AI • Runs On Your Machine**

[Download](#-installation) · [Features](#-features) · [How it works](#%EF%B8%8F-how-it-works) · [Build from source](#%EF%B8%8F-for-developers) · [MeetStream](https://meetstream.ai)

</div>

An AI assistant joins your meetings, and afterwards everything that was said
becomes something you can actually use: decisions, commitments and action items
that are filed into a notebook, searchable semantically, and answerable with
Ask AI — all with a model, database and machine that you choose.

<div align="center">
<img src="docs/screenshots/dashboard.png" alt="Meet Companion dashboard" width="900" />
</div>

<details>
<summary><b>Table of contents</b></summary>

- [Introduction](#-introduction)
- [Why Meet Companion?](#-why-meet-companion)
- [Features](#-features)
- [Installation](#-installation)
- [Features in action](#-features-in-action)
- [How it works](#%EF%B8%8F-how-it-works)
- [Configuration](#%EF%B8%8F-configuration)
- [For developers](#%EF%B8%8F-for-developers)
- [Contributing](#-contributing)
- [Roadmap](#%EF%B8%8F-roadmap)
- [License](#-license)

</details>

## 📖 Introduction

Meet Companion is built on top of [MeetStream](https://meetstream.ai), which
provides the bot that joins Google Meet, Zoom and Teams calls and produces the
transcript. Everything after that point — extraction, memory, notes, search,
the in-call agent's recall — runs in this project, on infrastructure you own.

It ships as a desktop app for Windows, macOS and Linux, and as a self-hostable
web app. Both are the same code.

## 💡 Why Meet Companion?

- **Nothing is hard-wired to a vendor.** Use OpenAI, Anthropic, Gemini, Groq, a
  local Ollama model, or any OpenAI-compatible endpoint. Switch in Settings at
  any time.
- **Your data stays where you put it.** A local SQLite file by default;
  PostgreSQL, Supabase, Neon or any Postgres host when you want it. Embeddings
  are computed locally and never leave the machine.
- **Meetings become notes, not a feed.** Each processed meeting is filed as a
  Markdown note under `Meetings / year / month`, with live action-item
  checkboxes — a notebook you would have organised that way yourself.
- **Fully offline is a real option.** With Ollama and SQLite, no data leaves
  your computer and no API key is needed — the only outbound call is to
  MeetStream when you actually send a bot into a call.

## ✨ Features

- 🎥 **Meeting capture** — send a bot into Google Meet, Zoom or Teams, or import
  bots that already ran on your MeetStream account.
- 🧠 **Memory extraction** — transcripts become structured decisions,
  commitments, requirements, concerns, open questions and action items.
- 📓 **Notebook** — nested folders, tags, favourites, search and sort; a
  rendered Markdown preview with an editor behind it.
- ✅ **Action items that stay in sync** — tick a box in a note and the task
  completes on the dashboard; write `- [ ] call Bob` in any note and it becomes
  a real action item.
- 🔍 **Semantic search** — hybrid vector + keyword search across everything
  ever said.
- 💬 **Ask AI** — questions answered from your own notes and meetings, grounded
  in retrieved content and instructed never to invent details.
- 🕸️ **Knowledge graph** — meetings, people, decisions and action items as an
  explorable graph, with Obsidian-style filters and force controls.
- 🎙️ **In-call recall** — an MCP server lets the in-meeting agent answer "what
  did we decide last time?" while the call is happening.
- 🤖 **Agents** — a template agent that every new agent is created from, with
  provider, model, voice and prompt all editable.
- 🔌 **Provider-agnostic** — LLMs and databases are adapters behind an
  interface; adding one is a single file.

## 📥 Installation

Download from the [latest release](https://github.com/meetstream-ai/companion/releases/latest).

### 🪟 Windows

1. Download **`MeetCompanion-Windows-Setup.exe`**.
2. Run it. SmartScreen will show *Windows protected your PC* because the build
   is not code-signed yet — click **More info → Run anyway**.
3. Meet Companion opens on the first-run setup.

### 🍎 macOS

1. Download **`MeetCompanion-macOS-arm64.dmg`** (Apple silicon) or
   **`MeetCompanion-macOS-x64.dmg`** (Intel).
2. Drag **Meet Companion** into Applications.
3. First launch: **right-click → Open** to get past Gatekeeper (unsigned build).

### 🐧 Linux

```bash
chmod +x MeetCompanion-Linux-x64.AppImage
./MeetCompanion-Linux-x64.AppImage
```

### What happens on first launch

The app walks you through choosing an **AI provider** and **storage**, and then
creates your account. The embedding model (~90 MB) is downloaded once on first
use. All data lives under your user data directory:

| OS | Location |
| --- | --- |
| Windows | `%APPDATA%\meet-companion\workspace` |
| macOS | `~/Library/Application Support/meet-companion/workspace` |
| Linux | `~/.config/meet-companion/workspace` |

> **Self-hosting instead?** See [For developers](#%EF%B8%8F-for-developers) — the
> web app runs from source with two commands, or with Docker Compose.

## 🎯 Features in action

### 📓 Meetings become organised notes

<div align="center">
<img src="docs/screenshots/notebook.png" alt="A meeting filed as a note, with summary, action items and decisions" width="900" />
</div>

Every processed meeting is written as a Markdown note — summary, action items
as checkboxes, then decisions, commitments, requirements, concerns and open
questions — and filed under `Meetings / 2026 / 09 September`, tagged with its
platform, customer and project. Edit it freely; regeneration never overwrites
a note you have touched.

### 🕸️ Knowledge graph

<div align="center">
<img src="docs/screenshots/graph.png" alt="Knowledge graph of meetings, people, memories and action items" width="900" />
</div>

See how meetings, people, decisions and action items connect. Filter by type,
hide orphans, tune node size, link distance and forces — settings persist
between visits.

### 🗄️ Pick any database

<div align="center">
<img src="docs/screenshots/settings-database.png" alt="Database provider picker" width="900" />
</div>

Local SQLite out of the box, or PostgreSQL, Supabase, Neon, Railway or any
other Postgres host. Test the connection, save, and the app switches over
live — no restart.

### 🤖 Your agent, your template

<div align="center">
<img src="docs/screenshots/agent.png" alt="Agent configuration" width="900" />
</div>

A template agent holds the starting system prompt, first message, provider,
model and voice. New agents are created from it; any agent's configuration can
be viewed and edited without switching to it.

## 🏗️ How it works

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

**Providers are interfaces, not conditionals.** Adding an LLM vendor is one
adapter in `app/providers/llm/` plus a registry entry. Each adapter declares the
configuration fields it needs, and that metadata drives the setup forms — which
is why Ollama never shows an API-key box.

**The database is swapped, not abstracted away.** Only two operations differ
between databases — similarity search and keyword search — and those live in
`app/providers/database/`, selected from the live connection's dialect.
Everything else is ordinary SQLAlchemy on portable column types.

**The desktop app is the web app.** An Electron shell starts the bundled server
on a free localhost port and opens it in a window. Embeddings run through ONNX
(`all-MiniLM-L6-v2`), which is what keeps the download at a sane size.

The full write-up is in [docs/architecture.md](docs/architecture.md).

## ⚙️ Configuration

Everything is configurable from **Settings** in the app. Precedence is:

1. process environment variables (containers, CI) — shown read-only in Settings
2. what you saved in the UI
3. `.env` file (self-hosted convenience)
4. built-in defaults

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/meet-companion.db` | Storage; `postgresql+asyncpg://…` for Postgres |
| `LLM_PROVIDER` | `ollama` | `openai` · `anthropic` · `gemini` · `ollama` · `groq` · `openai_compatible` |
| `LLM_MODEL` | per provider | Model name |
| `LLM_API_KEY` | — | Hosted providers only |
| `LLM_BASE_URL` | per provider | Proxies, gateways, self-hosted endpoints |
| `MEETSTREAM_API_KEY` | — | Only needed to send bots into live meetings |
| `MCP_AUTH_TOKEN` | — | Change before exposing the server beyond your machine |

Configuration saved from the UI lives in `data/config.json` next to the SQLite
database. Both are gitignored — `config.json` holds API keys.

## 🛠️ For developers

Requires Python 3.12+ and Node 20+.

```bash
git clone https://github.com/meetstream-ai/companion.git
cd companion

python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
npm --prefix frontend install
```

Run the backend and frontend in two terminals:

```bash
.venv/Scripts/python -m uvicorn app.main:app --port 8000 --reload
```

```bash
npm --prefix frontend run dev
```

Open <http://localhost:3000>. No `.env` is required — first run walks you
through setup.

**Fully offline:** install [Ollama](https://ollama.com), `ollama pull llama3.1`,
and pick *Ollama (local)* during setup.

**PostgreSQL:** `docker compose up -d`, then point `DATABASE_URL` at it (or pick
it in Settings). Schema, indexes and the pgvector extension are created
automatically.

**Tests and lint:**

```bash
.venv/Scripts/python -m pytest          # hermetic: throwaway SQLite, no network
npm --prefix frontend run lint
```

### Building the desktop app

```bash
npm --prefix frontend run build                                        # UI  -> frontend/dist
pip install pyinstaller
pyinstaller desktop/server.spec --noconfirm --distpath desktop/build --workpath desktop/work
npm --prefix desktop install
npm --prefix desktop run dist                                          # -> desktop/release/
```

`npm --prefix desktop start` runs the shell against the frozen server without
packaging. Set `MEET_COMPANION_DATA_DIR` to point it at an existing workspace.
Releases for all three platforms are built by
[`.github/workflows/release.yml`](.github/workflows/release.yml) on a `v*` tag.

## 🤝 Contributing

Contributions are welcome — issues, pull requests, providers, docs.

- **New LLM provider:** one file in `app/providers/llm/` plus a registry entry.
  `ollama.py` is the smallest example.
- **Database-specific code** belongs behind `SearchBackend` in
  `app/providers/database/`; dialect checks anywhere else are a smell.
- **Secrets never leave the API in full.** `app/runtime_config.py` masks them
  and tests assert it.
- Run the tests before opening a pull request. Commits follow
  [Conventional Commits](https://www.conventionalcommits.org/).

## 🗺️ Roadmap

- [ ] Local transcription provider, so capture can run without MeetStream
- [ ] Code-signed Windows and macOS builds
- [ ] MySQL / MariaDB support (listed as *coming soon* in the picker)
- [ ] Re-indexing task after changing embedding models
- [ ] Export (Markdown, JSON) for notes and meetings
- [ ] Auto-update for the desktop app

## 📄 License

[MIT](LICENSE) — use it, change it, ship it. Attribution appreciated.

## 🙏 Acknowledgments

- [MeetStream](https://meetstream.ai) — meeting bots and transcription
- [`all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
  via [fastembed](https://github.com/qdrant/fastembed) — local embeddings
- FastAPI, SQLAlchemy, React, Vite, Tailwind, Electron
