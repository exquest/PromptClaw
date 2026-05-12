"""Rolling JACK capture buffers for contact and room microphones."""
from __future__ import annotations

import json
import logging
import math
import os
import signal
import sqlite3
import threading
import time
import uuid
import wave
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
import numpy.typing as npt

try:
    from cypherclaw.first_boot import bootstrap_identity
except ImportError:
    try:
        from first_boot import bootstrap_identity
    except ImportError:
        def bootstrap_identity(*args, **kwargs): pass


if TYPE_CHECKING:
    pass


LOGGER = logging.getLogger(__name__)

CLIENT_NAME = "cypherclaw-capture"
SAMPLE_RATE = 48_000
BUFFER_DURATION_SECONDS = 60

JACK_SOURCE_PORTS = {
    "contact": "system:capture_1",
    "room": "system:capture_2",
    "self": "SuperCollider:out_1",
}

JACK_INPUT_PORTS = {
    "contact": "in_contact",
    "room": "in_room",
    "self": "in_self",
}

SAMPLE_CAPTURE_ROOT = Path("/home/user/cypherclaw-data/samples")
SAMPLE_INDEX_FILENAME = "index.sqlite"
CAPTURE_CONTEXT_PATHS: dict[str, Path] = {
    "organism": Path("/tmp/organism_state.json"),
    "room_presence": Path("/tmp/room_presence.json"),
}


class JackInputPort(Protocol):
    name: str

    def get_array(self) -> npt.NDArray[np.float32]:
        ...


class JackInputPortRegistry(Protocol):
    def register(self, name: str) -> JackInputPort:
        ...


class JackClientProtocol(Protocol):
    inports: JackInputPortRegistry

    def set_process_callback(self, callback: object) -> None:
        ...

    def set_xrun_callback(self, callback: object) -> None:
        ...

    def activate(self) -> None:
        ...

    def connect(self, source: str, destination: object) -> None:
        ...

    def close(self) -> None:
        ...


def _create_jack_client(name: str) -> JackClientProtocol:
    try:
        import jack
    except ImportError as exc:  # pragma: no cover - exercised by runtime only
        raise RuntimeError(
            "python-jack-client is required to run sample_capture_daemon"
        ) from exc
    return jack.Client(name)


@dataclass(slots=True)
class NumpyRingBuffer:
    sample_rate: int
    duration_seconds: int
    capacity: int = field(init=False)
    _data: npt.NDArray[np.float32] = field(init=False)
    _write_index: int = field(init=False, default=0)
    _filled: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.capacity = self.sample_rate * self.duration_seconds
        self._data = np.zeros(self.capacity, dtype=np.float32)
        self._write_index = 0
        self._filled = 0

    def append(self, samples: npt.ArrayLike) -> None:
        chunk = np.asarray(samples, dtype=np.float32).reshape(-1)
        if chunk.size == 0:
            return
        if chunk.size >= self.capacity:
            self._data[:] = chunk[-self.capacity :]
            self._write_index = 0
            self._filled = self.capacity
            return

        first_copy = min(chunk.size, self.capacity - self._write_index)
        self._data[self._write_index : self._write_index + first_copy] = chunk[:first_copy]
        remaining = chunk.size - first_copy
        if remaining:
            self._data[:remaining] = chunk[first_copy:]
        self._write_index = (self._write_index + chunk.size) % self.capacity
        self._filled = min(self.capacity, self._filled + chunk.size)

    def get_window(self, duration_sec: float, offset_sec: float = 0.0) -> npt.NDArray[np.float32]:
        if duration_sec < 0 or offset_sec < 0:
            raise ValueError("duration_sec and offset_sec must be non-negative")
        requested = int(round(duration_sec * self.sample_rate))
        offset = int(round(offset_sec * self.sample_rate))
        if requested == 0:
            return np.zeros(0, dtype=np.float32)
        if requested + offset > self.capacity:
            raise ValueError("requested window exceeds ring-buffer capacity")

        end = self._filled - offset
        if end <= 0:
            return np.zeros(requested, dtype=np.float32)

        available = min(requested, end)
        start = end - available
        payload = self._read_oldest_slice(start, available)
        if available == requested:
            return payload
        padding = np.zeros(requested - available, dtype=np.float32)
        return np.concatenate((padding, payload))

    def peak_offset_seconds(self) -> float:
        """Return seconds-back-from-now of the buffer's peak abs value."""
        if self._filled == 0 or self.sample_rate <= 0:
            return 0.0
        if self._filled < self.capacity:
            ordered = self._data[: self._filled]
        else:
            ordered = np.concatenate(
                (self._data[self._write_index :], self._data[: self._write_index])
            )
        if ordered.size == 0:
            return 0.0
        peak_idx = int(np.argmax(np.abs(ordered)))
        samples_since_peak = self._filled - 1 - peak_idx
        return float(samples_since_peak) / float(self.sample_rate)

    def _read_oldest_slice(self, start: int, length: int) -> npt.NDArray[np.float32]:
        if length <= 0:
            return np.zeros(0, dtype=np.float32)
        oldest_index = 0 if self._filled < self.capacity else self._write_index
        start_index = (oldest_index + start) % self.capacity
        first_copy = min(length, self.capacity - start_index)
        if first_copy == length:
            return self._data[start_index : start_index + length].copy()
        return np.concatenate(
            (
                self._data[start_index : start_index + first_copy],
                self._data[: length - first_copy],
            )
        ).astype(np.float32, copy=False)


