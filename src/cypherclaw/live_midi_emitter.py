"""Live MIDI emitter daemon scaffold.

This module owns the T-053a plumbing only: typed live MIDI event payloads,
environment-backed config, size/time batching, a retrying stdlib HTTP POST
client, and graceful shutdown. Composer integration is intentionally deferred.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT_URL = "https://cypherclaw.holdenu.com/api/cypherclaw/midi-event"
DEFAULT_BATCH_SIZE = 32
DEFAULT_FLUSH_INTERVAL_SECONDS = 0.25
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.25
DEFAULT_SOURCE = "cypherclaw-live-midi-emitter"

MIDI_EVENT_SCHEMA_VERSION = "cypherclaw.live_midi_event.v1"
MIDI_EVENT_NOTE_ON = "note_on"
MIDI_EVENT_NOTE_OFF = "note_off"
MIDI_EVENT_CONTROL_CHANGE = "control_change"
MIDI_EVENT_PITCH_BEND = "pitch_bend"
SUPPORTED_MIDI_EVENT_TYPES: tuple[str, ...] = (
    MIDI_EVENT_NOTE_ON,
    MIDI_EVENT_NOTE_OFF,
    MIDI_EVENT_CONTROL_CHANGE,
    MIDI_EVENT_PITCH_BEND,
)

LOGGER = logging.getLogger("cypherclaw.live_midi_emitter")


class HttpResponse(Protocol):
    """Small response protocol used by urllib and test fakes."""

    status: int
    code: int

    def __enter__(self) -> HttpResponse:
        ...

    def __exit__(self, *_args: object) -> None:
        ...

    def read(self) -> bytes:
        ...


UrlOpenFn = Callable[..., HttpResponse]
SleepFn = Callable[[float], None]
ClockFn = Callable[[], float]
PostBatchFn = Callable[[Sequence["LiveMidiEvent"]], "MidiPostResult"]


@dataclass(frozen=True)
class LiveMidiEvent:
    """One live MIDI event plus optional CypherClaw render context."""

    event_type: str
    status: int
    data1: int
    data2: int
    ts: float
    voice: str = ""
    scene: str = ""
    tuning: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event_type(self.event_type)
        _validate_midi_status_byte("status", self.status)
        _validate_midi_data_byte("data1", self.data1)
        _validate_midi_data_byte("data2", self.data2)
        _validate_event_status_shape(
            self.event_type,
            status=self.status,
            data1=self.data1,
            data2=self.data2,
        )
        if not isinstance(self.ts, int | float) or not math.isfinite(float(self.ts)):
            raise ValueError("ts must be a finite number")
        _validate_context_tag("voice", self.voice)
        _validate_context_tag("scene", self.scene)
        _validate_context_tag("tuning", self.tuning)
        _validate_metadata(self.metadata)

    @property
    def channel(self) -> int:
        """Return the MIDI channel encoded in the status byte."""

        return self.status & 0x0F

    @property
    def pitch_bend_value(self) -> int | None:
        """Return the 14-bit pitch-bend value for pitch-bend events."""

        if self.event_type != MIDI_EVENT_PITCH_BEND:
            return None
        return (self.data2 << 7) | self.data1

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-safe POST representation."""

        return {
            "event_type": self.event_type,
            "status": self.status,
            "data1": self.data1,
            "data2": self.data2,
            "ts": float(self.ts),
            "voice": self.voice,
            "scene": self.scene,
            "tuning": self.tuning,
            "metadata": _json_safe_mapping(self.metadata),
        }


@dataclass(frozen=True)
class LiveMidiEmitterConfig:
    """Runtime knobs for the live MIDI emitter daemon."""

    endpoint_url: str = DEFAULT_ENDPOINT_URL
    admin_token: str = ""
    batch_size: int = DEFAULT_BATCH_SIZE
    flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    source: str = DEFAULT_SOURCE

    def __post_init__(self) -> None:
        if not self.endpoint_url:
            raise ValueError("endpoint_url must be non-empty")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.flush_interval_seconds < 0:
            raise ValueError("flush_interval_seconds must be non-negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be non-negative")
        if not self.source:
            raise ValueError("source must be non-empty")


