-- 004_tension_store.sql — PostgreSQL DDL for the coherence tension store (P1).
--
-- The tension store records *held* contradictions — surfaced to agents as
-- "HOLD — do not silently collapse" rather than blocked. The SQLite store embeds the
-- equivalent schema in SqliteTensionStore._SCHEMA; this file is the PostgreSQL parity.

CREATE TABLE IF NOT EXISTS tensions (
    tension_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    statement TEXT NOT NULL,
    dialectic_state TEXT NOT NULL DEFAULT '',
    resolution_criterion TEXT NOT NULL DEFAULT '',
    between_refs TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open',
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_tensions_status ON tensions(status);
CREATE INDEX IF NOT EXISTS idx_tensions_created ON tensions(created_at);
