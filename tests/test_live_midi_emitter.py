"""Tests for the T-053a live MIDI emitter daemon scaffold."""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from cypherclaw import live_midi_emitter as mod


def _event(**overrides: object) -> mod.LiveMidiEvent:
    values: dict[str, object] = {
        "event_type": "note_on",
        "status": 0x90,
        "data1": 60,
        "data2": 100,
        "ts": 1779568086.25,
        "voice": "pluck",
        "scene": "Theme",
        "tuning": "just_intonation_5_limit",
        "metadata": {"render_space_id": "small_wooden_room"},
    }
    values.update(overrides)
    return mod.LiveMidiEvent(**values)


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.value = now

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _FakeResponse:
    def __init__(self, body: dict[str, object], status: int = 202) -> None:
        self._body = json.dumps(body).encode()
        self.status = status
        self.code = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(code: int) -> HTTPError:
    return HTTPError(
        "https://worker.example/api/cypherclaw/midi-event",
        code,
        "error",
        {},
        io.BytesIO(b'{"ok":false}'),
    )


def test_config_loads_defaults_and_env_overrides() -> None:
    defaults = mod.load_config(environ={})

    assert defaults.endpoint_url == mod.DEFAULT_ENDPOINT_URL
    assert defaults.admin_token == ""
    assert defaults.batch_size == mod.DEFAULT_BATCH_SIZE
    assert defaults.flush_interval_seconds == mod.DEFAULT_FLUSH_INTERVAL_SECONDS
    assert defaults.timeout_seconds == mod.DEFAULT_TIMEOUT_SECONDS
    assert defaults.max_retries == mod.DEFAULT_MAX_RETRIES
    assert defaults.backoff_base_seconds == mod.DEFAULT_BACKOFF_BASE_SECONDS
    assert defaults.source == mod.DEFAULT_SOURCE

    config = mod.load_config(
        environ={
            "CYPHERCLAW_LIVE_MIDI_ENDPOINT": "https://worker.example/midi-event",
            "CYPHERCLAW_LIVE_MIDI_TOKEN": "secret-token",
            "CYPHERCLAW_LIVE_MIDI_BATCH_SIZE": "4",
            "CYPHERCLAW_LIVE_MIDI_FLUSH_SECONDS": "0.125",
            "CYPHERCLAW_LIVE_MIDI_TIMEOUT_SECONDS": "2.5",
            "CYPHERCLAW_LIVE_MIDI_MAX_RETRIES": "5",
            "CYPHERCLAW_LIVE_MIDI_BACKOFF_SECONDS": "0.05",
            "CYPHERCLAW_LIVE_MIDI_SOURCE": "pytest-emitter",
        }
    )

    assert config.endpoint_url == "https://worker.example/midi-event"
    assert config.admin_token == "secret-token"
    assert config.batch_size == 4
    assert config.flush_interval_seconds == 0.125
    assert config.timeout_seconds == 2.5
    assert config.max_retries == 5
    assert config.backoff_base_seconds == 0.05
    assert config.source == "pytest-emitter"


def test_live_midi_event_validates_bytes_and_serializes_metadata() -> None:
    event = _event()

    assert event.to_dict() == {
        "event_type": "note_on",
        "status": 144,
        "data1": 60,
        "data2": 100,
        "ts": 1779568086.25,
        "voice": "pluck",
        "scene": "Theme",
        "tuning": "just_intonation_5_limit",
        "metadata": {"render_space_id": "small_wooden_room"},
    }

    with pytest.raises(ValueError, match="status"):
        _event(status=-1)
    with pytest.raises(ValueError, match="data1"):
        _event(data1=256)
    with pytest.raises(ValueError, match="data2"):
        _event(data2=12.5)
    with pytest.raises(ValueError, match="ts"):
        _event(ts=float("inf"))


