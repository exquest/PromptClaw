"""Live CypherClaw generation-to-audibility smoke test.

This test is intentionally host-gated. It creates one real generated sample,
registers it in the live sample library, then drives two short sampler pieces
and verifies the generated source appears in the usage journal and self-listen
state.
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


TOOLS_DIR = Path(__file__).resolve().parent.parent / "my-claw" / "tools"

MODE_NAME = "evening_reflection"
ARC_PHASE = "E2E-Generated-Emergence"
MOOD = {"energy": 0.58, "valence": 0.57, "arousal": 0.44}


def _require_live_cypherclaw() -> None:
    if os.environ.get("CI"):
        pytest.skip("cypherclaw e2e skipped on CI")
    host = platform.node().lower()
    forced = os.environ.get("CYPHERCLAW_E2E") == "1"
    if not forced and "cypherclaw" not in host:
        pytest.skip("requires the live cypherclaw host")


class _FixedConditioner:
    def __init__(self, model: str) -> None:
        self.model = model

    def build_request(
        self,
        *,
        mode: object,
        arc_phase: str,
        mood: dict[str, float],
        clap_centroid: object,
        duration_sec: float = 5.0,
    ) -> dict[str, Any]:
        from senseweave.generation.composer_hook import build_generation_request

        return build_generation_request(
            mode=mode,
            arc_phase=arc_phase,
            mood=mood,
            clap_centroid=clap_centroid,
            duration_sec=duration_sec,
            model=self.model,
        )


class _FileGeneratingClient:
    def __init__(self, backend: object, scratch_dir: Path) -> None:
        self.backend = backend
        self.scratch_dir = scratch_dir

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        backend_request = {
            "model": request["model"],
            "prompt": request["prompt"],
            "duration_sec": request["duration_sec"],
            "seed": request["seed"],
        }
        result = dict(self.backend.generate(backend_request))
        audio_path = result.get("audio_path") or result.get("wav_path")
        if audio_path is None:
            audio_bytes = result.get("audio_bytes")
            if not isinstance(audio_bytes, (bytes, bytearray)):
                raise AssertionError("generation result did not expose audio")
            audio_path = self.scratch_dir / f"{request['request_hash']}.wav"
            Path(audio_path).write_bytes(bytes(audio_bytes))
        result["audio_path"] = Path(audio_path)
        result.setdefault("audio_format", "wav")
        return result


class _PlayableRecord:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.buffer_id: int | None = None
        self.gain_db = 0.0


def _build_live_generation_client(scratch_dir: Path) -> _FileGeneratingClient:
    backend_name = os.environ.get("CYPHERCLAW_E2E_GENERATION_BACKEND", "replicate")
    if backend_name == "modal":
        from senseweave.generation.client_modal import ModalClient

        return _FileGeneratingClient(ModalClient(timeout_sec=55.0), scratch_dir)

    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        pytest.skip("REPLICATE_API_TOKEN is required for cypherclaw generation e2e")

    from senseweave.generation.client_replicate import ReplicateClient

    return _FileGeneratingClient(
        ReplicateClient(api_token=token, timeout_sec=55.0),
        scratch_dir,
    )


def _queue_last_error(db_path: Path, row_id: int) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, last_error FROM queue_items WHERE id = ?",
            (row_id,),
        ).fetchone()
    if row is None:
        return "missing queue row"
    return f"status={row[0]} last_error={row[1]}"


def _wait_for_processed_generation(
    *,
    queue: object,
    db_path: Path,
    row_id: int,
    deadline: float,
) -> str:
    while time.monotonic() < deadline:
        process_one = getattr(queue, "process_one")
        process_one()
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT idempotency_key, status, last_error FROM queue_items WHERE id = ?",
                (row_id,),
            ).fetchone()
        if row is None:
            raise AssertionError(f"missing queue row {row_id}")
        if row[1] == "done":
            return str(row[0])
        if row[1] == "failed":
            raise AssertionError(f"generation failed: {row[2]}")
        time.sleep(0.5)
    raise AssertionError(f"generation queue did not finish: {_queue_last_error(db_path, row_id)}")


def _find_generated_record(library: object, sample_id: str) -> object | None:
    matches = [
        record
        for record in library.find(source="generated")  # type: ignore[attr-defined]
        if record.sample_id == sample_id
    ]
    return matches[0] if matches else None


def _wait_for_generated_record(
    *,
    library: object,
    samples_root: Path,
    sample_id: str,
    deadline: float,
) -> object:
    while time.monotonic() < deadline:
        record = _find_generated_record(library, sample_id)
        generated_files = list((samples_root / "generated").glob(f"**/{sample_id}.wav"))
        if record is not None and generated_files:
            return record
        time.sleep(0.5)
    raise AssertionError(f"generated sample {sample_id} did not appear")


def _record_journal_play(
    *,
    journal_path: Path,
    piece_id: str,
    sample_id: str,
    source: str,
    row: int,
) -> None:
    from senseweave.usage_journal import (
        SampleUsageTracker,
        post_piece_hook,
        record_scheduled_sample_event,
    )

    tracker = SampleUsageTracker()
    tracker.start_piece(
        piece_id=piece_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    event = SimpleNamespace(
        role="sample",
        row=row,
        scene_name="GeneratedE2E",
        voice="sw_sampler",
        metadata={
            "sample_id": sample_id,
            "sample_gesture_source": source,
            "sample_gesture_mode": "grain_cloud",
            "sample_gesture_transforms": json.dumps(["generated_sample"]),
        },
        scene_metadata={},
    )
    record_scheduled_sample_event(tracker, event)
    post_piece_hook(
        tracker,
        arc_payoff_score=0.8,
        journal_path=journal_path,
        mode=MODE_NAME,
    )


def _play_generated_sample(path: Path) -> None:
    from pythonosc import udp_client
    from senseweave.sampler_buffers import BufferLoader
    from senseweave.sampler_dispatch import SamplerDispatcher

    osc = udp_client.SimpleUDPClient("127.0.0.1", 57110)
    dispatcher = SamplerDispatcher(
        osc,
        BufferLoader(osc, start_bufnum=9200, capacity=4),
        start_node_id=59200,
    )
    dispatcher.play_sampler(
        _PlayableRecord(path),
        duration_sec=4.0,
        position=0.0,
        position_rate=0.06,
        grain_size_ms=140.0,
        density=10.0,
        pitch_transpose=0.0,
        amp=0.2,
        fx_send=0.15,
    )
    time.sleep(4.5)


def _wait_for_self_listener_peak(started_at: float) -> dict[str, Any]:
    state_path = Path("/tmp/self_listen.json")
    deadline = time.monotonic() + 12.0
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}
            last_state = state
            timestamp = float(state.get("timestamp", 0.0) or 0.0)
            peak = max(
                float(state.get("peak", 0.0) or 0.0),
                float(state.get("rolling_peak", 0.0) or 0.0),
            )
            if timestamp >= started_at and peak > 0.0:
                return state
        time.sleep(0.5)
    raise AssertionError(f"/tmp/self_listen.json did not show peak: {last_state}")


@pytest.mark.cypherclaw_e2e
def test_generation_e2e_cypherclaw_real_sample_audible(tmp_path: Path) -> None:
    _require_live_cypherclaw()
    sys.path.insert(0, str(TOOLS_DIR))

    import duet_composer
    from senseweave.generation.queue import GenerationQueue
    from senseweave.generation.storage import GenerationStorage
    from senseweave.sample_library import SampleLibrary
    from senseweave.sample_selector import SampleSelector

    samples_root = Path(os.environ.get("CYPHERCLAW_SAMPLE_ROOT", "samples"))
    queue_db = tmp_path / "generation_queue_e2e.sqlite"
    journal_path = samples_root / "usage_journal.jsonl"
    model = os.environ.get("CYPHERCLAW_E2E_GENERATION_MODEL", "meta/musicgen")

    library = SampleLibrary(samples_root)
    queue = GenerationQueue(
        queue_db,
        client=_build_live_generation_client(tmp_path),
        storage=GenerationStorage(library, samples_root),
        max_attempts=1,
    )

    duet_composer._generation_queue = queue
    duet_composer._generation_conditioner = _FixedConditioner(model)
    duet_composer._generation_last_enqueued_at = None

    learning = {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 5.0}
    assert duet_composer._should_queue_now(MODE_NAME, MOOD, learning)
    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": ARC_PHASE}),
        learning,
        MOOD,
        MODE_NAME,
        [0.1, 0.2, 0.3],
    )
    assert row_id is not None

    deadline = time.monotonic() + 60.0
    request_hash = _wait_for_processed_generation(
        queue=queue,
        db_path=queue_db,
        row_id=row_id,
        deadline=deadline,
    )

    record = _wait_for_generated_record(
        library=library,
        samples_root=samples_root,
        sample_id=str(request_hash),
        deadline=deadline,
    )
    assert record.source == "generated"
    assert Path(record.path).exists(), _queue_last_error(queue_db, row_id)

    selector = SampleSelector(library, rng_seed=20260427)
    played_piece_ids: list[str] = []
    peak_state: dict[str, Any] | None = None
    for index in range(2):
        selected = selector.select(
            mode=MODE_NAME,
            arc_phase=ARC_PHASE,
            mood=MOOD,
            avoid_recent=0,
        )
        assert selected is not None
        piece_id = f"generation-e2e-{request_hash}-{index}"
        played_piece_ids.append(piece_id)
        _record_journal_play(
            journal_path=journal_path,
            piece_id=piece_id,
            sample_id=selected.sample_id,
            source=selected.source,
            row=index,
        )
        started_at = time.time()
        _play_generated_sample(Path(selected.path))
        peak_state = _wait_for_self_listener_peak(started_at)

    from senseweave.usage_journal import read_journal

    entries = [
        entry
        for entry in read_journal(journal_path)
        if entry.piece_id in set(played_piece_ids)
    ]
    assert any(
        sample.sample_id == request_hash and sample.source == "generated"
        for entry in entries
        for sample in entry.samples_played
    )
    assert peak_state is not None
    assert float(peak_state.get("peak", 0.0) or peak_state.get("rolling_peak", 0.0)) > 0
