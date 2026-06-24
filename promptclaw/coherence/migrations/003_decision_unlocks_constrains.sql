-- 003_decision_unlocks_constrains.sql — add forward-looking fields to the decision store.
--
-- unlocks:    what this decision makes possible (dependency tracking)
-- constrains: forward constraints this decision imposes (a machine-checkable predicate
--             for future coherence violations)
--
-- The SQLite store applies the equivalent ALTER TABLE idempotently in
-- SqliteDecisionStore.migrate() (see _ADDED_COLUMNS); this file is the PostgreSQL parity.

ALTER TABLE decisions ADD COLUMN IF NOT EXISTS unlocks TEXT NOT NULL DEFAULT '[]';
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS constrains TEXT NOT NULL DEFAULT '[]';
