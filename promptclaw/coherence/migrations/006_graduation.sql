-- 006_graduation.sql — PostgreSQL parity for persisted self-graduating-enforcement state (Phase 1c).
-- Single-row table: the engine's enforcement mode + observation stats survive across runs so
-- graduation (monitor -> soft -> full) actually accumulates. SQLite parity in GraduationManager._SCHEMA.

CREATE TABLE IF NOT EXISTS graduation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL,
    total_observations INTEGER NOT NULL DEFAULT 0,
    true_positives INTEGER NOT NULL DEFAULT 0,
    false_positives INTEGER NOT NULL DEFAULT 0,
    runs_in_current_mode INTEGER NOT NULL DEFAULT 0
);