@dataclass(frozen=True)
class MidiPostResult:
    """Result from posting one batch to the Worker."""

    ok: bool
    status_code: int | None
    attempts: int
    event_count: int
    response_body: str

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "event_count": self.event_count,
            "response_body": self.response_body,
        }


class MidiPostError(RuntimeError):
    """Raised when a MIDI batch cannot be posted."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        attempts: int,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


class BatchingMidiQueue:
    """Thread-safe size/time batching queue for live MIDI events."""

    def __init__(
        self,
        *,
        max_size: int,
        flush_interval_seconds: float,
        clock: ClockFn = time.monotonic,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if flush_interval_seconds < 0:
            raise ValueError("flush_interval_seconds must be non-negative")
        self._max_size = max_size
        self._flush_interval_seconds = flush_interval_seconds
        self._clock = clock
        self._pending: list[LiveMidiEvent] = []
        self._first_event_at: float | None = None
        self._lock = threading.Lock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def add(self, event: LiveMidiEvent) -> tuple[LiveMidiEvent, ...]:
        """Add an event and return a full batch when size triggers."""

        with self._lock:
            if not self._pending:
                self._first_event_at = self._clock()
            self._pending.append(event)
            if len(self._pending) >= self._max_size:
                return self._flush_locked()
            return ()

    def flush_due(self) -> tuple[LiveMidiEvent, ...]:
        """Return a batch when the time trigger has elapsed."""

        with self._lock:
            if not self._pending or self._first_event_at is None:
                return ()
            elapsed = self._clock() - self._first_event_at
            if elapsed >= self._flush_interval_seconds:
                return self._flush_locked()
            return ()

    def flush_all(self) -> tuple[LiveMidiEvent, ...]:
        """Flush any queued events regardless of age."""

        with self._lock:
            if not self._pending:
                return ()
            return self._flush_locked()

    def _flush_locked(self) -> tuple[LiveMidiEvent, ...]:
        batch = tuple(self._pending)
        self._pending.clear()
        self._first_event_at = None
        return batch


class LiveMidiPublisher:
    """Producer-facing wrapper for the emitter batching queue."""

    def __init__(
        self,
        *,
        queue: BatchingMidiQueue | None = None,
        config: LiveMidiEmitterConfig | None = None,
        post_batch: PostBatchFn | None = None,
        clock: ClockFn = time.monotonic,
    ) -> None:
        if queue is None:
            active_config = config or load_config()
            queue = BatchingMidiQueue(
                max_size=active_config.batch_size,
                flush_interval_seconds=active_config.flush_interval_seconds,
                clock=clock,
            )
        self._queue = queue
        self._post_batch = post_batch

    @property
    def pending_count(self) -> int:
        return self._queue.pending_count

    def publish(self, event: LiveMidiEvent) -> tuple[LiveMidiEvent, ...]:
        """Queue one event and return a batch if the size trigger fires."""

        return self._post_if_configured(self._queue.add(event))

    def flush_due(self) -> tuple[LiveMidiEvent, ...]:
        """Return a batch when the queue's time trigger has elapsed."""

        return self._post_if_configured(self._queue.flush_due())

    def flush_all(self) -> tuple[LiveMidiEvent, ...]:
        """Flush all pending producer events."""

        return self._post_if_configured(self._queue.flush_all())

    def _post_if_configured(
        self,
        batch: tuple[LiveMidiEvent, ...],
    ) -> tuple[LiveMidiEvent, ...]:
        if batch and self._post_batch is not None:
            self._post_batch(batch)
        return batch