def test_live_midi_event_schema_rejects_invalid_event_shapes() -> None:
    base: dict[str, object] = {
        "event_type": "note_on",
        "status": 0x90,
        "data1": 60,
        "data2": 100,
        "ts": 1779568086.25,
        "voice": "pluck",
        "scene": "Theme",
        "tuning": "just_intonation_5_limit",
    }

    invalid_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({**base, "event_type": "aftertouch"}, "event_type"),
        ({**base, "status": 0x80}, "status"),
        ({**base, "data1": 128}, "data1"),
        ({**base, "data2": 0}, "velocity"),
        ({**base, "ts": float("nan")}, "ts"),
        ({**base, "voice": 42}, "voice"),
        ({**base, "metadata": {"bad": object()}}, "metadata"),
        (
            {
                **base,
                "event_type": "control_change",
                "status": 0x90,
                "data1": 1,
                "data2": 64,
            },
            "status",
        ),
        (
            {
                **base,
                "event_type": "pitch_bend",
                "status": 0xB0,
                "data1": 0,
                "data2": 64,
            },
            "status",
        ),
    )

    for payload, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            mod.LiveMidiEvent(**payload)

    with pytest.raises(ValueError, match="channel"):
        mod.build_note_on_event(note=60, velocity=100, channel=16, ts=1.0)
    with pytest.raises(ValueError, match="bend"):
        mod.build_pitch_bend_event(value=16384, channel=0, ts=1.0)


def test_event_helper_constructors_emit_supported_schema_shapes() -> None:
    metadata = {"render_space_id": "damp_cave_wall", "fx_bus_id": 21}
    events = (
        mod.build_note_on_event(
            note=64,
            velocity=96,
            channel=2,
            ts=10.5,
            voice="bowed",
            scene="Verse",
            tuning="gamelan_slendro",
            metadata=metadata,
        ),
        mod.build_note_off_event(
            note=64,
            release_velocity=12,
            channel=2,
            ts=11.0,
            voice="bowed",
            scene="Verse",
            tuning="gamelan_slendro",
        ),
        mod.build_control_change_event(
            controller=74,
            value=48,
            channel=2,
            ts=11.25,
            voice="bowed",
            scene="Verse",
            tuning="gamelan_slendro",
        ),
        mod.build_pitch_bend_event(
            value=8192,
            channel=2,
            ts=11.5,
            voice="bowed",
            scene="Verse",
            tuning="gamelan_slendro",
        ),
    )

    assert [event.channel for event in events] == [2, 2, 2, 2]
    assert events[-1].pitch_bend_value == 8192
    assert [event.to_dict() for event in events] == [
        {
            "event_type": "note_on",
            "status": 0x92,
            "data1": 64,
            "data2": 96,
            "ts": 10.5,
            "voice": "bowed",
            "scene": "Verse",
            "tuning": "gamelan_slendro",
            "metadata": metadata,
        },
        {
            "event_type": "note_off",
            "status": 0x82,
            "data1": 64,
            "data2": 12,
            "ts": 11.0,
            "voice": "bowed",
            "scene": "Verse",
            "tuning": "gamelan_slendro",
            "metadata": {},
        },
        {
            "event_type": "control_change",
            "status": 0xB2,
            "data1": 74,
            "data2": 48,
            "ts": 11.25,
            "voice": "bowed",
            "scene": "Verse",
            "tuning": "gamelan_slendro",
            "metadata": {},
        },
        {
            "event_type": "pitch_bend",
            "status": 0xE2,
            "data1": 0,
            "data2": 64,
            "ts": 11.5,
            "voice": "bowed",
            "scene": "Verse",
            "tuning": "gamelan_slendro",
            "metadata": {},
        },
    ]


def test_validate_live_midi_event_payload_round_trips_context() -> None:
    event = mod.build_control_change_event(
        controller=1,
        value=90,
        channel=5,
        ts=20.0,
        voice="breath",
        scene="Bridge",
        tuning="twelve_tet",
        metadata={"space": {"fx_bus_id": 17}, "enabled": True},
    )

    payload = event.to_dict()
    reloaded = mod.validate_live_midi_event_payload(payload)
    serialized = mod.serialize_midi_event(reloaded)

    assert reloaded == event
    assert serialized == payload
    assert json.loads(json.dumps(serialized, sort_keys=True)) == payload

    for malformed in (
        {},
        {**payload, "event_type": "cc"},
        {**payload, "metadata": []},
        {**payload, "tuning": None},
    ):
        with pytest.raises(ValueError):
            mod.validate_live_midi_event_payload(malformed)


