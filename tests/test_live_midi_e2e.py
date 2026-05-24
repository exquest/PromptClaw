"""End-to-end live MIDI composer/emitter tests for T-053d."""

from __future__ import annotations

import importlib
import json
import logging
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from cypherclaw import live_midi_emitter as midi


REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "my-claw" / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


class _FakeOsc:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list[Any]]] = []

    def send_message(self, address: str, args: list[Any]) -> None:
        self.messages.append((address, args))


class _MockWorker:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def endpoint_url(self) -> str:
        if self._server is None:
            raise RuntimeError("mock Worker server has not started")
        host, port = self._server.server_address
        return f"http://{host}:{port}/api/cypherclaw/midi-event"

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                body = self.rfile.read(length)
                owner.headers.append(
                    {key.lower(): value for key, value in self.headers.items()}
                )
                owner.payloads.append(json.loads(body.decode("utf-8")))
                response = b'{"ok":true}'
                self.send_response(202)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="mock-live-midi-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _load_duet_composer(monkeypatch: pytest.MonkeyPatch) -> Any:
    pythonosc = types.ModuleType("pythonosc")
    udp_client = types.ModuleType("pythonosc.udp_client")

    class SimpleUDPClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.messages: list[tuple[str, list[Any]]] = []

        def send_message(self, address: str, args: list[Any]) -> None:
            self.messages.append((address, args))

    udp_client.SimpleUDPClient = SimpleUDPClient
    pythonosc.udp_client = udp_client
    monkeypatch.setitem(sys.modules, "pythonosc", pythonosc)
    monkeypatch.setitem(sys.modules, "pythonosc.udp_client", udp_client)
    monkeypatch.delitem(sys.modules, "duet_composer", raising=False)
    return importlib.import_module("duet_composer")


def test_composer_events_reach_mock_worker_batched_with_tags_and_ordering(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    duet_composer = _load_duet_composer(monkeypatch)
    osc = _FakeOsc()
    worker = _MockWorker()
    worker.start()
    try:
        config = midi.LiveMidiEmitterConfig(
            endpoint_url=worker.endpoint_url,
            batch_size=4,
            flush_interval_seconds=60.0,
            max_retries=0,
            source="pytest-composer-e2e",
        )
        queue = midi.BatchingMidiQueue(
            max_size=config.batch_size,
            flush_interval_seconds=config.flush_interval_seconds,
        )
        publisher = midi.LiveMidiPublisher(
            queue=queue,
            config=config,
            post_batch=lambda batch: midi.post_midi_batch(
                batch,
                config,
                batch_id="e2e-batch-1",
            ),
        )
        event_times = iter((1000.0, 1001.0))
        monkeypatch.setattr(duet_composer, "_live_midi_publisher", publisher)
        monkeypatch.setattr(duet_composer, "c", osc)
        monkeypatch.setattr(duet_composer, "next_nid", lambda: 60123)
        monkeypatch.setattr(
            duet_composer,
            "time",
            types.SimpleNamespace(time=lambda: next(event_times)),
        )

        with caplog.at_level(logging.INFO, logger=midi.LOGGER.name):
            duet_composer.play_voice(
                "pluck",
                261.625565,
                0.12,
                0.5,
                role="melody",
                scene="Theme",
                tuning="just_intonation_5_limit",
                live_midi_metadata={
                    "lane_name": "lead",
                    "row": 0,
                    "song_title": "Mock Worker Sonata",
                },
            )
            duet_composer.play_voice(
                "pluck",
                329.627557,
                0.18,
                0.25,
                role="countermelody",
                scene="Theme",
                tuning="just_intonation_5_limit",
                live_midi_metadata={
                    "lane_name": "answer",
                    "row": 4,
                    "song_title": "Mock Worker Sonata",
                },
            )

        assert len(worker.payloads) == 1
        payload = worker.payloads[0]
        assert payload["schema_version"] == midi.MIDI_EVENT_SCHEMA_VERSION
        assert payload["source"] == "pytest-composer-e2e"
        assert payload["batch_id"] == "e2e-batch-1"
        assert payload["event_count"] == 4

        events = payload["events"]
        assert [
            (
                event["event_type"],
                event["voice"],
                event["scene"],
                event["tuning"],
                event["data1"],
                event["data2"],
                event["ts"],
            )
            for event in events
        ] == [
            (
                midi.MIDI_EVENT_NOTE_ON,
                "pluck",
                "Theme",
                "just_intonation_5_limit",
                60,
                64,
                1000.0,
            ),
            (
                midi.MIDI_EVENT_NOTE_OFF,
                "pluck",
                "Theme",
                "just_intonation_5_limit",
                60,
                0,
                1000.5,
            ),
            (
                midi.MIDI_EVENT_NOTE_ON,
                "pluck",
                "Theme",
                "just_intonation_5_limit",
                64,
                95,
                1001.0,
            ),
            (
                midi.MIDI_EVENT_NOTE_OFF,
                "pluck",
                "Theme",
                "just_intonation_5_limit",
                64,
                0,
                1001.25,
            ),
        ]
        assert events[0]["metadata"] == {
            "duration_seconds": 0.5,
            "frequency_hz": 261.626,
            "lane_name": "lead",
            "role": "melody",
            "row": 0,
            "song_title": "Mock Worker Sonata",
        }
        assert events[2]["metadata"] == {
            "duration_seconds": 0.25,
            "frequency_hz": 329.628,
            "lane_name": "answer",
            "role": "countermelody",
            "row": 4,
            "song_title": "Mock Worker Sonata",
        }
        assert [message[0] for message in osc.messages] == ["/s_new", "/s_new"]

        log_text = "\n".join(record.getMessage() for record in caplog.records)
        assert "live_midi_publisher_batch_flushed" in log_text
        assert "live_midi_http_post_succeeded" in log_text
        assert "batch_id=e2e-batch-1" in log_text
        assert "events=4" in log_text
        assert f"endpoint={worker.endpoint_url}" in log_text
        assert "first_event=note_on:pluck:Theme:just_intonation_5_limit" in log_text
        assert "last_event=note_off:pluck:Theme:just_intonation_5_limit" in log_text
    finally:
        worker.stop()
