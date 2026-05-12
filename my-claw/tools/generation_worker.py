"""Standalone async entry point for the CypherClaw generation queue worker.

Constructs ``ReplicateClient``, ``GenerationCache``, ``GenerationBudget``,
``SampleLibrary``, ``GenerationStorage``, and ``GenerationQueue`` from
environment-configured paths, then runs ``queue.run_worker()`` under
``asyncio.run`` until SIGTERM/SIGINT, at which point it lets the current item
finish and exits clean. Wired up by ``cypherclaw-generation-worker.service``
(CCG-022/CCG-023).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from senseweave.generation.budget import GenerationBudget  # noqa: E402
from senseweave.generation.cache import GenerationCache  # noqa: E402
from senseweave.generation.client_replicate import ReplicateClient  # noqa: E402
from senseweave.generation.queue import GenerationQueue  # noqa: E402
from senseweave.generation.storage import GenerationStorage  # noqa: E402
from senseweave.sample_library import SampleLibrary, init_sample_storage  # noqa: E402


LOGGER = logging.getLogger("cypherclaw.generation_worker")

DEFAULT_DATA_DIR = Path("/home/user/cypherclaw-data")
ENV_DATA_DIR = "CYPHERCLAW_DATA_DIR"
ENV_QUEUE_DB = "CYPHERCLAW_GENERATION_QUEUE_DB"
ENV_CACHE_ROOT = "CYPHERCLAW_GENERATION_CACHE_ROOT"
ENV_SAMPLES_ROOT = "CYPHERCLAW_SAMPLES_ROOT"
ENV_BUDGET_STATE = "CYPHERCLAW_GENERATION_BUDGET_STATE"
ENV_REPLICATE_TOKEN = "REPLICATE_API_TOKEN"
ENV_STATUS_PATH = "CYPHERCLAW_GENERATION_STATUS_PATH"
DEFAULT_STATUS_PATH = Path("/tmp/generation_status.json")
STATUS_INTERVAL_SEC = 30.0
_SIGNAL_HANDLER_UNSUPPORTED = NotImplementedError


@dataclass(frozen=True)
class WorkerConfig:
    """Resolved generation worker runtime configuration."""

    data_dir: Path
    queue_db: Path
    cache_root: Path
    samples_root: Path
    budget_state: Path
    status_path: Path
    status_interval_sec: float = STATUS_INTERVAL_SEC
    replicate_api_token: str | None = None


def _data_dir() -> Path:
    raw = os.environ.get(ENV_DATA_DIR)
    return Path(raw) if raw else DEFAULT_DATA_DIR


def _resolve_path(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    return Path(raw) if raw else default


def load_worker_config(env: Mapping[str, str] | None = None) -> WorkerConfig:
    """Resolve worker settings from an environment mapping."""
    source = os.environ if env is None else env
    raw_data_dir = source.get(ENV_DATA_DIR)
    data_dir = Path(raw_data_dir) if raw_data_dir else DEFAULT_DATA_DIR

    def env_path(name: str, default: Path) -> Path:
        raw = source.get(name)
        return Path(raw) if raw else default

    token = source.get(ENV_REPLICATE_TOKEN) or None
    return WorkerConfig(
        data_dir=data_dir,
        queue_db=env_path(ENV_QUEUE_DB, data_dir / "generation_queue.db"),
        cache_root=env_path(ENV_CACHE_ROOT, data_dir / "cache"),
        samples_root=env_path(ENV_SAMPLES_ROOT, data_dir / "samples"),
        budget_state=env_path(
            ENV_BUDGET_STATE,
            data_dir / "state" / "generation_budget.json",
        ),
        status_path=env_path(ENV_STATUS_PATH, DEFAULT_STATUS_PATH),
        status_interval_sec=STATUS_INTERVAL_SEC,
        replicate_api_token=token,
    )


def worker_runtime_summary(config: WorkerConfig) -> dict[str, Any]:
    """Return an operator-safe summary of the resolved worker config."""
    return {
        "data_dir": str(config.data_dir),
        "queue_db": str(config.queue_db),
        "cache_root": str(config.cache_root),
        "samples_root": str(config.samples_root),
        "budget_state": str(config.budget_state),
        "status_path": str(config.status_path),
        "status_interval_sec": float(config.status_interval_sec),
        "replicate_token_configured": config.replicate_api_token is not None,
    }


def build_queue(config: WorkerConfig | None = None) -> GenerationQueue:
    """Construct the queue and all its dependencies from the environment."""
    resolved = load_worker_config() if config is None else config

    init_sample_storage(resolved.samples_root)
    library = SampleLibrary(resolved.samples_root)

    client = ReplicateClient(api_token=resolved.replicate_api_token)
    cache = GenerationCache(resolved.cache_root)
    budget = GenerationBudget(resolved.budget_state)
    storage = GenerationStorage(library, resolved.samples_root)

    LOGGER.info(
        "generation worker configured (db=%s cache=%s samples=%s budget_state=%s)",
        resolved.queue_db,
        resolved.cache_root,
        resolved.samples_root,
        resolved.budget_state,
    )

    return GenerationQueue(
        resolved.queue_db,
        client=client,
        cache=cache,
        budget=budget,
        storage=storage,
    )


def _status_path() -> Path:
    return load_worker_config().status_path


def write_generation_status(
    queue: GenerationQueue,
    path: Path = DEFAULT_STATUS_PATH,
    *,
    worker_pid: int | None = None,
) -> dict[str, Any]:
    """Write the worker diagnostic JSON file atomically."""
    pid = os.getpid() if worker_pid is None else worker_pid
    payload = queue.diagnostic_snapshot(worker_pid=pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{pid}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    os.replace(tmp_path, path)
    return payload


async def _status_loop(
    queue: GenerationQueue,
    path: Path,
    *,
    interval: float = STATUS_INTERVAL_SEC,
) -> None:
    while True:
        try:
            write_generation_status(queue, path)
        except Exception:
            LOGGER.exception("failed to write generation status")
        await asyncio.sleep(interval)


async def _amain(config: WorkerConfig | None = None) -> None:
    resolved = load_worker_config() if config is None else config
    queue = build_queue(resolved)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop(signame: str) -> None:
        if stop_event.is_set():
            return
        LOGGER.info("received %s; finishing current item then exiting", signame)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop, sig.name)
        except _SIGNAL_HANDLER_UNSUPPORTED:
            signal.signal(sig, lambda *_: _request_stop(sig.name))

    worker_task = asyncio.create_task(queue.run_worker(), name="generation-worker")
    stop_task = asyncio.create_task(stop_event.wait(), name="generation-worker-stop")
    status_task = asyncio.create_task(
        _status_loop(
            queue,
            resolved.status_path,
            interval=resolved.status_interval_sec,
        ),
        name="generation-worker-status",
    )

    LOGGER.info("generation worker started (pid=%d)", os.getpid())
    try:
        await asyncio.wait(
            {worker_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        if not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        if not stop_task.done():
            stop_task.cancel()
        if not status_task.done():
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass
        LOGGER.info("generation worker stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
