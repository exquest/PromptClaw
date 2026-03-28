"""Append-only event store backends (SQLite and PostgreSQL)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import CoherenceEvent


@runtime_checkable
class EventStoreBackend(Protocol):
    """Interface for event store backends."""

    def append(self, event: CoherenceEvent) -> None: ...
    def replay(self, run_id: str) -> list[CoherenceEvent]: ...
    def replay_all(self) -> list[CoherenceEvent]: ...
    def count(self, run_id: str | None = None) -> int: ...
    def migrate(self) -> None: ...


class SqliteEventStore:
    """SQLite-backed event store using stdlib sqlite3."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        phase TEXT DEFAULT '',
        agent TEXT DEFAULT '',
        role TEXT DEFAULT '',
        payload TEXT DEFAULT '{}',
        sequence_number INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def migrate(self) -> None:
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    def append(self, event: CoherenceEvent) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO events (event_id, run_id, timestamp, event_type, phase, agent, role, payload, sequence_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.run_id,
                event.timestamp,
                event.event_type,
                event.phase,
                event.agent,
                event.role,
                json.dumps(event.payload),
                event.sequence_number,
            ),
        )
        conn.commit()

    def replay(self, run_id: str) -> list[CoherenceEvent]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY sequence_number ASC",
            (run_id,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def replay_all(self) -> list[CoherenceEvent]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events ORDER BY timestamp ASC, sequence_number ASC"
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def count(self, run_id: str | None = None) -> int:
        conn = self._get_conn()
        if run_id:
            row = conn.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> CoherenceEvent:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return CoherenceEvent(
            event_id=row["event_id"],
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            event_type=row["event_type"],
            phase=row["phase"],
            agent=row["agent"],
            role=row["role"],
            payload=payload,
            sequence_number=row["sequence_number"],
        )


class PostgresEventStore:
    """PostgreSQL-backed event store with optional Redis caching."""

    def __init__(self, database_url: str, redis_url: str = "") -> None:
        self.database_url = database_url
        self.redis_url = redis_url
        self._pool = None
        self._redis = None

    def _get_pool(self):
        if self._pool is None:
            try:
                from psycopg2 import pool
                self._pool = pool.ThreadedConnectionPool(
                    minconn=1, maxconn=5, dsn=self.database_url
                )
            except ImportError:
                raise RuntimeError(
                    "psycopg2 is required for PostgreSQL event store. "
                    "Install with: pip install promptclaw[coherence-pg]"
                )
        return self._pool

    def _get_redis(self):
        if self._redis is None and self.redis_url:
            try:
                import redis
                self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def migrate(self) -> None:
        p = self._get_pool()
        conn = p.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
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
            """)
            conn.commit()
        finally:
            p.putconn(conn)

    def append(self, event: CoherenceEvent) -> None:
        p = self._get_pool()
        conn = p.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO coherence_events (event_id, run_id, timestamp, event_type, phase, agent, role, payload, sequence_number) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    event.event_id,
                    event.run_id,
                    event.timestamp,
                    event.event_type,
                    event.phase,
                    event.agent,
                    event.role,
                    json.dumps(event.payload),
                    event.sequence_number,
                ),
            )
            conn.commit()
        finally:
            p.putconn(conn)

        # Invalidate Redis cache for this run
        r = self._get_redis()
        if r:
            try:
                r.delete(f"coherence:state:{event.run_id}")
            except Exception:
                pass

    def replay(self, run_id: str) -> list[CoherenceEvent]:
        p = self._get_pool()
        conn = p.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT event_id, run_id, timestamp, event_type, phase, agent, role, payload, sequence_number "
                "FROM coherence_events WHERE run_id = %s ORDER BY sequence_number ASC",
                (run_id,),
            )
            rows = cur.fetchall()
        finally:
            p.putconn(conn)
        return [
            CoherenceEvent(
                event_id=r[0], run_id=r[1], timestamp=str(r[2]), event_type=r[3],
                phase=r[4], agent=r[5], role=r[6],
                payload=r[7] if isinstance(r[7], dict) else json.loads(r[7]),
                sequence_number=r[8],
            )
            for r in rows
        ]

    def replay_all(self) -> list[CoherenceEvent]:
        p = self._get_pool()
        conn = p.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT event_id, run_id, timestamp, event_type, phase, agent, role, payload, sequence_number "
                "FROM coherence_events ORDER BY timestamp ASC, sequence_number ASC"
            )
            rows = cur.fetchall()
        finally:
            p.putconn(conn)
        return [
            CoherenceEvent(
                event_id=r[0], run_id=r[1], timestamp=str(r[2]), event_type=r[3],
                phase=r[4], agent=r[5], role=r[6],
                payload=r[7] if isinstance(r[7], dict) else json.loads(r[7]),
                sequence_number=r[8],
            )
            for r in rows
        ]

    def count(self, run_id: str | None = None) -> int:
        p = self._get_pool()
        conn = p.getconn()
        try:
            cur = conn.cursor()
            if run_id:
                cur.execute("SELECT COUNT(*) FROM coherence_events WHERE run_id = %s", (run_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM coherence_events")
            row = cur.fetchone()
        finally:
            p.putconn(conn)
        return row[0] if row else 0

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()
            self._pool = None
