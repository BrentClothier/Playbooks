CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS search;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS core.sources (
    id              BIGSERIAL PRIMARY KEY,
    source_key      TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    agency          TEXT,
    source_type     TEXT NOT NULL,
    base_url        TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.ingest_runs (
    id              BIGSERIAL PRIMARY KEY,
    source_id       BIGINT REFERENCES core.sources(id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    records_seen    BIGINT NOT NULL DEFAULT 0,
    records_written BIGINT NOT NULL DEFAULT 0,
    error_message   TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS core.documents (
    id               BIGSERIAL PRIMARY KEY,
    source_id        BIGINT REFERENCES core.sources(id),
    external_id      TEXT,
    title            TEXT NOT NULL,
    document_type    TEXT,
    agency           TEXT,
    published_at     TIMESTAMPTZ,
    reporting_period TEXT,
    source_url       TEXT,
    object_key       TEXT,
    sha256           TEXT,
    retrieved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    parser_version   TEXT,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS search.document_chunks (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES core.documents(id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    content       TEXT NOT NULL,
    page_number   INTEGER,
    embedding     vector(1536),
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON search.document_chunks
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS documents_metadata_gin_idx
    ON core.documents USING gin (metadata);

CREATE INDEX IF NOT EXISTS document_chunks_content_trgm_idx
    ON search.document_chunks USING gin (content gin_trgm_ops);