class SampleCaptureDaemon:
    """Capture rolling mono buffers from JACK contact and room inputs."""

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        buffer_duration_seconds: int = BUFFER_DURATION_SECONDS,
        client_factory: Callable[[str], JackClientProtocol] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.buffer_duration_seconds = buffer_duration_seconds
        self.input_port_names = dict(JACK_INPUT_PORTS)
        self.source_port_names = dict(JACK_SOURCE_PORTS)
        self._client_factory = client_factory or _create_jack_client
        self._logger = logger or LOGGER
        self._client: JackClientProtocol | None = None
        self._input_ports: dict[str, JackInputPort] = {}
        self._buffers = {
            source: NumpyRingBuffer(sample_rate=sample_rate, duration_seconds=buffer_duration_seconds)
            for source in self.source_port_names
        }
        self._lock = threading.Lock()
        self.xrun_count = 0

    def start(self) -> None:
        if self._client is not None:
            return
        client = self._client_factory(CLIENT_NAME)
        self._client = client
        self._input_ports = {
            source: client.inports.register(port_name)
            for source, port_name in self.input_port_names.items()
        }
        client.set_process_callback(self._process)
        client.set_xrun_callback(self._handle_xrun)
        client.activate()
        for source, source_port in self.source_port_names.items():
            self._connect_port(source_port, self._input_ports[source])

    def stop(self) -> None:
        client = self._client
        self._client = None
        self._input_ports = {}
        if client is None:
            return
        client.close()

    def get_window(self, source: str, duration_sec: float, offset_sec: float = 0.0) -> npt.NDArray[np.float32]:
        if source not in self._buffers:
            raise KeyError(f"unknown source: {source}")
        with self._lock:
            return self._buffers[source].get_window(duration_sec, offset_sec)

    def peak_offset_seconds(self, source: str) -> float:
        if source not in self._buffers:
            raise KeyError(f"unknown source: {source}")
        with self._lock:
            return self._buffers[source].peak_offset_seconds()

    def _process(self, frames: int) -> int:
        with self._lock:
            for source, port in self._input_ports.items():
                samples = np.asarray(port.get_array(), dtype=np.float32).reshape(-1)
                if samples.size > frames:
                    samples = samples[:frames]
                self._buffers[source].append(samples)
        return 0

    def _handle_xrun(self, *args: object) -> int:
        self.xrun_count += 1
        delay_usecs = 0.0
        if args:
            candidate = args[0]
            if isinstance(candidate, (int, float)):
                delay_usecs = float(candidate)
        self._logger.warning("JACK xrun detected (count=%s delay_usecs=%.2f)", self.xrun_count, delay_usecs)
        return 0

    def _connect_port(self, source_port: str, input_port: JackInputPort) -> None:
        assert self._client is not None
        try:
            self._client.connect(source_port, input_port)
            return
        except TypeError:
            pass
        self._client.connect(source_port, f"{CLIENT_NAME}:{input_port.name}")


def _spectral_magnitude(samples: npt.NDArray[np.float32]) -> npt.NDArray[np.float64]:
    if samples.size == 0:
        return np.zeros(0, dtype=np.float64)
    window = np.hanning(samples.size).astype(np.float64)
    spectrum = np.fft.rfft(samples.astype(np.float64) * window)
    return np.abs(spectrum)


def _spectral_flux(prev_mag: npt.NDArray[np.float64], current_mag: npt.NDArray[np.float64]) -> float:
    if prev_mag.size == 0 or prev_mag.size != current_mag.size:
        return 0.0
    diff = current_mag - prev_mag
    diff[diff < 0.0] = 0.0
    norm = float(np.linalg.norm(current_mag))
    if norm <= 1e-12:
        return 0.0
    return float(np.sum(diff) / norm)


def _rms_dbfs(samples: npt.NDArray[np.float32]) -> float:
    if samples.size == 0:
        return -math.inf
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms <= 1e-9:
        return -math.inf
    return 20.0 * math.log10(rms)