def test_build_batch_payload_includes_schema_version_and_mixed_event_shapes() -> None:
    config = mod.LiveMidiEmitterConfig(
        endpoint_url="https://worker.example/api/cypherclaw/midi-event",
        source="pytest-schema",
    )
    events = (
        mod.build_note_on_event(
            note=60,
            velocity=100,
            channel=0,
            ts=1.0,
            voice="pluck",
            scene="Intro",
            tuning="just_intonation_5_limit",
        ),
        mod.build_note_off_event(
            note=60,
            channel=0,
            ts=1.5,
            voice="pluck",
            scene="Intro",
            tuning="just_intonation_5_limit",
        ),
        mod.build_control_change_event(
            controller=64,
            value=127,
            channel=1,
            ts=2.0,
            voice="pad",
            scene="Intro",
            tuning="twelve_tet",
        ),
        mod.build_pitch_bend_event(
            value=16383,
            channel=1,
            ts=2.25,
            voice="pad",
            scene="Intro",
            tuning="twelve_tet",
        ),
    )

    payload = mod.build_batch_payload(events, config, batch_id="schema-batch")

    assert payload == {
        "schema_version": mod.MIDI_EVENT_SCHEMA_VERSION,
        "source": "pytest-schema",
        "batch_id": "schema-batch",
        "event_count": 4,
        "events": [
            {
                "event_type": "note_on",
                "status": 0x90,
                "data1": 60,
                "data2": 100,
                "ts": 1.0,
                "voice": "pluck",
                "scene": "Intro",
                "tuning": "just_intonation_5_limit",
                "metadata": {},
            },
            {
                "event_type": "note_off",
                "status": 0x80,
                "data1": 60,
                "data2": 0,
                "ts": 1.5,
                "voice": "pluck",
                "scene": "Intro",
                "tuning": "just_intonation_5_limit",
                "metadata": {},
            },
            {
                "event_type": "control_change",
                "status": 0xB1,
                "data1": 64,
                "data2": 127,
                "ts": 2.0,
                "voice": "pad",
                "scene": "Intro",
                "tuning": "twelve_tet",
                "metadata": {},
            },
            {
                "event_type": "pitch_bend",
                "status": 0xE1,
                "data1": 127,
                "data2": 127,
                "ts": 2.25,
                "voice": "pad",
                "scene": "Intro",
                "tuning": "twelve_tet",
                "metadata": {},
            },
        ],
    }
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_batching_queue_flushes_by_size_and_time() -> None:
    clock = _Clock(now=100.0)
    queue = mod.BatchingMidiQueue(
        max_size=3,
        flush_interval_seconds=0.5,
        clock=clock.now,
    )

    first = _event(data1=60)
    second = _event(data1=62)
    third = _event(data1=64)
    fourth = _event(data1=65)

    assert queue.add(first) == ()
    clock.advance(0.1)
    assert queue.add(second) == ()
    clock.advance(0.1)
    assert queue.add(third) == (first, second, third)
    assert queue.pending_count == 0

    assert queue.add(fourth) == ()
    assert queue.flush_due() == ()
    clock.advance(0.49)
    assert queue.flush_due() == ()
    clock.advance(0.01)
    assert queue.flush_due() == (fourth,)
    assert queue.pending_count == 0


def test_http_client_posts_json_payload_with_auth_header() -> None:
    config = mod.LiveMidiEmitterConfig(
        endpoint_url="https://worker.example/api/cypherclaw/midi-event",
        admin_token="secret-token",
        source="pytest-emitter",
    )
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, *, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return _FakeResponse({"ok": True, "accepted": 1})

    result = mod.post_midi_batch(
        [_event()],
        config,
        batch_id="batch-1",
        urlopen_fn=fake_urlopen,
    )

    assert captured["url"] == config.endpoint_url
    assert captured["method"] == "POST"
    assert captured["headers"]["authorization"] == "Bearer secret-token"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["timeout"] == mod.DEFAULT_TIMEOUT_SECONDS
    assert captured["body"]["source"] == "pytest-emitter"
    assert captured["body"]["batch_id"] == "batch-1"
    assert captured["body"]["event_count"] == 1
    assert captured["body"]["events"][0]["status"] == 144
    assert captured["body"]["events"][0]["voice"] == "pluck"
    assert result.ok is True
    assert result.status_code == 202
    assert result.attempts == 1
    assert result.event_count == 1


