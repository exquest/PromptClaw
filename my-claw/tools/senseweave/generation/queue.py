"""SQLite-backed skeleton for generation queue state."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSON NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_error TEXT
);
"""


QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
BLOCKED = "blocked"


@dataclass(frozen=True)
class QueueItem:
    id: int
    idempotency_key: str
    payload: Any
    status: str
    attempts: int
    source: str | None
    last_error: str | None
    created_at: float
    updated_at: float


@contextmanager
def connect_generation_queue_db(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open the queue DB, creating its parent directory and schema if needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate_generation_queue_schema(conn)
        yield conn
    finally:
        conn.close()


class GenerationQueue:
    """Thin wrapper around the generation queue database."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        client: Any | None = None,
        cache: Any | None = None,
        budget: Any | None = None,
        storage: Any | None = None,
        validator: Callable[[Any, Any], bool] | None = None,
        max_concurrent: int = 1,
        max_attempts: int = 3,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self.db_path = Path(db_path)
        self.client = client
        self.cache = cache
        self.budget = budget
        self.storage = storage
        self.validator = validator
        self.max_concurrent = max_concurrent
        self.max_attempts = max_attempts
        self._clock = clock or time.time
        self._last_error: dict[str, Any] | None = None
        self._last_success: dict[str, Any] | None = None
        with connect_generation_queue_db(self.db_path):
            pass

    async def run_worker(self, *, idle_sleep: float = 0.1) -> None:
        """Run worker loops forever, bounded by ``max_concurrent``."""
        if self.max_concurrent == 1:
            await self._worker_loop(idle_sleep)
            return

        tasks = [
            asyncio.create_task(self._worker_loop(idle_sleep))
            for _ in range(self.max_concurrent)
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def process_one(self) -> bool:
        """Process one queued item, returning True if work was done."""
        item = self.dequeue()
        if not item:
            return False

        try:
            if self._complete_from_cache(item):
                return True
            if not self._budget_allows(item.payload):
                self.mark_blocked(item.id)
                return True

            result = self._generate_sync(item.payload)
            if not self._validate_result(result, item.payload):
                self.mark_failed(
                    item.id, error="validation_rejected", terminal=True
                )
                return True

            self._store_success(item.payload, result)
            if self.mark_done(item.id, source="generated"):
                self._record_success(item, result)
            return True
        except Exception as exc:
            self.mark_failed(item.id, error=str(exc))
            return True

    def diagnostic_snapshot(self, *, worker_pid: int) -> dict[str, Any]:
        """Return the worker diagnostic payload written for operators."""
        queue_depth, last_error = self._queue_status()
        cache_size_bytes, cache_entries = _cache_status(self.cache)
        today_spent_usd, month_spent_usd = _budget_status(self.budget)
        return {
            "queue_depth": queue_depth,
            "cache_size_bytes": cache_size_bytes,
            "cache_entries": cache_entries,
            "today_spent_usd": today_spent_usd,
            "month_spent_usd": month_spent_usd,
            "last_error": self._last_error or last_error,
            "last_success": self._last_success,
            "worker_pid": int(worker_pid),
            "last_updated": float(self._clock()),
        }

    def enqueue(self, payload: Any, idempotency_key: str) -> int:
        """Insert a queued item, or return the existing row id on duplicate key."""
        payload_json = json.dumps(payload)
        now = self._clock()
        with connect_generation_queue_db(self.db_path) as conn:
            conn.execute(
                """INSERT INTO queue_items
                       (idempotency_key, payload, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(idempotency_key) DO NOTHING""",
                (idempotency_key, payload_json, QUEUED, now, now),
            )
            row = conn.execute(
                "SELECT id FROM queue_items WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return int(row["id"])

    def dequeue(self) -> QueueItem | None:
        """Atomically claim the oldest queued item for processing."""
        now = self._clock()
        with connect_generation_queue_db(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """UPDATE queue_items
                       SET status = ?,
                           attempts = attempts + 1,
                           updated_at = ?
                       WHERE id = (
                           SELECT id
                           FROM queue_items
                           WHERE status IN (?, ?)
                           ORDER BY id ASC
                           LIMIT 1
                       )
                       RETURNING *""",
                    (RUNNING, now, QUEUED, BLOCKED),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        if row is None:
            return None
        return _row_to_queue_item(row)

    def mark_done(self, item_id: int, *, source: str = "generated") -> bool:
        """Mark a running item as done."""
        return self._mark_running_item(item_id, DONE, source=source)

    def mark_failed(
        self,
        item_id: int,
        *,
        error: str | None = None,
        terminal: bool = False,
    ) -> bool:
        """Mark a running item failed.

        With ``terminal=True`` the item is marked ``failed`` unconditionally —
        used for validation rejection where retrying cannot help. Otherwise the
        item is requeued for retry while ``attempts`` remains below
        ``max_attempts``; on the final attempt it transitions to ``failed``.
        ``error`` is recorded in ``last_error`` either way.
        """
        now = self._clock()
        with connect_generation_queue_db(self.db_path) as conn:
            if terminal:
                cursor = conn.execute(
                    """UPDATE queue_items
                       SET status = ?, last_error = ?, updated_at = ?
                       WHERE id = ? AND status = ?""",
                    (FAILED, error, now, item_id, RUNNING),
                )
            else:
                cursor = conn.execute(
                    """UPDATE queue_items
                       SET status = CASE
                               WHEN attempts >= ? THEN ?
                               ELSE ?
                           END,
                           last_error = ?,
                           updated_at = ?
                       WHERE id = ? AND status = ?""",
                    (self.max_attempts, FAILED, QUEUED, error, now, item_id, RUNNING),
                )
        changed = cursor.rowcount == 1
        if changed and error:
            self._last_error = {"ts": float(now), "message": str(error)}
        return changed

    def mark_blocked(self, item_id: int) -> bool:
        """Mark a running item blocked so a later worker iteration can retry it."""
        return self._mark_running_item(item_id, BLOCKED)

    async def _worker_loop(self, idle_sleep: float) -> None:
        while True:
            outcome = await self._process_next_async()
            if outcome != "processed":
                await asyncio.sleep(idle_sleep)

    async def _process_next_async(self) -> str:
        item = self.dequeue()
        if item is None:
            return "idle"

        try:
            if self._complete_from_cache(item):
                return "processed"
            if not self._budget_allows(item.payload):
                self.mark_blocked(item.id)
                return "blocked"

            result = await self._generate_async(item.payload)
            if not self._validate_result(result, item.payload):
                self.mark_failed(
                    item.id, error="validation_rejected", terminal=True
                )
                return "processed"

            self._store_success(item.payload, result)
            if self.mark_done(item.id, source="generated"):
                self._record_success(item, result)
            return "processed"
        except Exception as exc:
            self.mark_failed(item.id, error=str(exc))
            return "processed"

    def _complete_from_cache(self, item: QueueItem) -> bool:
        cached = self._cache_get(item.payload)
        if cached is None:
            return False
        if not self.mark_done(item.id, source="cache"):
            return False
        self._record_success(item, cached)
        return True

    def _cache_get(self, payload: Any) -> Any | None:
        if self.cache is None:
            return None
        get = getattr(self.cache, "get", None)
        if not callable(get):
            return None
        return get(payload)

    def _budget_allows(self, payload: Any) -> bool:
        if self.budget is None:
            return True
        allow = getattr(self.budget, "allow", None)
        if not callable(allow):
            return True
        decision = allow(payload)
        if isinstance(decision, tuple):
            return bool(decision[0])
        return bool(decision)

    def _generate_sync(self, payload: Any) -> Any:
        if self.client is None:
            return None
        return self.client.generate(payload)

    async def _generate_async(self, payload: Any) -> Any:
        if self.client is None:
            return None
        return await asyncio.to_thread(self.client.generate, payload)

    def _validate_result(self, result: Any, payload: Any) -> bool:
        if self.validator is not None:
            return bool(self.validator(result, payload))
        validate = getattr(self.client, "validate", None)
        if not callable(validate):
            return True
        return bool(validate(result, payload))

    def _store_success(self, payload: Any, result: Any) -> None:
        if self.storage is not None and result is not None:
            self.storage.save(result, payload)
        if self.cache is not None and result is not None:
            set_cache = getattr(self.cache, "set", None)
            if callable(set_cache):
                set_cache(payload, result)
        if self.budget is not None:
            record = getattr(self.budget, "record", None)
            if callable(record):
                record(result)
                return
            pay = getattr(self.budget, "pay", None)
            if callable(pay):
                pay(payload, result)

    def _mark_running_item(
        self,
        item_id: int,
        status: str,
        *,
        source: str | None = None,
    ) -> bool:
        now = self._clock()
        with connect_generation_queue_db(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE queue_items
                   SET status = ?, source = ?, updated_at = ?
                   WHERE id = ? AND status = ?""",
                (status, source, now, item_id, RUNNING),
            )
        return cursor.rowcount == 1

    def _queue_status(self) -> tuple[int, dict[str, Any] | None]:
        with connect_generation_queue_db(self.db_path) as conn:
            queue_depth = conn.execute(
                """SELECT COUNT(*)
                   FROM queue_items
                   WHERE status IN (?, ?, ?)""",
                (QUEUED, RUNNING, BLOCKED),
            ).fetchone()[0]
            last_error = conn.execute(
                """SELECT updated_at, last_error
                   FROM queue_items
                   WHERE last_error IS NOT NULL
                   ORDER BY updated_at DESC, id DESC
                   LIMIT 1"""
            ).fetchone()
        if last_error is None:
            return int(queue_depth), None
        return int(queue_depth), {
            "ts": float(last_error["updated_at"]),
            "message": str(last_error["last_error"]),
        }

    def _record_success(self, item: QueueItem, result: Any) -> None:
        self._last_success = {
            "ts": float(self._clock()),
            "hash": _status_hash(item.payload, item.idempotency_key),
            "model": _status_model(item.payload, result),
            "cost": _status_cost(result),
        }


def _migrate_generation_queue_schema(conn: sqlite3.Connection) -> None:
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(queue_items)")}
    if "source" not in columns:
        conn.execute("ALTER TABLE queue_items ADD COLUMN source TEXT")
    if "last_error" not in columns:
        conn.execute("ALTER TABLE queue_items ADD COLUMN last_error TEXT")


def _row_to_queue_item(row: sqlite3.Row) -> QueueItem:
    return QueueItem(
        id=int(row["id"]),
        idempotency_key=str(row["idempotency_key"]),
        payload=json.loads(str(row["payload"])),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        source=row["source"] if row["source"] is None else str(row["source"]),
        last_error=(
            row["last_error"] if row["last_error"] is None else str(row["last_error"])
        ),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _cache_status(cache: Any) -> tuple[int, int]:
    if cache is None:
        return 0, 0
    entries = getattr(cache, "_entries", None)
    if not isinstance(entries, Mapping):
        return 0, 0
    size_bytes = 0
    for entry in entries.values():
        size_bytes += int(getattr(entry, "size_bytes", 0))
    return size_bytes, len(entries)


def _budget_status(budget: Any) -> tuple[float, float]:
    if budget is None:
        return 0.0, 0.0
    state = getattr(budget, "state", None)
    if state is None:
        return 0.0, 0.0
    return (
        float(getattr(state, "today_spent_usd", 0.0)),
        float(getattr(state, "month_spent_usd", 0.0)),
    )


def _status_hash(payload: Any, fallback: str) -> str:
    value = _field(payload, "request_hash", "hash")
    if callable(value):
        value = value()
    if value is None:
        return str(fallback)
    return str(value)


def _status_model(payload: Any, result: Any) -> str:
    value = _field(result, "model_used", "model", "model_name")
    if value is None:
        value = _field(payload, "model", "model_name")
    return "" if value is None else str(value)


def _status_cost(result: Any) -> float:
    value = _field(result, "cost_usd", "cost")
    if value is None:
        return 0.0
    return float(value)


def _field(obj: Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None
