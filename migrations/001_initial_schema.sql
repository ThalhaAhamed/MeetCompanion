-- ============================================================
-- MeetStream Companion — Initial Database Schema
-- ============================================================
-- Runs automatically on first Docker container start
-- via /docker-entrypoint-initdb.d/ mount.
-- ============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Core Tables
-- ============================================================

CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    settings        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    name            VARCHAR(255),
    role            VARCHAR(50) DEFAULT 'member',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, email)
);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    key_hash        VARCHAR(255) NOT NULL UNIQUE,
    key_prefix      VARCHAR(10) NOT NULL,
    name            VARCHAR(255),
    scopes          JSONB DEFAULT '["*"]',
    is_active       BOOLEAN DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Meeting Tables
-- ============================================================

CREATE TABLE meetings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meetstream_bot_id       VARCHAR(255) UNIQUE,
    title                   VARCHAR(500),
    meeting_url             VARCHAR(2000),
    platform                VARCHAR(50),
    customer_name           VARCHAR(255),
    project_name            VARCHAR(255),
    started_at              TIMESTAMPTZ,
    ended_at                TIMESTAMPTZ,
    status                  VARCHAR(50) DEFAULT 'pending',
    summary                 TEXT,
    meetstream_transcript_id VARCHAR(255),
    processing_status       VARCHAR(50) DEFAULT 'pending',
    processing_error        TEXT,
    custom_attributes       JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_meetings_org ON meetings(organization_id);
CREATE INDEX idx_meetings_bot ON meetings(meetstream_bot_id);
CREATE INDEX idx_meetings_status ON meetings(organization_id, status);
CREATE INDEX idx_meetings_customer ON meetings(organization_id, customer_name);
CREATE INDEX idx_meetings_project ON meetings(organization_id, project_name);
CREATE INDEX idx_meetings_started ON meetings(organization_id, started_at DESC);

CREATE TABLE participants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id      UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    name            VARCHAR(255),
    email           VARCHAR(255),
    identifier      VARCHAR(255),
    platform_id     VARCHAR(255),
    role            VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_participants_meeting ON participants(meeting_id);
CREATE INDEX idx_participants_name ON participants(name);

CREATE TABLE transcript_segments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id          UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker             VARCHAR(255),
    speaker_identifier  VARCHAR(255),
    text                TEXT NOT NULL,
    start_time          DOUBLE PRECISION,
    end_time            DOUBLE PRECISION,
    confidence          DOUBLE PRECISION,
    word_data           JSONB,
    segment_index       INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_segments_meeting ON transcript_segments(meeting_id);
CREATE INDEX idx_segments_speaker ON transcript_segments(meeting_id, speaker);

-- ============================================================
-- Memory Tables
-- ============================================================

CREATE TYPE memory_type AS ENUM (
    'decision',
    'commitment',
    'action_item',
    'requirement',
    'concern',
    'preference',
    'fact',
    'project_update',
    'relationship_context',
    'unresolved_question'
);

CREATE TABLE memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id      UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    type            memory_type NOT NULL,
    content         TEXT NOT NULL,
    importance      INTEGER DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    speaker         VARCHAR(255),
    customer_name   VARCHAR(255),
    project_name    VARCHAR(255),
    source_segment_ids UUID[],
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memories_org ON memories(organization_id);
CREATE INDEX idx_memories_meeting ON memories(meeting_id);
CREATE INDEX idx_memories_type ON memories(organization_id, type);
CREATE INDEX idx_memories_customer ON memories(organization_id, customer_name);
CREATE INDEX idx_memories_speaker ON memories(organization_id, speaker);

CREATE TABLE action_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id      UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    memory_id       UUID REFERENCES memories(id) ON DELETE SET NULL,
    owner           VARCHAR(255),
    task            TEXT NOT NULL,
    due_date        DATE,
    status          VARCHAR(50) DEFAULT 'open',
    priority        VARCHAR(20) DEFAULT 'medium',
    notes           TEXT,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_actions_org ON action_items(organization_id);
CREATE INDEX idx_actions_status ON action_items(organization_id, status);
CREATE INDEX idx_actions_owner ON action_items(organization_id, owner);
CREATE INDEX idx_actions_meeting ON action_items(meeting_id);

-- ============================================================
-- Vector Embedding Tables (pgvector)
-- ============================================================

CREATE TABLE meeting_memory_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id      UUID REFERENCES meetings(id) ON DELETE CASCADE,
    memory_id       UUID REFERENCES memories(id) ON DELETE CASCADE,
    source_type     VARCHAR(50) NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(384) NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_mme_org ON meeting_memory_embeddings(organization_id);
CREATE INDEX idx_mme_meeting ON meeting_memory_embeddings(meeting_id);

-- IVFFlat index for vector similarity search
-- Note: IVFFlat requires training data. The index is created with lists=100.
-- For small datasets (<1000 rows), queries will fall back to sequential scan,
-- which is fine. The index kicks in as the dataset grows.
CREATE INDEX idx_mme_embedding ON meeting_memory_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE company_knowledge_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id     UUID,
    source_type     VARCHAR(50) NOT NULL,
    source_name     VARCHAR(500),
    content         TEXT NOT NULL,
    embedding       vector(384) NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cke_org ON company_knowledge_embeddings(organization_id);
CREATE INDEX idx_cke_embedding ON company_knowledge_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- Webhook & Processing Tables
-- ============================================================

CREATE TABLE webhook_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id          VARCHAR(255) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,
    processed       BOOLEAN DEFAULT FALSE,
    processing_error TEXT,
    idempotency_key VARCHAR(500) UNIQUE NOT NULL,
    received_at     TIMESTAMPTZ DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX idx_webhook_bot ON webhook_events(bot_id);
CREATE INDEX idx_webhook_unprocessed ON webhook_events(processed) WHERE NOT processed;

CREATE TABLE processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id      UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    job_type        VARCHAR(100) NOT NULL,
    status          VARCHAR(50) DEFAULT 'pending',
    attempts        INTEGER DEFAULT 0,
    max_attempts    INTEGER DEFAULT 3,
    error           TEXT,
    result          JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_meeting ON processing_jobs(meeting_id);
CREATE INDEX idx_jobs_status ON processing_jobs(status);
CREATE INDEX idx_jobs_pending ON processing_jobs(status, created_at)
    WHERE status IN ('pending', 'retrying');

-- ============================================================
-- Default seed data — single organization for MVP
-- ============================================================

INSERT INTO organizations (id, name, slug, settings)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Default Organization',
    'default',
    '{"meetstream_api_key_configured": false}'
);
