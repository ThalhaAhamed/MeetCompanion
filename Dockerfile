# MeetStream Companion backend - production image for Railway/Render/Fly/etc.
FROM python:3.12-slim

WORKDIR /app

# System deps needed to build asyncpg/psycopg2/sentence-transformers wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

# Railway (and most PaaS) inject $PORT at runtime - fall back to 8000 for local
# `docker run`. Shell form so the env var actually expands.
ENV PORT=8000
EXPOSE 8000
# Apply the schema migration on every boot (idempotent - warns and continues on
# already-exists) before starting the server. Runs from inside the container so
# it can reach a database on the platform's private network (e.g. Railway's
# postgres.railway.internal), which isn't reachable from outside that network.
CMD ["sh", "-c", "python scripts/setup_db.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
