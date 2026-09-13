# Contributing

Thanks for your interest. Issues, questions, and pull requests are all welcome.

## Getting set up

Requirements: **Python 3.12**, **Node 22**, and optionally Docker (for Postgres).

```bash
git clone https://github.com/ThalhaAhamed/MeetCompanion.git
cd MeetCompanion
python -m venv .venv
.venv/Scripts/activate            # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
```

Run the API and the UI in two terminals:

```bash
python -m uvicorn app.main:app --port 8000 --reload
npm --prefix frontend run dev      # http://localhost:3000, proxies /api to :8000
```

No `.env` is needed - first run walks you through configuration. Use Ollama or
any provider key you have; SQLite is the default database.

## Where things live

| Area | Path |
| --- | --- |
| HTTP endpoints | `app/api/` (one router per UI page) |
| Business logic | `app/services/` (processing pipeline, notes, extraction) |
| LLM adapters | `app/providers/llm/` - one file per vendor plus a registry entry |
| Search backends | `app/providers/database/` - pgvector vs. portable numpy |
| ORM models and schema patches | `app/models/database.py`, `app/database/bootstrap.py` |
| MCP tools for the voice agent | `app/mcp/tools.py` |
| Web UI | `frontend/src/pages/` and `frontend/src/components/` |
| Desktop shell | `desktop/` |

`docs/architecture.md` explains the layering and the reasons behind it.

## Before opening a pull request

```bash
python -m pytest              # runs on a throwaway SQLite file, no network
npm --prefix frontend run lint
npm --prefix frontend run build
```

CI runs the same suite against SQLite and Postgres (pgvector), builds the
Docker image, and lints and builds the UI.

- Keep pull requests focused. One behaviour change per PR is ideal.
- Add or update tests for behaviour you change. Tests use the `authed_client`
  fixture for signed-in requests; see `tests/conftest.py`.
- Schema changes go in `app/models/database.py` **and**, for existing
  databases, an idempotent patch in `app/database/bootstrap.py` for both
  Postgres and SQLite.
- Never log or return a secret in full. `app/runtime_config.py` masks them.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `ci:` ...).

## Adding an LLM provider

1. Copy `app/providers/llm/ollama.py` (the smallest adapter).
2. Implement `_complete()` and `health_check()`.
3. Register it in `app/providers/llm/__init__.py` with the fields the setup
   form should show.
4. Add a case to `tests/test_llm_providers.py`.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Please don't file public issues for those.
