-- 005_trust.sql — PostgreSQL parity for the persisted per-agent trust store (Phase 1c).
-- The SQLite store embeds the equivalent schema in TrustManager._SCHEMA; this is the PG parity.

CREATE TABLE IF NOT EXISTS trust_scores (
    agent TEXT PRIMARY KEY,
    score DOUBLE PRECISION NOT NULL,
    hard_violations INTEGER NOT NULL DEFAULT 0,
    soft_violations INTEGER NOT NULL DEFAULT 0,
    compliant_actions INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT ''
);
