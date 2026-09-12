# Architecture

Notes for contributors on how Meet Companion is put together and why.

## Principles

1. **No vendor in the application layer.** Business logic never knows which LLM
   or database is in use. That knowledge lives in `app/providers/`.
2. **Local-first.** The default configuration runs with no external services:
   SQLite for storage, Ollama for inference, local embeddings.
3. **Declarative configuration wins.** An environment variable that is actually
   set always beats a value saved in the UI, so containers stay reproducible.
4. **Fail usefully.** A missing provider, unreachable host or absent model
   produces an actionable message, not a stack trace.

## Layers

```
UI → API → services → providers → external systems
```

- `app/api/` — HTTP surface. Validation and serialisation only; no vendor logic.
- `app/services/` — application logic (memory extraction, embeddings, provider
  resolution).
- `app/database/` — repositories. All queries are organization-scoped.
- `app/providers/` — the swappable parts.
- `app/models/` — ORM models plus the portable column types that let one schema
  target several databases.

## LLM providers

Every adapter implements `LLMProvider` (`app/providers/llm/base.py`):

```python
async def complete(messages, *, json_mode, temperature, max_tokens) -> str
async def health_check() -> ProviderStatus
```

`complete_json()` is provided by the base class. Providers that support native
JSON output declare `supports_json_mode = True`; the rest fall back to a shared
extractor that recovers JSON from fenced or prose-wrapped replies.

Adapters are built on `httpx` rather than vendor SDKs. This keeps the dependency
surface small and makes adding a provider a code change instead of a dependency
change.

### Adding a provider

1. Create `app/providers/llm/<name>.py` with a subclass of `LLMProvider`.
2. Register the class in `PROVIDERS` in `app/providers/llm/__init__.py`.
3. Add a `ProviderDescriptor` describing **only** the configuration fields it
   actually needs. That metadata renders the onboarding and settings forms, so
   listing an irrelevant field makes it appear in the UI.
4. Add a wire-format test alongside the existing ones in
   `tests/test_llm_providers.py`.

Anything speaking the OpenAI chat-completions format needs no new adapter at
all — subclass `OpenAICompatibleProvider` and change the default base URL, which
is all `GroqProvider` does.

## Database providers

Only two operations genuinely differ between databases:

| Operation | PostgreSQL | Everything else |
| --- | --- | --- |
| Similarity | pgvector `<=>` over an ivfflat index | cosine similarity with numpy |
| Keyword | `tsvector` / `ts_rank` | distinct term matches scored with `LIKE` |

Both live behind `SearchBackend` (`app/providers/database/`) and the backend is
chosen from the live connection's dialect, so changing `DATABASE_URL` is the
only step needed to switch.

Both backends clamp similarity to `[0, 1]` identically. Postgres derives it as
`max(0, 1 - distance)`; the portable path would otherwise return negative values
for opposed vectors and the same `min_similarity` threshold would mean different
things depending on the database.

The portable backend scans candidate rows rather than using an index, so it is
O(n) in corpus size. That is comfortably fast for one person's meeting history;
shared or very large deployments should use Postgres.

### Portable column types

`app/models/types.py` keeps native Postgres representations where they exist and
falls back elsewhere:

| Type | PostgreSQL | Elsewhere |
| --- | --- | --- |
| `GUID` | `uuid` | `CHAR(36)` |
| `GUIDArray` | `uuid[]` | JSON array |
| `JSONDocument` | `jsonb` | `json` |
| `Embedding` | `vector(n)` | JSON array of floats |

Read JSON keys with `col["k"].as_string()`, which works on both. JSONB-only
`.astext` silently breaks on SQLite.

## Schema management

The schema is created from ORM metadata at startup, so a new database needs no
migration step. Indexes are declared on the models and therefore created on
every dialect; the ivfflat indexes are Postgres-only and created alongside the
`vector` extension in `app/main.py`.

Postgres databases created before several columns existed get idempotent
`ADD COLUMN IF NOT EXISTS` patches, skipped entirely on other dialects.

## Configuration

Precedence, highest first:

1. An environment variable that is explicitly set
2. The value saved in `data/config.json` during onboarding or in Settings
3. The provider's documented default

`describe_environment_managed()` reports which fields the environment owns so
the UI can render them read-only, rather than appearing to accept changes that
are silently overridden.

Secrets are accepted but never returned — responses carry masked previews only,
and omitting a key on save keeps the stored one, so a settings form that never
saw the real key cannot erase it.

## Retrieval

Meeting content is chunked, embedded and stored in
`meeting_memory_embeddings`. Search fuses vector and keyword results with
reciprocal rank fusion (`app/rag/retrieval.py`), and re-ranks by any date the
query mentions.

Notes carry their embedding on the row itself. `Note` therefore satisfies the
`SearchBackend` contract (`content` + `embedding`) directly, which is why Ask AI
retrieval needs no separate index table.

## Multi-tenancy

Every domain row is scoped by `organization_id`, and repositories require it.
A default workspace is created on first run so a fresh install is immediately
usable. Sessions are signed cookies; membership is re-checked against the
database on every request, so removing a member revokes their session at once.

## Testing

The suite is hermetic — a throwaway SQLite file, no Postgres, no Docker, no
network. HTTP calls to providers are mocked with `pytest_httpx`.

The schema is rebuilt per test so rows from one test cannot leak into the next.
`authed_client` signs a real session cookie rather than overriding the auth
dependency, so the session gate is exercised the way production runs it.
