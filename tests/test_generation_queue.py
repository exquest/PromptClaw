from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.queue import (  # noqa: E402
    GenerationQueue,
    connect_generation_queue_db,
)


class TickClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        current = self.value
        self.value += 1.0
        return current


def _queue_row(queue: GenerationQueue, row_id: int) -> sqlite3.Row:
    with sqlite3.connect(queue.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM queue_items WHERE id = ?",
            (row_id,),
        ).fetchone()
    assert row is not None
    return row


def test_generation_queue_constructor_creates_queue_items_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state" / "generation_queue.sqlite"

    queue = GenerationQueue(db_path)

    assert queue.db_path == db_path
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]: {"type": row[2], "not_null": bool(row[3]), "default": row[4]}
            for row in conn.execute("PRAGMA table_info(queue_items)")
        }
        conn.execute(
            """INSERT INTO queue_items
               (idempotency_key, payload, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("request-1", '{"prompt": "bells"}', "queued", 1.0, 1.0),
        )
        try:
            conn.execute(
                """INSERT INTO queue_items
                   (idempotency_key, payload, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("request-1", '{"prompt": "bells"}', "queued", 1.0, 1.0),
            )
        except sqlite3.IntegrityError:
            duplicate_rejected = True
        else:
            duplicate_rejected = False

    assert list(columns) == [
        "id",
        "idempotency_key",
        "payload",
        "status",
        "attempts",
        "source",
        "created_at",
        "updated_at",
        "last_error",
    ]
    assert columns["payload"]["type"] == "JSON"
    assert columns["attempts"]["default"] == "0"
    assert duplicate_rejected is True


def test_connect_generation_queue_db_applies_schema_idempotently(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "generation_queue.sqlite"

    with connect_generation_queue_db(db_path) as conn:
        conn.execute(
            """INSERT INTO queue_items
               (idempotency_key, payload, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("request-1", "{}", "queued", 1.0, 1.0),
        )

    with connect_generation_queue_db(db_path) as conn:
        rows = conn.execute("SELECT idempotency_key FROM queue_items").fetchall()

    assert [row[0] for row in rows] == ["request-1"]


def test_enqueue_first_insert_creates_queued_row(tmp_path: Path) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite")

    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    with sqlite3.connect(queue.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, idempotency_key, payload, status, attempts FROM queue_items"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["id"] == row_id
    assert rows[0]["idempotency_key"] == "request-1"
    assert json.loads(rows[0]["payload"]) == {"prompt": "bells"}
    assert rows[0]["status"] == "queued"
    assert rows[0]["attempts"] == 0


def test_enqueue_duplicate_key_is_noop_and_returns_existing_id(tmp_path: Path) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite")

    first_id = queue.enqueue({"prompt": "bells"}, "request-1")
    second_id = queue.enqueue({"prompt": "different"}, "request-1")

    assert second_id == first_id
    with sqlite3.connect(queue.db_path) as conn:
        rows = conn.execute(
            "SELECT payload FROM queue_items WHERE idempotency_key = ?",
            ("request-1",),
        ).fetchall()

    assert len(rows) == 1
    assert json.loads(rows[0][0]) == {"prompt": "bells"}


def test_enqueue_concurrent_calls_return_same_id(tmp_path: Path) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite")
    worker_count = 8
    barrier = Barrier(worker_count)

    def worker(index: int) -> int:
        barrier.wait()
        return queue.enqueue({"prompt": "bells", "n": index}, "request-1")

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        ids = list(pool.map(worker, range(worker_count)))

    assert len(set(ids)) == 1
    with sqlite3.connect(queue.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM queue_items WHERE idempotency_key = ?",
            ("request-1",),
        ).fetchone()[0]
    assert count == 1


def test_dequeue_claims_oldest_queued_item_fifo(tmp_path: Path) -> None:
    clock = TickClock()
    queue = GenerationQueue(tmp_path / "queue.sqlite", clock=clock)
    first_id = queue.enqueue({"prompt": "first"}, "request-1")
    second_id = queue.enqueue({"prompt": "second"}, "request-2")

    first_claim = queue.dequeue()
    assert first_claim is not None
    assert first_claim.id == first_id
    assert first_claim.idempotency_key == "request-1"
    assert first_claim.payload == {"prompt": "first"}
    assert first_claim.status == "running"
    assert first_claim.attempts == 1

    first_row = _queue_row(queue, first_id)
    second_row = _queue_row(queue, second_id)
    assert first_row["status"] == "running"
    assert first_row["attempts"] == 1
    assert first_row["updated_at"] > first_row["created_at"]
    assert second_row["status"] == "queued"
    assert second_row["attempts"] == 0

    second_claim = queue.dequeue()
    assert second_claim is not None
    assert second_claim.id == second_id
    assert second_claim.payload == {"prompt": "second"}
    assert second_claim.attempts == 1


def test_mark_done_completes_running_item_and_refreshes_updated_at(
    tmp_path: Path,
) -> None:
    clock = TickClock()
    queue = GenerationQueue(tmp_path / "queue.sqlite", clock=clock)
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")
    claimed = queue.dequeue()
    assert claimed is not None
    running_updated_at = _queue_row(queue, row_id)["updated_at"]

    assert queue.mark_done(row_id) is True

    row = _queue_row(queue, row_id)
    assert row["status"] == "done"
    assert row["source"] == "generated"
    assert row["attempts"] == 1
    assert row["updated_at"] > running_updated_at
    assert queue.dequeue() is None


def test_mark_failed_requeues_for_retry_until_max_attempts(tmp_path: Path) -> None:
    clock = TickClock()
    queue = GenerationQueue(tmp_path / "queue.sqlite", max_attempts=2, clock=clock)
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")
    first_claim = queue.dequeue()
    assert first_claim is not None
    first_running_updated_at = _queue_row(queue, row_id)["updated_at"]

    assert queue.mark_failed(row_id) is True

    retry_row = _queue_row(queue, row_id)
    assert retry_row["status"] == "queued"
    assert retry_row["attempts"] == 1
    assert retry_row["updated_at"] > first_running_updated_at

    second_claim = queue.dequeue()
    assert second_claim is not None
    assert second_claim.id == row_id
    assert second_claim.attempts == 2

    assert queue.mark_failed(row_id) is True

    failed_row = _queue_row(queue, row_id)
    assert failed_row["status"] == "failed"
    assert failed_row["attempts"] == 2
    assert queue.dequeue() is None


def test_mark_failed_terminal_skips_retry_and_records_error(tmp_path: Path) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite", max_attempts=3)
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")
    claim = queue.dequeue()
    assert claim is not None
    assert claim.attempts == 1

    assert (
        queue.mark_failed(row_id, error="validation_rejected", terminal=True) is True
    )

    row = _queue_row(queue, row_id)
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert row["last_error"] == "validation_rejected"
    assert queue.dequeue() is None


def test_mark_failed_records_last_error_on_each_transient_attempt(
    tmp_path: Path,
) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite", max_attempts=3)
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    queue.dequeue()
    assert queue.mark_failed(row_id, error="boom-1") is True
    requeued = _queue_row(queue, row_id)
    assert requeued["status"] == "queued"
    assert requeued["last_error"] == "boom-1"

    queue.dequeue()
    assert queue.mark_failed(row_id, error="boom-2") is True
    requeued = _queue_row(queue, row_id)
    assert requeued["status"] == "queued"
    assert requeued["last_error"] == "boom-2"

    queue.dequeue()
    assert queue.mark_failed(row_id, error="boom-3") is True
    failed = _queue_row(queue, row_id)
    assert failed["status"] == "failed"
    assert failed["attempts"] == 3
    assert failed["last_error"] == "boom-3"


def test_run_worker_validation_reject_is_terminal_no_retry(tmp_path: Path) -> None:
    client = FakeClient()
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        validator=lambda result, payload: False,
        max_attempts=3,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(
            queue, lambda: _queue_row(queue, row_id)["status"] == "failed"
        )
    )

    row = _queue_row(queue, row_id)
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert row["last_error"] == "validation_rejected"


def test_run_worker_generation_error_retries_until_max_attempts(
    tmp_path: Path,
) -> None:
    client = RaisingClient()
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        max_attempts=3,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(
            queue, lambda: _queue_row(queue, row_id)["status"] == "failed"
        )
    )

    row = _queue_row(queue, row_id)
    assert row["status"] == "failed"
    assert row["attempts"] == 3
    assert client.calls == 3
    assert row["last_error"] == "generation failed"


def test_dequeue_concurrent_workers_do_not_double_claim(tmp_path: Path) -> None:
    queue = GenerationQueue(tmp_path / "queue.sqlite")
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")
    worker_count = 2
    barrier = Barrier(worker_count)

    def worker(_: int):
        barrier.wait()
        return queue.dequeue()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        claims = list(pool.map(worker, range(worker_count)))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].id == row_id
    assert sum(item is None for item in claims) == 1

    row = _queue_row(queue, row_id)
    assert row["status"] == "running"
    assert row["attempts"] == 1


async def _run_worker_until(
    queue: GenerationQueue,
    done,
    *,
    idle_sleep: float = 0.001,
    timeout: float = 1.0,
) -> None:
    worker = asyncio.create_task(queue.run_worker(idle_sleep=idle_sleep))
    try:
        await asyncio.wait_for(_wait_until(done), timeout)
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


async def _wait_until(done) -> None:
    while not done():
        await asyncio.sleep(0.001)


class FakeBudget:
    def __init__(self, decisions: list[bool] | None = None) -> None:
        self.decisions = decisions or [True]
        self.allow_calls: list[dict] = []
        self.pay_calls: list[tuple[dict, dict]] = []

    def allow(self, payload: dict) -> bool:
        self.allow_calls.append(payload)
        if len(self.allow_calls) <= len(self.decisions):
            return self.decisions[len(self.allow_calls) - 1]
        return self.decisions[-1]

    def pay(self, payload: dict, result: dict) -> None:
        self.pay_calls.append((payload, result))


class FakeCache:
    def __init__(self, hit=None) -> None:
        self.hit = hit
        self.get_calls: list[dict] = []
        self.set_calls: list[tuple[dict, dict]] = []

    def get(self, payload: dict):
        self.get_calls.append(payload)
        return self.hit

    def set(self, payload: dict, result: dict) -> None:
        self.set_calls.append((payload, result))


class RecordingStorage:
    def __init__(self) -> None:
        self.save_calls: list[tuple[dict, dict]] = []

    def save(self, result: dict, payload: dict) -> None:
        self.save_calls.append((result, payload))


class RaisingClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, payload: dict):
        self.calls += 1
        raise RuntimeError("generation failed")


def test_run_worker_cache_hit_marks_done_without_budget_or_generation(
    tmp_path: Path,
) -> None:
    class ShouldNotGenerate:
        calls = 0

        def generate(self, payload: dict):
            self.calls += 1
            raise AssertionError("cache hit should not generate")

    client = ShouldNotGenerate()
    cache = FakeCache(hit={"audio_path": "/tmp/cached.wav"})
    budget = FakeBudget(decisions=[True])
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        cache=cache,
        budget=budget,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(queue, lambda: _queue_row(queue, row_id)["status"] == "done")
    )

    row = _queue_row(queue, row_id)
    assert row["source"] == "cache"
    assert client.calls == 0
    assert budget.allow_calls == []
    assert budget.pay_calls == []


def test_run_worker_budget_deny_marks_blocked_without_paying(
    tmp_path: Path,
) -> None:
    class ShouldNotGenerate:
        calls = 0

        def generate(self, payload: dict):
            self.calls += 1
            raise AssertionError("budget block should not generate")

    client = ShouldNotGenerate()
    budget = FakeBudget(decisions=[False])
    queue = GenerationQueue(tmp_path / "queue.sqlite", client=client, budget=budget)
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(
            queue,
            lambda: _queue_row(queue, row_id)["status"] == "blocked",
            idle_sleep=60.0,
        )
    )

    assert client.calls == 0
    assert len(budget.allow_calls) == 1
    assert budget.pay_calls == []


def test_run_worker_retries_blocked_item_after_budget_allows(
    tmp_path: Path,
) -> None:
    budget = FakeBudget(decisions=[False, True])
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=FakeClient(),
        budget=budget,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(queue, lambda: _queue_row(queue, row_id)["status"] == "done")
    )

    row = _queue_row(queue, row_id)
    assert row["source"] == "generated"
    assert len(budget.allow_calls) == 2
    assert len(budget.pay_calls) == 1


def test_run_worker_generation_success_uses_thread_and_stores_result(
    tmp_path: Path,
) -> None:
    main_thread = threading.get_ident()

    class ThreadRecordingClient:
        def __init__(self) -> None:
            self.thread_id: int | None = None

        def generate(self, payload: dict):
            self.thread_id = threading.get_ident()
            return {"audio_path": "/tmp/fake.wav", "cost_usd": 0.01}

    client = ThreadRecordingClient()
    storage = RecordingStorage()
    cache = FakeCache()
    budget = FakeBudget(decisions=[True])
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        cache=cache,
        budget=budget,
        storage=storage,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(queue, lambda: _queue_row(queue, row_id)["status"] == "done")
    )

    row = _queue_row(queue, row_id)
    assert row["source"] == "generated"
    assert client.thread_id is not None
    assert client.thread_id != main_thread
    assert len(storage.save_calls) == 1
    assert len(cache.set_calls) == 1
    assert len(budget.pay_calls) == 1


def test_run_worker_generation_failure_marks_failed_at_max_attempts(
    tmp_path: Path,
) -> None:
    client = RaisingClient()
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        max_attempts=1,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(queue, lambda: _queue_row(queue, row_id)["status"] == "failed")
    )

    assert client.calls == 1


def test_run_worker_validation_reject_marks_failed_without_store_or_pay(
    tmp_path: Path,
) -> None:
    storage = RecordingStorage()
    budget = FakeBudget(decisions=[True])
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=FakeClient(),
        budget=budget,
        storage=storage,
        validator=lambda result, payload: False,
        max_attempts=1,
    )
    row_id = queue.enqueue({"prompt": "bells"}, "request-1")

    asyncio.run(
        _run_worker_until(queue, lambda: _queue_row(queue, row_id)["status"] == "failed")
    )

    assert storage.save_calls == []
    assert budget.pay_calls == []


def test_run_worker_respects_max_concurrent(
    tmp_path: Path,
) -> None:
    class BlockingClient:
        def __init__(self) -> None:
            self.active = 0
            self.max_seen = 0
            self.lock = threading.Lock()
            self.release = threading.Event()

        def generate(self, payload: dict):
            with self.lock:
                self.active += 1
                self.max_seen = max(self.max_seen, self.active)
            self.release.wait(timeout=1.0)
            with self.lock:
                self.active -= 1
            return {"audio_path": f"/tmp/{payload['prompt']}.wav", "cost_usd": 0.01}

    client = BlockingClient()
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=client,
        max_concurrent=2,
    )
    row_ids = [
        queue.enqueue({"prompt": f"sound-{index}"}, f"request-{index}")
        for index in range(3)
    ]

    async def scenario() -> None:
        worker = asyncio.create_task(queue.run_worker(idle_sleep=0.001))
        try:
            await asyncio.wait_for(_wait_until(lambda: client.max_seen == 2), 1.0)
            assert client.active == 2
            client.release.set()
            await asyncio.wait_for(
                _wait_until(
                    lambda: all(
                        _queue_row(queue, row_id)["status"] == "done"
                        for row_id in row_ids
                    )
                ),
                1.0,
            )
        finally:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())

    assert client.max_seen == 2


class FakeClient:
    def generate(self, request):
        return {"audio_path": "/tmp/fake.wav", "cost_usd": 0.01}

class FakeStorage:
    def save(self, result, req):
        return None

def test_integration_worker_loop_success(tmp_path: Path) -> None:
    db_path = tmp_path / "queue.sqlite"
    client = FakeClient()
    storage = FakeStorage()
    queue = GenerationQueue(db_path, client=client, storage=storage)
    
    # Enqueue a job
    job_id = queue.enqueue({"prompt": "bells", "hash": "abc"}, "req-1")
    
    # Run the worker loop once
    processed = queue.process_one()
    
    assert processed is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT status FROM queue_items WHERE id = ?", (job_id,)).fetchone()
        assert row[0] == "done"
