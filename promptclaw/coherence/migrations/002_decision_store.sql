-- 002_decision_store.sql — PostgreSQL DDL for the coherence decision store.

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    title TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    decision_text TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    file_paths TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at);

-- Optional: pgvector column for semantic search (requires pgvector extension)
-- ALTER TABLE decisions ADD COLUMN embedding vector(1536);
-- CREATE INDEX IF NOT EXISTS idx_decisions_embedding ON decisions USING ivfflat (embedding vector_cosine_ops);