def _count_transients(
    samples: npt.NDArray[np.float32],
    sample_rate: int,
    *,
    threshold_db: float,
) -> int:
    if samples.size == 0 or sample_rate <= 0:
        return 0
    frame_size = max(1, int(round(sample_rate * 0.01)))
    n_frames = samples.size // frame_size
    if n_frames < 4:
        return 0
    framed = samples[: n_frames * frame_size].astype(np.float64).reshape(n_frames, frame_size)
    energies = np.mean(np.square(framed), axis=1)
    energy_db = 10.0 * np.log10(energies + 1e-12)
    median_window = max(3, int(round(0.08 / 0.01)))
    transients = 0
    last_index = -median_window
    for i in range(median_window, n_frames):
        local_median = float(np.median(energy_db[i - median_window : i]))
        if energy_db[i] - local_median >= threshold_db and (i - last_index) >= median_window // 2:
            transients += 1
            last_index = i
    return transients


@dataclass(frozen=True)
class DetectorThresholds:
    """Tunable knobs for `InterestingMomentDetector`."""

    spectral_flux_multiplier: float = 0.6
    rms_dbfs_floor: float = -45.0
    transient_count_min: int = 2
    cooldown_seconds: float = 30.0
    window_seconds: float = 1.0
    hop_seconds: float = 0.25
    min_capture_seconds: float = 4.0
    max_capture_seconds: float = 8.0
    flux_history_size: int = 20
    transient_threshold_db: float = 6.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "DetectorThresholds":
        env = os.environ if env is None else env

        def _float(name: str, default: float) -> float:
            raw = env.get(name)
            return float(raw) if raw is not None else default

        def _int(name: str, default: int) -> int:
            raw = env.get(name)
            return int(raw) if raw is not None else default

        defaults = cls()
        return cls(
            spectral_flux_multiplier=_float("SAMPLE_CAPTURE_FLUX_MULTIPLIER", defaults.spectral_flux_multiplier),
            rms_dbfs_floor=_float("SAMPLE_CAPTURE_RMS_DBFS", defaults.rms_dbfs_floor),
            transient_count_min=_int("SAMPLE_CAPTURE_TRANSIENT_MIN", defaults.transient_count_min),
            cooldown_seconds=_float("SAMPLE_CAPTURE_COOLDOWN_SEC", defaults.cooldown_seconds),
            window_seconds=_float("SAMPLE_CAPTURE_WINDOW_SEC", defaults.window_seconds),
            hop_seconds=_float("SAMPLE_CAPTURE_HOP_SEC", defaults.hop_seconds),
            min_capture_seconds=_float("SAMPLE_CAPTURE_MIN_LEN_SEC", defaults.min_capture_seconds),
            max_capture_seconds=_float("SAMPLE_CAPTURE_MAX_LEN_SEC", defaults.max_capture_seconds),
            flux_history_size=_int("SAMPLE_CAPTURE_FLUX_HISTORY", defaults.flux_history_size),
            transient_threshold_db=_float("SAMPLE_CAPTURE_TRANSIENT_DB", defaults.transient_threshold_db),
        )


@dataclass(frozen=True)
class FlaggedMoment:
    """Description of a flagged interesting-moment capture window."""

    flagged_at_sec: float
    capture_seconds: float
    pre_roll_seconds: float
    post_roll_seconds: float
    spectral_flux: float
    rms_dbfs: float
    transient_count: int