def test_http_client_retries_transient_failures_with_backoff() -> None:
    config = mod.LiveMidiEmitterConfig(
        endpoint_url="https://worker.example/api/cypherclaw/midi-event",
        max_retries=2,
        backoff_base_seconds=0.2,
    )
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request: Any, *, timeout: float) -> _FakeResponse:
        del timeout
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary network failure")
        if calls == 2:
            raise _http_error(503)
        return _FakeResponse({"ok": True})

    result = mod.post_midi_batch(
        [_event()],
        config,
        batch_id="batch-retry",
        urlopen_fn=fake_urlopen,
        sleep_fn=sleeps.append,
    )

    assert result.ok is True
    assert result.attempts == 3
    assert calls == 3
    assert sleeps == [0.2, 0.4]


def test_http_client_does_not_retry_non_transient_client_errors() -> None:
    config = mod.LiveMidiEmitterConfig(
        endpoint_url="https://worker.example/api/cypherclaw/midi-event",
        max_retries=5,
        backoff_base_seconds=0.2,
    )
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(_request: Any, *, timeout: float) -> _FakeResponse:
        del timeout
        nonlocal calls
        calls += 1
        raise _http_error(400)

    with pytest.raises(mod.MidiPostError) as excinfo:
        mod.post_midi_batch(
            [_event()],
            config,
            batch_id="batch-bad",
            urlopen_fn=fake_urlopen,
            sleep_fn=sleeps.append,
        )

    assert calls == 1
    assert sleeps == []
    assert excinfo.value.status_code == 400
    assert excinfo.value.attempts == 1


def test_run_daemon_flushes_pending_events_on_shutdown() -> None:
    config = mod.LiveMidiEmitterConfig(endpoint_url="https://worker.example/midi")
    queue = mod.BatchingMidiQueue(max_size=10, flush_interval_seconds=60.0)
    queued_event = _event(data1=72)
    queue.add(queued_event)
    stop_event = threading.Event()
    stop_event.set()
    posted: list[tuple[mod.LiveMidiEvent, ...]] = []

    def fake_post(batch: Sequence[mod.LiveMidiEvent]) -> mod.MidiPostResult:
        posted.append(tuple(batch))
        return mod.MidiPostResult(
            ok=True,
            status_code=202,
            attempts=1,
            event_count=len(batch),
            response_body="{}",
        )

    result = mod.run_daemon(
        config,
        stop_event=stop_event,
        queue=queue,
        post_batch=fake_post,
        poll_interval=0.0,
    )

    assert result == 0
    assert posted == [(queued_event,)]
    assert queue.pending_count == 0


def test_main_builds_config_installs_signal_handlers_and_runs_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed: list[threading.Event] = []
    captured: dict[str, object] = {}

    def fake_install(stop_event: threading.Event) -> None:
        installed.append(stop_event)

    def fake_run(
        config: mod.LiveMidiEmitterConfig,
        stop_event: threading.Event,
    ) -> int:
        captured["config"] = config
        captured["stop_event"] = stop_event
        return 0

    monkeypatch.setattr(mod, "install_signal_handlers", fake_install)
    monkeypatch.setattr(mod, "run_daemon", fake_run)
    monkeypatch.setattr(mod, "configure_logging", lambda *_args, **_kwargs: None)

    result = mod.main(
        [
            "--endpoint-url",
            "https://worker.example/api/cypherclaw/midi-event",
            "--batch-size",
            "8",
            "--flush-interval",
            "0.2",
            "--max-retries",
            "1",
            "--source",
            "cli-test",
        ]
    )

    assert result == 0
    assert installed == [captured["stop_event"]]
    config = captured["config"]
    assert isinstance(config, mod.LiveMidiEmitterConfig)
    assert config.endpoint_url == "https://worker.example/api/cypherclaw/midi-event"
    assert config.batch_size == 8
    assert config.flush_interval_seconds == 0.2
    assert config.max_retries == 1
    assert config.source == "cli-test"
