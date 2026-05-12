"""Subprocess + signal regression for tools/generation_worker.py (T-016)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "my-claw" / "tools" / "generation_worker.py"
sys.path.insert(0, str(WORKER.parent))

import generation_worker  # noqa: E402
from senseweave.generation.queue import GenerationQueue  # noqa: E402


class TickClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        current = self.value
        self.value += 1.0
        return current


class FakeClient:
    def generate(self, request):
        return {
            "audio_path": "/tmp/fake.wav",
            "model_used": request["model"],
            "cost_usd": 0.25,
        }


@dataclass
class FakeBudgetState:
    today_spent_usd: float
    month_spent_usd: float


class FakeBudget:
    state = FakeBudgetState(today_spent_usd=1.25, month_spent_usd=12.5)

    def allow(self, request) -> bool:
        return True


class FakeCache:
    def __init__(self) -> None:
        self._entries = {
            "a": SimpleNamespace(size_bytes=10),
            "b": SimpleNamespace(size_bytes=20),
        }


def _worker_config(tmp_path: Path) -> object:
    return generation_worker.WorkerConfig(
        data_dir=tmp_path,
        queue_db=tmp_path / "queue.sqlite",
        cache_root=tmp_path / "cache",
        samples_root=tmp_path / "samples",
        budget_state=tmp_path / "state" / "budget.json",
        status_path=tmp_path / "status.json",
        status_interval_sec=0.1,
        replicate_api_token="test-token",
    )


def _spawn_worker(tmp_path: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["CYPHERCLAW_DATA_DIR"] = str(tmp_path)
    env["CYPHERCLAW_GENERATION_STATUS_PATH"] = str(tmp_path / "generation_status.json")
    env.pop("REPLICATE_API_TOKEN", None)
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, str(WORKER)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )


def _queue_with_diagnostics(tmp_path: Path) -> GenerationQueue:
    queue = GenerationQueue(
        tmp_path / "queue.sqlite",
        client=FakeClient(),
        cache=FakeCache(),
        budget=FakeBudget(),
        clock=TickClock(),
    )
    queue.enqueue(
        {"request_hash": "hash-ok", "model": "musicgen-medium"},
        "hash-ok",
    )
    assert queue.process_one() is True

    failed_id = queue.enqueue(
        {"request_hash": "hash-failed", "model": "musicgen-medium"},
        "hash-failed",
    )
    assert queue.dequeue() is not None
    assert queue.mark_failed(failed_id, error="backend unavailable", terminal=True)

    queue.enqueue(
        {"request_hash": "hash-pending", "model": "stable-audio-open"},
        "hash-pending",
    )
    return queue


def test_load_worker_config_resolves_environment_paths(tmp_path: Path) -> None:
    env = {
        generation_worker.ENV_DATA_DIR: str(tmp_path),
        generation_worker.ENV_QUEUE_DB: str(tmp_path / "explicit-queue.sqlite"),
        generation_worker.ENV_CACHE_ROOT: str(tmp_path / "explicit-cache"),
        generation_worker.ENV_SAMPLES_ROOT: str(tmp_path / "explicit-samples"),
        generation_worker.ENV_BUDGET_STATE: str(tmp_path / "state" / "budget.json"),
        generation_worker.ENV_STATUS_PATH: str(tmp_path / "status.json"),
        generation_worker.ENV_REPLICATE_TOKEN: "secret-token",
    }

    config = generation_worker.load_worker_config(env)

    assert config.data_dir == tmp_path
    assert config.queue_db == tmp_path / "explicit-queue.sqlite"
    assert config.cache_root == tmp_path / "explicit-cache"
    assert config.samples_root == tmp_path / "explicit-samples"
    assert config.budget_state == tmp_path / "state" / "budget.json"
    assert config.status_path == tmp_path / "status.json"
    assert config.replicate_api_token == "secret-token"


def test_worker_runtime_summary_redacts_secret_token(tmp_path: Path) -> None:
    config = _worker_config(tmp_path)

    summary = generation_worker.worker_runtime_summary(config)
    encoded = json.dumps(summary, sort_keys=True)

    assert summary["data_dir"] == str(tmp_path)
    assert summary["queue_db"] == str(tmp_path / "queue.sqlite")
    assert summary["cache_root"] == str(tmp_path / "cache")
    assert summary["samples_root"] == str(tmp_path / "samples")
    assert summary["budget_state"] == str(tmp_path / "state" / "budget.json")
    assert summary["status_path"] == str(tmp_path / "status.json")
    assert summary["status_interval_sec"] == 0.1
    assert summary["replicate_token_configured"] is True
    assert "test-token" not in encoded


def test_build_queue_uses_explicit_config(tmp_path: Path) -> None:
    config = _worker_config(tmp_path)

    queue = generation_worker.build_queue(config)

    assert queue.db_path == tmp_path / "queue.sqlite"
    assert queue.cache.root == tmp_path / "cache"
    assert queue.budget.path == tmp_path / "state" / "budget.json"
    assert queue.storage.samples_root == tmp_path / "samples"
    assert queue.client._api_token == "test-token"
    assert (tmp_path / "queue.sqlite").exists()
    assert (tmp_path / "cache").is_dir()
    assert (tmp_path / "samples" / "index.sqlite").exists()


def test_write_generation_status_matches_schema(tmp_path: Path) -> None:
    status_path = tmp_path / "generation_status.json"
    queue = _queue_with_diagnostics(tmp_path)

    returned = generation_worker.write_generation_status(
        queue,
        status_path,
        worker_pid=4242,
    )
    payload = json.loads(status_path.read_text())

    assert payload == returned
    assert set(payload) == {
        "queue_depth",
        "cache_size_bytes",
        "cache_entries",
        "today_spent_usd",
        "month_spent_usd",
        "last_error",
        "last_success",
        "worker_pid",
        "last_updated",
    }
    assert payload["queue_depth"] == 1
    assert payload["cache_size_bytes"] == 30
    assert payload["cache_entries"] == 2
    assert payload["today_spent_usd"] == 1.25
    assert payload["month_spent_usd"] == 12.5
    assert payload["last_error"]["message"] == "backend unavailable"
    assert isinstance(payload["last_error"]["ts"], float)
    assert payload["last_success"]["hash"] == "hash-ok"
    assert payload["last_success"]["model"] == "musicgen-medium"
    assert payload["last_success"]["cost"] == 0.25
    assert isinstance(payload["last_success"]["ts"], float)
    assert payload["worker_pid"] == 4242
    assert isinstance(payload["last_updated"], float)


def test_write_generation_status_uses_temp_file_and_os_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_path = tmp_path / "generation_status.json"
    queue = _queue_with_diagnostics(tmp_path)
    calls: list[tuple[Path, Path]] = []
    real_replace = generation_worker.os.replace

    def replace(src, dst) -> None:
        calls.append((Path(src), Path(dst)))
        assert Path(src).exists()
        real_replace(src, dst)

    monkeypatch.setattr(generation_worker.os, "replace", replace)

    generation_worker.write_generation_status(queue, status_path, worker_pid=999)

    assert calls == [
        (tmp_path / ".generation_status.json.999.tmp", status_path),
    ]
    assert status_path.exists()
    assert not calls[0][0].exists()


def _wait_until_started(proc: subprocess.Popen[bytes], timeout: float = 10.0) -> str:
    """Read stdout until the 'started' log line appears or timeout expires."""
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    assert proc.stdout is not None
    os.set_blocking(proc.stdout.fileno(), False)
    try:
        while time.monotonic() < deadline:
            chunk = proc.stdout.read()
            if chunk:
                buffer.extend(chunk)
                if b"generation worker started" in buffer:
                    return buffer.decode("utf-8", errors="replace")
            if proc.poll() is not None:
                tail = proc.stdout.read()
                if tail:
                    buffer.extend(tail)
                pytest.fail(
                    f"worker exited before startup; rc={proc.returncode}\n"
                    f"output:\n{buffer.decode('utf-8', errors='replace')}"
                )
            time.sleep(0.05)
    finally:
        os.set_blocking(proc.stdout.fileno(), True)
    pytest.fail(
        f"worker did not start within {timeout}s; "
        f"output:\n{buffer.decode('utf-8', errors='replace')}"
    )


def test_generation_worker_exits_clean_on_sigterm(tmp_path: Path) -> None:
    proc = _spawn_worker(tmp_path)
    try:
        startup_output = _wait_until_started(proc)
        assert "generation worker started" in startup_output

        proc.send_signal(signal.SIGTERM)
        try:
            stdout_bytes, _ = proc.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("worker did not exit within 10s of SIGTERM")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
    assert proc.returncode == 0, (
        f"worker exited with rc={proc.returncode}; output:\n{startup_output}{stdout}"
    )
    combined = startup_output + stdout
    assert "received SIGTERM" in combined
    assert "generation worker stopped" in combined


def test_generation_worker_exits_clean_on_sigint(tmp_path: Path) -> None:
    proc = _spawn_worker(tmp_path)
    try:
        startup_output = _wait_until_started(proc)
        proc.send_signal(signal.SIGINT)
        try:
            stdout_bytes, _ = proc.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("worker did not exit within 10s of SIGINT")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
    assert proc.returncode == 0
    combined = startup_output + stdout
    assert "received SIGINT" in combined
    assert "generation worker stopped" in combined


def test_generation_worker_creates_queue_db(tmp_path: Path) -> None:
    proc = _spawn_worker(tmp_path)
    try:
        _wait_until_started(proc)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=10.0)

    assert (tmp_path / "generation_queue.db").exists()
    assert (tmp_path / "cache").is_dir()
    assert (tmp_path / "samples").is_dir()
    assert (tmp_path / "samples" / "index.sqlite").exists()


def test_generation_worker_fractal_depth_is_at_least_two() -> None:
    sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
    from sdp.fractal import classify_depth

    result = classify_depth(WORKER)

    assert result.depth >= 2, result.reason