class InterestingMomentDetector:
    """Stream 1-second windows and flag novel, energetic, transient-rich moments."""

    def __init__(
        self,
        daemon: SampleCaptureDaemon | None = None,
        *,
        source: str = "room",
        sample_rate: int | None = None,
        thresholds: DetectorThresholds | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._daemon = daemon
        self._source = source
        self._thresholds = thresholds or DetectorThresholds.from_env()
        self._clock = clock or time.monotonic
        if sample_rate is not None:
            self._sample_rate = sample_rate
        elif daemon is not None:
            self._sample_rate = daemon.sample_rate
        else:
            self._sample_rate = SAMPLE_RATE
        self._prev_mag: npt.NDArray[np.float64] | None = None
        self._flux_history: deque[float] = deque(maxlen=self._thresholds.flux_history_size)
        self._last_capture_at: float | None = None

    @property
    def thresholds(self) -> DetectorThresholds:
        return self._thresholds

    @property
    def source(self) -> str:
        return self._source

    def reset(self) -> None:
        self._prev_mag = None
        self._flux_history.clear()
        self._last_capture_at = None

    def evaluate(
        self,
        samples: npt.NDArray[np.float32],
        *,
        now: float | None = None,
    ) -> FlaggedMoment | None:
        moment_at = self._clock() if now is None else now
        mag = _spectral_magnitude(samples)
        flux = 0.0 if self._prev_mag is None else _spectral_flux(self._prev_mag, mag)
        self._prev_mag = mag
        rms_db = _rms_dbfs(samples)
        transient_count = _count_transients(
            samples,
            self._sample_rate,
            threshold_db=self._thresholds.transient_threshold_db,
        )

        prior_history = list(self._flux_history)
        recent_median = float(np.median(prior_history)) if prior_history else 0.0
        self._flux_history.append(flux)

        novelty_threshold = self._thresholds.spectral_flux_multiplier * recent_median
        novelty_ok = len(prior_history) >= 2 and flux > novelty_threshold and flux > 0.0
        rms_ok = rms_db > self._thresholds.rms_dbfs_floor
        transient_ok = transient_count >= self._thresholds.transient_count_min
        cooldown_ok = (
            self._last_capture_at is None
            or (moment_at - self._last_capture_at) > self._thresholds.cooldown_seconds
        )

        if not (novelty_ok and rms_ok and transient_ok and cooldown_ok):
            return None

        capture_seconds = self._capture_length(flux, recent_median)
        residual = max(0.0, capture_seconds - self._thresholds.window_seconds)
        pre_roll = residual / 2.0
        post_roll = residual - pre_roll
        self._last_capture_at = moment_at
        return FlaggedMoment(
            flagged_at_sec=moment_at,
            capture_seconds=capture_seconds,
            pre_roll_seconds=pre_roll,
            post_roll_seconds=post_roll,
            spectral_flux=flux,
            rms_dbfs=rms_db,
            transient_count=transient_count,
        )

    def step(self) -> FlaggedMoment | None:
        if self._daemon is None:
            raise RuntimeError("InterestingMomentDetector.step requires a SampleCaptureDaemon")
        window = self._daemon.get_window(self._source, self._thresholds.window_seconds)
        return self.evaluate(window)

    def _capture_length(self, flux: float, recent_median: float) -> float:
        thresholds = self._thresholds
        span = thresholds.max_capture_seconds - thresholds.min_capture_seconds
        if span <= 0.0 or recent_median <= 0.0:
            return thresholds.min_capture_seconds + max(0.0, span) * 0.5
        ratio = flux / recent_median
        denom = max(1e-6, 2.0 - thresholds.spectral_flux_multiplier)
        richness = (min(2.0, ratio) - thresholds.spectral_flux_multiplier) / denom
        richness = max(0.0, min(1.0, richness))
        return thresholds.min_capture_seconds + richness * span


ARC_PHASES: frozenset[str] = frozenset({"build", "rise", "climax", "resolve", "rest"})
PRESENCE_LABELS: frozenset[str] = frozenset({"solo", "aware", "engaged", "performing"})
MOOD_LABELS: frozenset[str] = frozenset(
    {"melancholy", "neutral", "content", "anxious", "excited"}
)
TIME_OF_DAY_LABELS: tuple[str, ...] = (
    "night",
    "dawn",
    "morning",
    "afternoon",
    "evening",
)


@dataclass(frozen=True)
class SampleTags:
    """Unified tag record attached to a captured sample.

    Combines contextual tags drawn from the surrounding world state at
    capture time with heuristic acoustic descriptors derived from the
    audio itself (warm, bright, metallic, percussive, sustained, …).
    """

    arc_phase: str = "unknown"
    mood_label: str = "neutral"
    mood_valence: float = 0.0
    mood_arousal: float = 0.0
    presence: str = "unknown"
    presence_confidence: float = 0.0
    someone_here: bool = False
    time_of_day: str = "unknown"
    captured_at_iso: str = ""
    captured_at_unix: float = 0.0
    acoustic_tags: tuple[str, ...] = ()
    mode: str = "unknown"
    extra_tags: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["acoustic_tags"] = list(self.acoustic_tags)
        payload["extra_tags"] = dict(self.extra_tags)
        return payload


def time_of_day_from_timestamp(unix_seconds: float) -> str:
    """Bucket a unix timestamp into a coarse local time-of-day label."""
    hour = datetime.fromtimestamp(unix_seconds).hour
    if hour < 6:
        return "night"
    if hour < 9:
        return "dawn"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 20:
        return "evening"
    return "night"


def _coerce_arc_phase(raw: object) -> str:
    if isinstance(raw, str):
        candidate = raw.strip().lower()
        if candidate in ARC_PHASES:
            return candidate
    return "unknown"


def _coerce_presence(raw: object) -> str:
    if isinstance(raw, str):
        candidate = raw.strip().lower()
        if candidate in PRESENCE_LABELS:
            return candidate
    return "unknown"


def _coerce_mood_label(raw: object) -> str:
    if isinstance(raw, str):
        candidate = raw.strip().lower()
        if candidate in MOOD_LABELS:
            return candidate
    return "neutral"


def _coerce_unit(raw: object, *, lo: float, hi: float, default: float) -> float:
    if isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, (int, float)):
        value = float(raw)
        if math.isnan(value) or math.isinf(value):
            return default
        return max(lo, min(hi, value))
    return default


