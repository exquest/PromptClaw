-- 001_event_store.sql — PostgreSQL DDL for the coherence event store.

CREATE TABLE IF NOT EXISTS coherence_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    phase TEXT DEFAULT '',
    agent TEXT DEFAULT '',
    role TEXT DEFAULT '',
    payload JSONB DEFAULT '{}',
    sequence_number INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coherence_events_run_id ON coherence_events(run_id);
CREATE INDEX IF NOT EXISTS idx_coherence_events_type ON coherence_events(event_type);
CREATE INDEX IF NOT EXISTS idx_coherence_events_timestamp ON coherence_events(timestamp);