def load_config(
    environ: Mapping[str, str] | None = None,
) -> LiveMidiEmitterConfig:
    """Load emitter config from environment variables."""

    env = os.environ if environ is None else environ
    return LiveMidiEmitterConfig(
        endpoint_url=env.get("CYPHERCLAW_LIVE_MIDI_ENDPOINT", DEFAULT_ENDPOINT_URL),
        admin_token=env.get("CYPHERCLAW_LIVE_MIDI_TOKEN", ""),
        batch_size=_int_env(env, "CYPHERCLAW_LIVE_MIDI_BATCH_SIZE", DEFAULT_BATCH_SIZE),
        flush_interval_seconds=_float_env(
            env,
            "CYPHERCLAW_LIVE_MIDI_FLUSH_SECONDS",
            DEFAULT_FLUSH_INTERVAL_SECONDS,
        ),
        timeout_seconds=_float_env(
            env,
            "CYPHERCLAW_LIVE_MIDI_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        ),
        max_retries=_int_env(
            env,
            "CYPHERCLAW_LIVE_MIDI_MAX_RETRIES",
            DEFAULT_MAX_RETRIES,
        ),
        backoff_base_seconds=_float_env(
            env,
            "CYPHERCLAW_LIVE_MIDI_BACKOFF_SECONDS",
            DEFAULT_BACKOFF_BASE_SECONDS,
        ),
        source=env.get("CYPHERCLAW_LIVE_MIDI_SOURCE", DEFAULT_SOURCE),
    )


def build_batch_payload(
    events: Sequence[LiveMidiEvent],
    config: LiveMidiEmitterConfig,
    *,
    batch_id: str | None = None,
) -> dict[str, object]:
    """Return the JSON-safe POST payload for a MIDI event batch."""

    return {
        "schema_version": MIDI_EVENT_SCHEMA_VERSION,
        "source": config.source,
        "batch_id": batch_id or str(uuid.uuid4()),
        "event_count": len(events),
        "events": [event.to_dict() for event in events],
    }


def build_note_on_event(
    *,
    note: int,
    velocity: int,
    ts: float,
    channel: int = 0,
    voice: str = "",
    scene: str = "",
    tuning: str = "",
    metadata: Mapping[str, object] | None = None,
) -> LiveMidiEvent:
    """Construct a validated live MIDI note-on event."""

    _validate_midi_data_byte("note", note)
    _validate_note_on_velocity(velocity)
    return LiveMidiEvent(
        event_type=MIDI_EVENT_NOTE_ON,
        status=_status_for_channel(0x90, channel),
        data1=note,
        data2=velocity,
        ts=ts,
        voice=voice,
        scene=scene,
        tuning=tuning,
        metadata=_metadata_or_empty(metadata),
    )


def build_note_off_event(
    *,
    note: int,
    ts: float,
    release_velocity: int = 0,
    channel: int = 0,
    voice: str = "",
    scene: str = "",
    tuning: str = "",
    metadata: Mapping[str, object] | None = None,
) -> LiveMidiEvent:
    """Construct a validated live MIDI note-off event."""

    _validate_midi_data_byte("note", note)
    _validate_midi_data_byte("release_velocity", release_velocity)
    return LiveMidiEvent(
        event_type=MIDI_EVENT_NOTE_OFF,
        status=_status_for_channel(0x80, channel),
        data1=note,
        data2=release_velocity,
        ts=ts,
        voice=voice,
        scene=scene,
        tuning=tuning,
        metadata=_metadata_or_empty(metadata),
    )


def build_control_change_event(
    *,
    controller: int,
    value: int,
    ts: float,
    channel: int = 0,
    voice: str = "",
    scene: str = "",
    tuning: str = "",
    metadata: Mapping[str, object] | None = None,
) -> LiveMidiEvent:
    """Construct a validated live MIDI control-change event."""

    _validate_midi_data_byte("controller", controller)
    _validate_midi_data_byte("value", value)
    return LiveMidiEvent(
        event_type=MIDI_EVENT_CONTROL_CHANGE,
        status=_status_for_channel(0xB0, channel),
        data1=controller,
        data2=value,
        ts=ts,
        voice=voice,
        scene=scene,
        tuning=tuning,
        metadata=_metadata_or_empty(metadata),
    )


def build_pitch_bend_event(
    *,
    value: int,
    ts: float,
    channel: int = 0,
    voice: str = "",
    scene: str = "",
    tuning: str = "",
    metadata: Mapping[str, object] | None = None,
) -> LiveMidiEvent:
    """Construct a validated live MIDI pitch-bend event from a 14-bit value."""

    _validate_pitch_bend_value(value)
    return LiveMidiEvent(
        event_type=MIDI_EVENT_PITCH_BEND,
        status=_status_for_channel(0xE0, channel),
        data1=value & 0x7F,
        data2=(value >> 7) & 0x7F,
        ts=ts,
        voice=voice,
        scene=scene,
        tuning=tuning,
        metadata=_metadata_or_empty(metadata),
    )


def serialize_midi_event(event: LiveMidiEvent) -> dict[str, object]:
    """Serialize a validated live MIDI event to the schema dictionary."""

    return event.to_dict()


def validate_live_midi_event_payload(payload: Mapping[str, object]) -> LiveMidiEvent:
    """Validate a payload mapping and return the equivalent live MIDI event."""

    if not isinstance(payload, Mapping):
        raise ValueError("event payload must be a mapping")
    for field_name in ("event_type", "status", "data1", "data2", "ts"):
        if field_name not in payload:
            raise ValueError(f"event payload missing required field: {field_name}")
    schema_version = payload.get("schema_version")
    if schema_version is not None and schema_version != MIDI_EVENT_SCHEMA_VERSION:
        raise ValueError(
            "schema_version must be "
            f"{MIDI_EVENT_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    event_type = _payload_string(payload, "event_type")
    status = _payload_int(payload, "status")
    data1 = _payload_int(payload, "data1")
    data2 = _payload_int(payload, "data2")
    if "channel" in payload:
        channel = _payload_int(payload, "channel")
        if channel != (status & 0x0F):
            raise ValueError("channel must match the status byte channel")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    return LiveMidiEvent(
        event_type=event_type,
        status=status,
        data1=data1,
        data2=data2,
        ts=_payload_number(payload, "ts"),
        voice=_payload_optional_string(payload, "voice"),
        scene=_payload_optional_string(payload, "scene"),
        tuning=_payload_optional_string(payload, "tuning"),
        metadata=metadata,
    )


def post_midi_batch(
    events: Sequence[LiveMidiEvent],
    config: LiveMidiEmitterConfig,
    *,
    batch_id: str | None = None,
    urlopen_fn: UrlOpenFn = urlopen,
    sleep_fn: SleepFn = time.sleep,
) -> MidiPostResult:
    """Post one MIDI batch to the Worker with retry/backoff."""

    batch = tuple(events)
    if not batch:
        return MidiPostResult(
            ok=True,
            status_code=None,
            attempts=0,
            event_count=0,
            response_body="",
        )

    request = build_post_request(batch, config, batch_id=batch_id)
    max_attempts = config.max_retries + 1
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen_fn(request, timeout=config.timeout_seconds) as response:  # noqa: S310
                body = _decode_body(response.read())
                status_code = _response_status(response)
            if 200 <= status_code < 300:
                return MidiPostResult(
                    ok=True,
                    status_code=status_code,
                    attempts=attempt,
                    event_count=len(batch),
                    response_body=body,
                )
            if not _should_retry_status(status_code) or attempt > config.max_retries:
                raise MidiPostError(
                    f"Worker returned HTTP {status_code}",
                    status_code=status_code,
                    attempts=attempt,
                )
        except HTTPError as exc:
            status_code = int(exc.code)
            last_error = exc
            if not _should_retry_status(status_code) or attempt > config.max_retries:
                raise MidiPostError(
                    f"Worker returned HTTP {status_code}",
                    status_code=status_code,
                    attempts=attempt,
                ) from exc
        except URLError as exc:
            last_error = exc
            if attempt > config.max_retries:
                raise MidiPostError(
                    f"Worker POST failed: {exc.reason}",
                    status_code=None,
                    attempts=attempt,
                ) from exc

        delay = _backoff_delay(config.backoff_base_seconds, attempt)
        LOGGER.warning(
            "live_midi_post_retry attempt=%d max_attempts=%d delay=%.3f error=%s",
            attempt,
            max_attempts,
            delay,
            last_error,
        )
        sleep_fn(delay)

    raise MidiPostError(
        "Worker POST failed after retries",
        status_code=None,
        attempts=max_attempts,
    )


def build_post_request(
    events: Sequence[LiveMidiEvent],
    config: LiveMidiEmitterConfig,
    *,
    batch_id: str | None = None,
) -> Request:
    """Build a JSON POST request for a MIDI batch."""

    payload = build_batch_payload(events, config, batch_id=batch_id)
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "cypherclaw-live-midi-emitter/1",
    }
    if config.admin_token:
        headers["Authorization"] = f"Bearer {config.admin_token}"
    return Request(config.endpoint_url, data=data, headers=headers, method="POST")


def run_daemon(
    config: LiveMidiEmitterConfig,
    stop_event: threading.Event | None = None,
    *,
    queue: BatchingMidiQueue | None = None,
    post_batch: PostBatchFn | None = None,
    poll_interval: float = 0.05,
) -> int:
    """Run the idle emitter loop until stopped, flushing pending events."""

    if stop_event is None:
        stop_event = threading.Event()
    active_queue = queue or BatchingMidiQueue(
        max_size=config.batch_size,
        flush_interval_seconds=config.flush_interval_seconds,
    )
    post = post_batch or (lambda batch: post_midi_batch(batch, config))

    try:
        while not stop_event.is_set():
            _post_if_present(active_queue.flush_due(), post)
            stop_event.wait(timeout=poll_interval)
    finally:
        _post_if_present(active_queue.flush_all(), post)
    return 0


def install_signal_handlers(stop_event: threading.Event) -> None:
    """Wire SIGINT/SIGTERM to request graceful shutdown."""

    def _handle(signum: int, _frame: object) -> None:
        LOGGER.info("shutdown_signal signal=%d", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure key=value-style daemon logging."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the daemon scaffold."""

    parser = argparse.ArgumentParser(description="CypherClaw live MIDI emitter")
    parser.add_argument("--endpoint-url", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--flush-interval", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--backoff-base", type=float, default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    configure_logging()
    config = _config_with_cli_overrides(load_config(), args)
    stop_event = threading.Event()
    install_signal_handlers(stop_event)
    LOGGER.info(
        "live_midi_emitter_started endpoint=%s batch_size=%d flush_interval=%.3f",
        config.endpoint_url,
        config.batch_size,
        config.flush_interval_seconds,
    )
    try:
        return run_daemon(config, stop_event)
    finally:
        LOGGER.info("live_midi_emitter_exiting")


def _config_with_cli_overrides(
    config: LiveMidiEmitterConfig,
    args: argparse.Namespace,
) -> LiveMidiEmitterConfig:
    return LiveMidiEmitterConfig(
        endpoint_url=(
            args.endpoint_url if args.endpoint_url is not None else config.endpoint_url
        ),
        admin_token=config.admin_token,
        batch_size=args.batch_size if args.batch_size is not None else config.batch_size,
        flush_interval_seconds=(
            args.flush_interval
            if args.flush_interval is not None
            else config.flush_interval_seconds
        ),
        timeout_seconds=args.timeout if args.timeout is not None else config.timeout_seconds,
        max_retries=(
            args.max_retries if args.max_retries is not None else config.max_retries
        ),
        backoff_base_seconds=(
            args.backoff_base
            if args.backoff_base is not None
            else config.backoff_base_seconds
        ),
        source=args.source if args.source is not None else config.source,
    )


def _post_if_present(
    batch: Sequence[LiveMidiEvent],
    post_batch: PostBatchFn,
) -> None:
    if not batch:
        return
    try:
        result = post_batch(batch)
    except MidiPostError as exc:
        LOGGER.warning(
            "live_midi_post_failed attempts=%d status=%s error=%s",
            exc.attempts,
            exc.status_code,
            exc,
        )
        return
    LOGGER.info(
        "live_midi_batch_posted events=%d attempts=%d status=%s",
        result.event_count,
        result.attempts,
        result.status_code,
    )


def _validate_event_type(value: object) -> None:
    if value not in SUPPORTED_MIDI_EVENT_TYPES:
        raise ValueError(
            "event_type must be one of "
            f"{SUPPORTED_MIDI_EVENT_TYPES!r}, got {value!r}"
        )


def _validate_midi_status_byte(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer MIDI byte")
    if value < 0 or value > 255:
        raise ValueError(f"{name} must be between 0 and 255")


def _validate_midi_data_byte(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer MIDI data byte")
    if value < 0 or value > 127:
        raise ValueError(f"{name} must be between 0 and 127")


def _validate_event_status_shape(
    event_type: str,
    *,
    status: int,
    data1: int,
    data2: int,
) -> None:
    del data1
    status_class = status & 0xF0
    if event_type == MIDI_EVENT_NOTE_ON:
        if status_class != 0x90:
            raise ValueError("status must use 0x90 for note_on")
        _validate_note_on_velocity(data2)
        return
    if event_type == MIDI_EVENT_NOTE_OFF:
        if status_class == 0x80:
            return
        if status_class == 0x90 and data2 == 0:
            return
        raise ValueError("status must use 0x80 or 0x90 velocity zero for note_off")
    if event_type == MIDI_EVENT_CONTROL_CHANGE:
        if status_class != 0xB0:
            raise ValueError("status must use 0xB0 for control_change")
        return
    if event_type == MIDI_EVENT_PITCH_BEND:
        if status_class != 0xE0:
            raise ValueError("status must use 0xE0 for pitch_bend")
        return


def _validate_note_on_velocity(value: object) -> None:
    _validate_midi_data_byte("velocity", value)
    if value == 0:
        raise ValueError("velocity must be between 1 and 127 for note_on")


def _validate_channel(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("channel must be an integer")
    if value < 0 or value > 15:
        raise ValueError("channel must be between 0 and 15")


def _validate_pitch_bend_value(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("bend value must be an integer")
    if value < 0 or value > 16383:
        raise ValueError("bend value must be between 0 and 16383")


def _validate_context_tag(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string context tag")


def _validate_metadata(metadata: object) -> None:
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    _ensure_json_safe("metadata", metadata)


def _ensure_json_safe(label: str, value: object) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{label} must be JSON-safe")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} keys must be strings")
            _ensure_json_safe(f"{label}.{key}", item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            _ensure_json_safe(f"{label}[{index}]", item)
        return
    raise ValueError(f"{label} must be JSON-safe")


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe_value(item) for item in value]
    return value


def _json_safe_mapping(metadata: Mapping[str, object]) -> dict[str, object]:
    return {key: _json_safe_value(value) for key, value in metadata.items()}


def _status_for_channel(status_class: int, channel: int) -> int:
    _validate_channel(channel)
    return status_class | channel


def _metadata_or_empty(
    metadata: Mapping[str, object] | None,
) -> Mapping[str, object]:
    return {} if metadata is None else metadata


def _payload_string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _payload_optional_string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name, "")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _payload_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _payload_number(payload: Mapping[str, object], field_name: str) -> float:
    value = payload[field_name]
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    return result


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _float_env(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _response_status(response: HttpResponse) -> int:
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    code = getattr(response, "code", None)
    if isinstance(code, int):
        return code
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        value = getcode()
        if isinstance(value, int):
            return value
    return 200


def _should_retry_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _backoff_delay(base_seconds: float, attempt: int) -> float:
    return base_seconds * (2 ** (attempt - 1))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