def _coerce_bool(raw: object, *, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "yes", "y", "1", "on"}
    return default


def _resolve_first(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def extract_context_tags(
    context: Mapping[str, Any] | None,
    *,
    captured_at: float | None = None,
) -> SampleTags:
    """Build a `SampleTags` record from a snapshot of capture-time context.

    `context` accepts the merged shape produced by reading
    `/tmp/organism_state.json` and `/tmp/room_presence.json`, or a flat
    dict with the same keys. Missing values fall back to the schema's
    defaults (``unknown`` / ``neutral`` / 0.0) so partial state is safe.
    """
    captured_at_unix = time.time() if captured_at is None else float(captured_at)
    organism = _section(context, "organism")
    presence_section = _section(context, "presence") or _section(context, "room_presence")
    mood_section = _section(organism, "mood") or _section(context, "mood")

    arc_phase = _coerce_arc_phase(_resolve_first(organism, ("arc_phase",))) if organism else "unknown"
    if arc_phase == "unknown" and context is not None:
        arc_phase = _coerce_arc_phase(_resolve_first(context, ("arc_phase",)))

    mood_label = _coerce_mood_label(_resolve_first(mood_section, ("label", "mood_label")))
    mood_valence = _coerce_unit(
        _resolve_first(mood_section, ("valence",)), lo=-1.0, hi=1.0, default=0.0
    )
    mood_arousal = _coerce_unit(
        _resolve_first(mood_section, ("arousal",)), lo=0.0, hi=1.0, default=0.0
    )

    presence_label = _coerce_presence(
        _resolve_first(presence_section, ("presence", "mode", "attention_state"))
    )
    if presence_label == "unknown" and organism:
        presence_label = _coerce_presence(_resolve_first(organism, ("mode",)))
    presence_confidence = _coerce_unit(
        _resolve_first(presence_section, ("confidence", "presence_confidence")),
        lo=0.0,
        hi=1.0,
        default=0.0,
    )
    someone_here = _coerce_bool(
        _resolve_first(presence_section, ("someone_here",)), default=False
    )

    captured_dt = datetime.fromtimestamp(captured_at_unix, tz=timezone.utc)
    captured_iso = captured_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return SampleTags(
        arc_phase=arc_phase,
        mood_label=mood_label,
        mood_valence=mood_valence,
        mood_arousal=mood_arousal,
        presence=presence_label,
        presence_confidence=presence_confidence,
        someone_here=someone_here,
        time_of_day=time_of_day_from_timestamp(captured_at_unix),
        captured_at_iso=captured_iso,
        captured_at_unix=captured_at_unix,
    )


def _section(source: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    if source is None:
        return {}
    value = source.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


@dataclass(frozen=True)
class AcousticFeatures:
    """Raw heuristic acoustic features extracted from a captured sample.

    Numeric features only — semantic tags (``warm``/``percussive``/…) are
    layered on later in the auto-tag pipeline.
    """

    spectral_centroid_hz: float = 0.0
    spectral_bandwidth_hz: float = 0.0
    transient_density_hz: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def analyze_acoustic_features(
    samples: npt.NDArray[np.float32],
    sample_rate: int,
    *,
    transient_threshold_db: float = 6.0,
) -> AcousticFeatures:
    """Compute spectral centroid, bandwidth, and transient density for a sample.

    Reuses the spectral magnitude and transient-counting primitives that
    drive the interesting-moment detector so the auto-tag pipeline shares
    a single definition of these features.
    """
    if samples.size == 0 or sample_rate <= 0:
        return AcousticFeatures()

    magnitude = _spectral_magnitude(samples)
    total = float(np.sum(magnitude))
    if total <= 1e-12:
        centroid_hz = 0.0
        bandwidth_hz = 0.0
    else:
        freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
        centroid_hz = float(np.sum(freqs * magnitude) / total)
        variance = float(np.sum(((freqs - centroid_hz) ** 2) * magnitude) / total)
        bandwidth_hz = math.sqrt(max(0.0, variance))

    transient_count = _count_transients(
        samples,
        sample_rate,
        threshold_db=transient_threshold_db,
    )
    duration_sec = samples.size / float(sample_rate)
    transient_density_hz = transient_count / duration_sec if duration_sec > 0.0 else 0.0

    return AcousticFeatures(
        spectral_centroid_hz=centroid_hz,
        spectral_bandwidth_hz=bandwidth_hz,
        transient_density_hz=transient_density_hz,
    )


@dataclass(frozen=True)
class AcousticTagThresholds:
    """Threshold knobs that map acoustic features to descriptor tags."""

    warm_centroid_max_hz: float = 800.0
    bright_centroid_min_hz: float = 2000.0
    metallic_bandwidth_max_hz: float = 600.0
    percussive_transient_min_hz: float = 3.0
    sustained_transient_max_hz: float = 0.5


_ACOUSTIC_TAG_ORDER: tuple[str, ...] = (
    "warm",
    "bright",
    "metallic",
    "percussive",
    "sustained",
)


def derive_acoustic_tags(
    features: AcousticFeatures,
    *,
    thresholds: AcousticTagThresholds | None = None,
) -> tuple[str, ...]:
    """Map raw acoustic features to descriptor tags via threshold rules.

    Returns tags in a stable canonical order so repeated calls and
    serialized records compare deterministically.
    """
    rules = thresholds or AcousticTagThresholds()
    centroid = features.spectral_centroid_hz
    bandwidth = features.spectral_bandwidth_hz
    transients = features.transient_density_hz
    has_signal = centroid > 0.0 or bandwidth > 0.0 or transients > 0.0
    if not has_signal:
        return ()

    matched: set[str] = set()
    if 0.0 < centroid < rules.warm_centroid_max_hz:
        matched.add("warm")
    if centroid >= rules.bright_centroid_min_hz:
        matched.add("bright")
        if bandwidth < rules.metallic_bandwidth_max_hz:
            matched.add("metallic")
    if transients >= rules.percussive_transient_min_hz:
        matched.add("percussive")
    elif transients <= rules.sustained_transient_max_hz:
        matched.add("sustained")

    return tuple(tag for tag in _ACOUSTIC_TAG_ORDER if tag in matched)


def build_sample_tags(
    samples: npt.NDArray[np.float32],
    sample_rate: int,
    *,
    context: Mapping[str, Any] | None = None,
    captured_at: float | None = None,
    transient_threshold_db: float = 6.0,
    acoustic_thresholds: AcousticTagThresholds | None = None,
) -> SampleTags:
    """Build a unified `SampleTags` record from audio + capture-time context."""
    context_tags = extract_context_tags(context, captured_at=captured_at)
    features = analyze_acoustic_features(
        samples,
        sample_rate,
        transient_threshold_db=transient_threshold_db,
    )
    acoustic_tags = derive_acoustic_tags(features, thresholds=acoustic_thresholds)
    return replace(context_tags, acoustic_tags=acoustic_tags)


@dataclass(frozen=True)
class SavedCapture:
    """A persisted sample capture plus the tag record emitted at write time."""

    sample_id: str
    source: str
    path: Path
    tags: SampleTags
    sample_rate: int
    frame_count: int
    index_path: Path
    gain_db: float = 0.0


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def load_capture_context(
    paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Load the organism/presence snapshot used for capture-time auto-tagging."""
    resolved_paths = CAPTURE_CONTEXT_PATHS if paths is None else dict(paths)
    organism = _read_json_mapping(
        resolved_paths.get("organism", CAPTURE_CONTEXT_PATHS["organism"])
    )
    room_presence = _read_json_mapping(
        resolved_paths.get("room_presence", CAPTURE_CONTEXT_PATHS["room_presence"])
    )

    context: dict[str, Any] = {}
    if organism:
        context["organism"] = organism
    if room_presence:
        context["room_presence"] = room_presence
    return context


PEAK_NORMALIZE_TARGET_DBFS = -1.0
PEAK_NORMALIZE_FLOOR_DBFS = -30.0


def _peak_normalize(
    samples: npt.NDArray[np.float32],
    *,
    target_dbfs: float = PEAK_NORMALIZE_TARGET_DBFS,
    floor_dbfs: float = PEAK_NORMALIZE_FLOOR_DBFS,
) -> tuple[npt.NDArray[np.float32], float]:
    """Peak-normalize to ``target_dbfs`` unless peak is below ``floor_dbfs``.

    Returns ``(normalized_samples, gain_db)`` where ``gain_db`` is the
    adjustment that was applied (0.0 when raw is preserved).
    """
    if samples.size == 0:
        return samples, 0.0
    peak = float(np.max(np.abs(samples.astype(np.float64))))
    if peak <= 1e-12:
        return samples, 0.0
    peak_dbfs = 20.0 * math.log10(peak)
    if peak_dbfs < floor_dbfs:
        return samples, 0.0
    gain_db = target_dbfs - peak_dbfs
    scale = 10.0 ** (gain_db / 20.0)
    scaled = (samples.astype(np.float64) * scale).astype(np.float32)
    return scaled, gain_db


def _samples_to_pcm24le(samples: npt.NDArray[np.float32]) -> bytes:
    clipped = np.clip(samples.astype(np.float64), -1.0, 1.0)
    scaled = np.round(clipped * ((1 << 23) - 1)).astype(np.int32)
    payload = bytearray()
    for value in scaled:
        payload.extend(int(value).to_bytes(4, byteorder="little", signed=True)[:3])
    return bytes(payload)


def _write_capture_wav(path: Path, samples: npt.NDArray[np.float32], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(sample_rate)
        handle.writeframes(_samples_to_pcm24le(samples))


class SampleIndex:
    """SQLite-backed capture index storing emitted tag payloads."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / SAMPLE_INDEX_FILENAME
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    sample_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sample_rate INTEGER NOT NULL,
                    frame_count INTEGER NOT NULL,
                    captured_at_iso TEXT NOT NULL,
                    captured_at_unix REAL NOT NULL,
                    arc_phase TEXT NOT NULL,
                    mood_label TEXT NOT NULL,
                    mood_valence REAL NOT NULL,
                    mood_arousal REAL NOT NULL,
                    presence TEXT NOT NULL,
                    presence_confidence REAL NOT NULL,
                    someone_here INTEGER NOT NULL,
                    time_of_day TEXT NOT NULL,
                    acoustic_tags_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    gain_db REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_samples_source_captured_at
                ON samples(source, captured_at_unix DESC)
                """
            )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_samples_arc_phase
                ON samples(arc_phase)
                """
            )

    def insert(self, capture: SavedCapture) -> None:
        tags_payload = capture.tags.as_dict()
        acoustic_tags_json = json.dumps(tags_payload["acoustic_tags"])
        tags_json = json.dumps(tags_payload)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO samples (
                    sample_id,
                    source,
                    path,
                    sample_rate,
                    frame_count,
                    captured_at_iso,
                    captured_at_unix,
                    arc_phase,
                    mood_label,
                    mood_valence,
                    mood_arousal,
                    presence,
                    presence_confidence,
                    someone_here,
                    time_of_day,
                    acoustic_tags_json,
                    tags_json,
                    gain_db
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture.sample_id,
                    capture.source,
                    str(capture.path),
                    capture.sample_rate,
                    capture.frame_count,
                    capture.tags.captured_at_iso,
                    capture.tags.captured_at_unix,
                    capture.tags.arc_phase,
                    capture.tags.mood_label,
                    capture.tags.mood_valence,
                    capture.tags.mood_arousal,
                    capture.tags.presence,
                    capture.tags.presence_confidence,
                    int(capture.tags.someone_here),
                    capture.tags.time_of_day,
                    acoustic_tags_json,
                    tags_json,
                    capture.gain_db,
                ),
            )


def _coerce_mode(raw: object) -> str:
    if isinstance(raw, str):
        candidate = raw.strip().lower()
        if candidate:
            return candidate
    return "unknown"


def _normalize_extra_tags(
    raw: Mapping[str, Any] | tuple[tuple[str, str], ...] | None,
) -> tuple[tuple[str, str], ...]:
    if not raw:
        return ()
    items = raw.items() if isinstance(raw, Mapping) else raw
    return tuple((str(k), str(v)) for k, v in items)


def save_capture(
    samples: npt.ArrayLike,
    *,
    source: str,
    sample_rate: int,
    capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
    context: Mapping[str, Any] | None = None,
    captured_at: float | None = None,
    transient_threshold_db: float = 6.0,
    acoustic_thresholds: AcousticTagThresholds | None = None,
    mode: str | None = None,
    extra_tags: Mapping[str, Any] | tuple[tuple[str, str], ...] | None = None,
) -> SavedCapture:
    """Write a capture, emit auto-tags, and persist both into `index.sqlite`."""
    if source not in JACK_SOURCE_PORTS:
        raise ValueError(f"unknown capture source: {source}")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    capture_root_path = Path(capture_root)
    sample_array = np.asarray(samples, dtype=np.float32).reshape(-1)
    resolved_context = load_capture_context() if context is None else dict(context)
    tags = build_sample_tags(
        sample_array,
        sample_rate,
        context=resolved_context,
        captured_at=captured_at,
        transient_threshold_db=transient_threshold_db,
        acoustic_thresholds=acoustic_thresholds,
    )
    if mode is not None:
        tags = replace(tags, mode=_coerce_mode(mode))
    normalized_extras = _normalize_extra_tags(extra_tags)
    if normalized_extras:
        tags = replace(tags, extra_tags=normalized_extras)

    normalized_samples, gain_db = _peak_normalize(sample_array)

    sample_id = uuid.uuid4().hex
    captured_dt = datetime.fromtimestamp(tags.captured_at_unix, tz=timezone.utc)
    timestamp_slug = captured_dt.strftime("%Y%m%dT%H%M%SZ")
    arc_slug = tags.arc_phase or "unknown"
    wav_path = capture_root_path / source / f"{source}_{timestamp_slug}_{arc_slug}_{sample_id}.wav"
    _write_capture_wav(wav_path, normalized_samples, sample_rate)

    index = SampleIndex(capture_root_path)
    capture = SavedCapture(
        sample_id=sample_id,
        source=source,
        path=wav_path,
        tags=tags,
        sample_rate=sample_rate,
        frame_count=int(normalized_samples.size),
        index_path=index.path,
        gain_db=gain_db,
    )
    index.insert(capture)
    return capture


SELF_QUOTE_DURATION_SECONDS = 4.0
SELF_QUOTE_ARC_PAYOFF_THRESHOLD = 0.6
SELF_QUOTE_EXCLUDED_MODES: frozenset[str] = frozenset({"working_ambience"})
SELF_QUOTE_SOURCE = "self"


def _should_self_quote(score_summary: Mapping[str, Any]) -> bool:
    try:
        arc_payoff = float(score_summary.get("arc_payoff", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    try:
        click_count = int(score_summary.get("click_count", 0) or 0)
    except (TypeError, ValueError):
        return False
    mode = _coerce_mode(score_summary.get("mode"))
    if arc_payoff <= SELF_QUOTE_ARC_PAYOFF_THRESHOLD:
        return False
    if click_count != 0:
        return False
    if mode in SELF_QUOTE_EXCLUDED_MODES:
        return False
    return True


def self_quote(
    score_summary: Mapping[str, Any],
    *,
    daemon: "SampleCaptureDaemon | None" = None,
    capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
    captured_at: float | None = None,
    source: str = SELF_QUOTE_SOURCE,
) -> SavedCapture | None:
    """Capture a 4-second self-quotation when the song meets the trigger gate.

    Triggers when ``arc_payoff > 0.6`` AND ``click_count == 0`` AND
    ``mode != working_ambience``. Captures the 4-second window centered on
    the moment of peak rolling_peak in the daemon's ``self`` buffer.
    """
    if not _should_self_quote(score_summary):
        return None
    active_daemon = start_daemon() if daemon is None else daemon
    peak_offset_sec = active_daemon.peak_offset_seconds(source)
    half_window = SELF_QUOTE_DURATION_SECONDS / 2.0
    offset = max(0.0, peak_offset_sec - half_window)
    max_offset = max(0.0, active_daemon.buffer_duration_seconds - SELF_QUOTE_DURATION_SECONDS)
    offset = min(offset, max_offset)
    samples = active_daemon.get_window(source, SELF_QUOTE_DURATION_SECONDS, offset)
    extra_tags: dict[str, str] = {}
    song_id = score_summary.get("song_id") or score_summary.get("self_quote_source_song_id")
    if song_id is not None:
        extra_tags["self_quote_source_song_id"] = str(song_id)
    arc_phase = score_summary.get("arc_phase")
    mood = score_summary.get("mood")
    organism: dict[str, Any] = {}
    if arc_phase:
        organism["arc_phase"] = str(arc_phase)
    if mood:
        organism["mood"] = {"label": str(mood)}
    context = {"organism": organism} if organism else {}
    return save_capture(
        samples,
        source=source,
        sample_rate=active_daemon.sample_rate,
        capture_root=capture_root,
        context=context,
        captured_at=captured_at,
        mode=score_summary.get("mode"),
        extra_tags=extra_tags,
    )


_DEFAULT_DAEMON: SampleCaptureDaemon | None = None


def start_daemon() -> SampleCaptureDaemon:
    global _DEFAULT_DAEMON
    if _DEFAULT_DAEMON is None:
        daemon = SampleCaptureDaemon()
        daemon.start()
        _DEFAULT_DAEMON = daemon
    return _DEFAULT_DAEMON


def stop_daemon() -> None:
    global _DEFAULT_DAEMON
    if _DEFAULT_DAEMON is None:
        return
    _DEFAULT_DAEMON.stop()
    _DEFAULT_DAEMON = None


def get_window(source: str, duration_sec: float, offset_sec: float = 0.0) -> npt.NDArray[np.float32]:
    daemon = start_daemon()
    return daemon.get_window(source, duration_sec, offset_sec)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    
    # Ensure identity exists before anything that depends on it (Hardening)
    bootstrap_identity()

    stop_event = threading.Event()

    def _shutdown(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    start_daemon()
    LOGGER.info("sample capture daemon started")
    try:
        while not stop_event.is_set():
            time.sleep(1.0)
    finally:
        stop_daemon()


if __name__ == "__main__":
    main()
