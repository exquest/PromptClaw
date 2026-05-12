"""Self-listener v3 — peak-aware audio monitoring with click detection.

Captures short clips from SuperCollider output, tracks RMS/peak/pitch, and
logs sparse click/pop events with lightweight PipeWire and scsynth snapshots
for later correlation.
"""
from __future__ import annotations

import json
import math
import os
import socket
import struct
import subprocess
import sys
import time
import wave
import re

sys.path.insert(0, os.path.dirname(__file__))
from audio_analysis import detect_click_transients, detect_pitch_autocorrelation
from capture_alias import persist_capture_alias
from senseweave.dsp_scene_lab import AudioFeatureFrame, glyph_features_from_audio
from senseweave.sample_dsp_activity import build_sample_dsp_activity

STATE = "/tmp/self_listen.json"
CLIP = "/tmp/self_listen.wav"
SELF_CAPTURE = "/tmp/self_capture.wav"
ROOM_CAPTURE = "/tmp/room_capture.wav"
CLICK_LOG = "/tmp/self_listen_clicks.jsonl"
TRACKER_RUNTIME_STATE = "/tmp/tracker_runtime_state.json"
COMPOSER_STATE = "/tmp/composer_state.json"
CADENCE_STATE = "/tmp/cadence_state.json"
GLYPH_AUDIO_FEATURES = "/tmp/glyph_audio_features.json"
SAMPLE_DSP_ACTIVITY = "/tmp/sample_dsp_activity.json"

CAPTURE_PORT = os.environ.get("SELF_LISTENER_PORT", "SuperCollider:out_1")
CAPTURE_DURATION = os.environ.get("SELF_LISTENER_CAPTURE_DURATION", "1")
CAPTURE_BACKEND = os.environ.get("SELF_LISTENER_CAPTURE_BACKEND", "auto").strip().lower()
PIPEWIRE_CAPTURE_TARGET = os.environ.get("SELF_LISTENER_PIPEWIRE_TARGET", "").strip()
DIRECT_JACK_PROBE_TIMEOUT_SECONDS = float(
    os.environ.get("SELF_LISTENER_DIRECT_JACK_PROBE_TIMEOUT_SECONDS", "8")
)
JACK_BACKEND_RECHECK_SECONDS = float(
    os.environ.get("SELF_LISTENER_JACK_RECHECK_SECONDS", "30")
)
SLEEP_BETWEEN = float(os.environ.get("SELF_LISTENER_SLEEP_SECONDS", "2"))
ROLLING_WINDOW = int(os.environ.get("SELF_LISTENER_ROLLING_WINDOW", "5"))
PIPEWIRE_RESYNC_WINDOW_SECONDS = int(
    os.environ.get("SELF_LISTENER_RESYNC_WINDOW_SECONDS", "30")
)
MAX_CLICK_EVENTS = int(os.environ.get("SELF_LISTENER_MAX_CLICK_EVENTS", "8"))
MAX_PIPEWIRE_LINES = int(os.environ.get("SELF_LISTENER_MAX_PIPEWIRE_LINES", "5"))
CLICK_EDGE_GUARD_MS = float(os.environ.get("SELF_LISTENER_CLICK_EDGE_GUARD_MS", "50"))
TRACKER_RUNTIME_WINDOW_SECONDS = int(
    os.environ.get("SELF_LISTENER_TRACKER_WINDOW_SECONDS", "10")
)
ROOM_CAPTURE_MAX_AGE_SECONDS = float(
    os.environ.get("SELF_LISTENER_ROOM_CAPTURE_MAX_AGE_SECONDS", "20")
)
_CAPTURE_BACKEND_CACHE: dict[str, float | str | None] = {"backend": None, "timestamp": 0.0}
PIPEWIRE_SINK_TARGET_RE = re.compile(r"(?P<default>\*)?\s*(?P<id>\d+)\.\s+(?P<name>.+?)\s+\[")


def _round(value: float | int, digits: int = 6) -> float:
    return round(float(value), digits)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def analyze_wav(path: str) -> dict:
    """Analyze a WAV file and return the decoded mono samples plus metrics."""
    try:
        with wave.open(path) as wav_file:
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            channels = wav_file.getnchannels()
            raw = wav_file.readframes(frame_count)

        fmt = f"<{frame_count * channels}h"
        if len(raw) < struct.calcsize(fmt):
            return {
                "sample_rate": 0,
                "mono": [],
                "rms": 0.0,
                "peak": 0.0,
                "pitch_hz": 0.0,
                "pitch_confidence": 0.0,
            }

        samples = list(struct.unpack(fmt, raw[: struct.calcsize(fmt)]))
        mono = [samples[i] for i in range(0, len(samples), channels)]
        if not mono:
            return {
                "sample_rate": sample_rate,
                "mono": [],
                "rms": 0.0,
                "peak": 0.0,
                "pitch_hz": 0.0,
                "pitch_confidence": 0.0,
            }

        norm = [sample / 32768.0 for sample in mono]
        rms = math.sqrt(sum(sample * sample for sample in norm) / len(norm))
        peak = max(abs(sample) for sample in norm)
        pitch_hz, pitch_confidence = 0.0, 0.0
        spectral_centroid_hz = estimate_spectral_centroid_hz(mono, sample_rate)
        onset_rate_hz = estimate_onset_rate_hz(mono, sample_rate)
        if rms > 0.005:
            try:
                pitch_hz, pitch_confidence = detect_pitch_autocorrelation(mono, sample_rate)
            except Exception:
                pitch_hz, pitch_confidence = 0.0, 0.0

        return {
            "sample_rate": sample_rate,
            "mono": mono,
            "rms": rms,
            "peak": peak,
            "pitch_hz": float(pitch_hz or 0.0),
            "pitch_confidence": float(pitch_confidence or 0.0),
            "spectral_centroid_hz": float(spectral_centroid_hz or 0.0),
            "onset_rate_hz": float(onset_rate_hz or 0.0),
        }
    except Exception:
        return {
            "sample_rate": 0,
            "mono": [],
            "rms": 0.0,
            "peak": 0.0,
            "pitch_hz": 0.0,
            "pitch_confidence": 0.0,
            "spectral_centroid_hz": 0.0,
            "onset_rate_hz": 0.0,
        }


def estimate_spectral_centroid_hz(samples: list[int], sample_rate: int) -> float:
    """Cheap brightness estimate from zero-crossing density."""
    if sample_rate <= 0 or len(samples) < 2:
        return 0.0
    crossings = 0
    prev = samples[0]
    for sample in samples[1:]:
        if (prev < 0 <= sample) or (prev > 0 >= sample):
            crossings += 1
        prev = sample
    if crossings <= 0:
        return 0.0
    return min(sample_rate / 4.0, (crossings * sample_rate) / (2.0 * len(samples)))


def estimate_onset_rate_hz(samples: list[int], sample_rate: int) -> float:
    """Approximate onset density from short-frame energy rises."""
    if sample_rate <= 0 or len(samples) < 512:
        return 0.0
    frame_size = 256
    hop_size = 128
    energies: list[float] = []
    for start in range(0, max(1, len(samples) - frame_size + 1), hop_size):
        frame = samples[start : start + frame_size]
        if not frame:
            continue
        energy = sum(abs(sample) for sample in frame) / (len(frame) * 32768.0)
        energies.append(energy)
    if len(energies) < 2:
        return 0.0
    mean_energy = sum(energies) / len(energies)
    threshold = max(0.01, mean_energy * 1.35)
    onsets = 0
    previous = energies[0]
    for energy in energies[1:]:
        if energy >= threshold and previous < threshold and energy > (previous * 1.1):
            onsets += 1
        previous = energy
    duration_s = len(samples) / float(sample_rate)
    if duration_s <= 0.0:
        return 0.0
    return onsets / duration_s


def _pad_osc_string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\0"
    return raw + (b"\0" * ((4 - (len(raw) % 4)) % 4))


def _parse_osc_string(payload: bytes, offset: int) -> tuple[str, int]:
    end = payload.index(0, offset)
    text = payload[offset:end].decode("utf-8")
    return text, (end + 4) & ~0x03


def query_scsynth_status() -> dict:
    """Query scsynth /status.reply without third-party OSC dependencies."""
    try:
        message = _pad_osc_string("/status") + _pad_osc_string(",")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.25)
            sock.sendto(message, ("127.0.0.1", 57110))
            payload, _ = sock.recvfrom(4096)

        _, offset = _parse_osc_string(payload, 0)
        tags, offset = _parse_osc_string(payload, offset)
        values: list[float | int] = []
        for tag in tags[1:]:
            if tag == "i":
                values.append(struct.unpack(">i", payload[offset : offset + 4])[0])
                offset += 4
            elif tag == "f":
                values.append(struct.unpack(">f", payload[offset : offset + 4])[0])
                offset += 4
            elif tag == "d":
                values.append(struct.unpack(">d", payload[offset : offset + 8])[0])
                offset += 8

        if len(values) < 9:
            return {"error": "short_status_reply"}

        return {
            "ugen_count": int(values[1]),
            "synth_count": int(values[2]),
            "group_count": int(values[3]),
            "synthdef_count": int(values[4]),
            "avg_cpu": _round(values[5], 3),
            "peak_cpu": _round(values[6], 3),
            "nominal_sample_rate": _round(values[7], 3),
            "actual_sample_rate": _round(values[8], 3),
        }
    except Exception as exc:
        return {"error": str(exc)[:120]}


def recent_pipewire_resyncs(window_seconds: int = PIPEWIRE_RESYNC_WINDOW_SECONDS) -> list[str]:
    """Return recent PipeWire resync/xrun-like log lines."""
    try:
        completed = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "pipewire",
                "--since",
                f"{window_seconds} seconds ago",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []

    matches = []
    for line in completed.stdout.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("resync", "xrun", "underrun", "overrun")):
            matches.append(line.strip())
    return matches[-MAX_PIPEWIRE_LINES:]


def read_tracker_runtime_state(
    *,
    now: float | None = None,
    window_seconds: int = TRACKER_RUNTIME_WINDOW_SECONDS,
) -> dict:
    """Read the latest tracker scheduler state if it is fresh."""
    try:
        current = time.time() if now is None else now
        with open(TRACKER_RUNTIME_STATE, encoding="utf-8") as handle:
            state = json.load(handle)
        if current - float(state.get("timestamp", 0.0)) > window_seconds:
            return {}
        return state
    except Exception:
        return {}


def read_json_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _capture_meta(path: str, *, now: float) -> dict:
    if not os.path.exists(path):
        return {"exists": False, "age_seconds": None}
    try:
        return {"exists": True, "age_seconds": max(0.0, now - os.path.getmtime(path))}
    except OSError:
        return {"exists": False, "age_seconds": None}


def _mean_range(values: object) -> float:
    if isinstance(values, (list, tuple)) and len(values) == 2:
        try:
            return (float(values[0]) + float(values[1])) / 2.0
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _string_list(values: object) -> list[str]:
    if isinstance(values, (list, tuple)):
        return [str(value) for value in values]
    return []


def _capture_registry(now: float) -> dict[str, dict[str, float | bool | None | str]]:
    paths = {
        "room_mic": "/tmp/room_capture.wav",
        "garden_mic": "/tmp/garden_capture.wav",
        "contact_mic": "/tmp/contact_capture.wav",
        "theramini_in": "/tmp/theramini_capture.wav",
        "self_bus": SELF_CAPTURE,
    }
    registry: dict[str, dict[str, float | bool | None | str]] = {}
    for source_name, path in paths.items():
        meta = _capture_meta(path, now=now)
        meta["path"] = path
        registry[source_name] = meta
    return registry


def _capture_env() -> dict[str, str]:
    env = os.environ.copy()
    env["JACK_NO_START_SERVER"] = "1"
    return env


def _command_timeout(command: list[str]) -> float:
    if command[:1] == ["jack_lsp"]:
        return DIRECT_JACK_PROBE_TIMEOUT_SECONDS
    return 2.0


def _decode_timeout_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="ignore")
    return output


def resolve_pipewire_monitor_target(status: str | None = None) -> str | None:
    if PIPEWIRE_CAPTURE_TARGET:
        return PIPEWIRE_CAPTURE_TARGET
    if status is None:
        try:
            completed = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            status = completed.stdout
        except Exception:
            return None

    in_sinks = False
    fallback_target: str | None = None
    for raw_line in status.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("├─ Sinks:") or stripped.startswith("└─ Sinks:"):
            in_sinks = True
            continue
        if in_sinks and stripped.startswith("├─") and "Sinks:" not in stripped:
            break
        if not in_sinks:
            continue
        match = PIPEWIRE_SINK_TARGET_RE.search(stripped)
        if not match:
            continue
        target_id = match.group("id")
        target_name = match.group("name").strip()
        if fallback_target is None and "jack sink" in target_name.lower():
            fallback_target = target_id
        if match.group("default"):
            return target_id
    return fallback_target


def _list_capture_ports(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_command_timeout(command),
            check=False,
            env=_capture_env(),
        )
    except subprocess.TimeoutExpired as exc:
        return _decode_timeout_output(exc.stdout)
    except Exception:
        return ""
    if completed.returncode != 0 and not completed.stdout:
        return ""
    return completed.stdout


def _cache_capture_backend(backend: str, *, now: float | None = None) -> str:
    _CAPTURE_BACKEND_CACHE["backend"] = backend
    _CAPTURE_BACKEND_CACHE["timestamp"] = time.time() if now is None else now
    return backend


def reset_capture_backend_cache() -> None:
    _CAPTURE_BACKEND_CACHE["backend"] = None
    _CAPTURE_BACKEND_CACHE["timestamp"] = 0.0


def select_capture_backend(capture_port: str = CAPTURE_PORT, *, now: float | None = None) -> str:
    forced = CAPTURE_BACKEND
    if forced in {"jack", "pw-jack", "pipewire"}:
        return forced

    current_time = time.time() if now is None else now
    cached_backend = _CAPTURE_BACKEND_CACHE.get("backend")
    cached_at = float(_CAPTURE_BACKEND_CACHE.get("timestamp", 0.0) or 0.0)
    if cached_backend == "jack":
        return "jack"
    if cached_backend == "pw-jack" and (current_time - cached_at) < JACK_BACKEND_RECHECK_SECONDS:
        return "pw-jack"

    if resolve_pipewire_monitor_target():
        return _cache_capture_backend("pipewire", now=current_time)
    if capture_port in _list_capture_ports(["jack_lsp"]):
        return _cache_capture_backend("jack", now=current_time)
    if capture_port in _list_capture_ports(["pw-jack", "jack_lsp"]):
        return _cache_capture_backend("pw-jack", now=current_time)
    return _cache_capture_backend("pw-jack", now=current_time)


def build_capture_command(capture_port: str = CAPTURE_PORT) -> tuple[list[str], dict[str, str], str]:
    backend = select_capture_backend(capture_port)
    if backend == "pipewire":
        target = resolve_pipewire_monitor_target()
        if target:
            return [
                "timeout",
                str(int(float(CAPTURE_DURATION)) + 1),
                "pw-record",
                "--target",
                target,
                "--channels",
                "1",
                "--rate",
                "16000",
                "--format",
                "s16",
                CLIP,
            ], os.environ.copy(), backend
    recorder = ["jack_rec", "-f", CLIP, "-d", CAPTURE_DURATION, "-b", "16", capture_port]
    if backend == "jack":
        return recorder, _capture_env(), backend
    return ["pw-jack"] + recorder, _capture_env(), backend


def run_capture_once(capture_cmd: list[str], capture_env: dict[str, str]) -> bool:
    try:
        if os.path.exists(CLIP):
            os.remove(CLIP)
    except OSError:
        pass

    try:
        subprocess.run(
            capture_cmd,
            timeout=max(5, int(float(CAPTURE_DURATION)) + 4),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=capture_env,
        )
        return True
    except subprocess.TimeoutExpired:
        return False


def load_fallback_capture(now: float | None = None) -> tuple[dict | None, str | None]:
    """Return a recent room capture when direct self-capture is unavailable."""
    current_time = time.time() if now is None else now
    try:
        if not os.path.exists(ROOM_CAPTURE) or os.path.getsize(ROOM_CAPTURE) <= 500:
            return None, None
        age_seconds = current_time - os.path.getmtime(ROOM_CAPTURE)
        if age_seconds > ROOM_CAPTURE_MAX_AGE_SECONDS:
            return None, None
    except OSError:
        return None, None

    analysis = analyze_wav(ROOM_CAPTURE)
    if analysis.get("sample_rate", 0) <= 0 or not analysis.get("mono"):
        return None, None
    return analysis, "room_capture"


def append_click_event(timestamp: float, click_info: dict) -> None:
    """Append a single JSONL click event with runtime context."""
    tracker_runtime = read_tracker_runtime_state(now=timestamp)
    event = {
        "timestamp": _round(timestamp, 3),
        "capture_port": CAPTURE_PORT,
        "click_count": click_info["count"],
        "click_times_ms": [
            round(event["time_seconds"] * 1000.0, 3)
            for event in click_info["events"][:MAX_CLICK_EVENTS]
        ],
        "click_max_residual": _round(click_info["max_residual"], 6),
        "click_max_ratio": _round(click_info["max_ratio"], 3),
        "scsynth_status": query_scsynth_status(),
        "pipewire_resyncs": recent_pipewire_resyncs(),
        "system_loadavg": [round(value, 3) for value in os.getloadavg()],
        "tracker_runtime": tracker_runtime,
    }
    with open(CLICK_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def build_glyph_audio_state(
    timestamp: float,
    analysis: dict,
    click_info: dict,
    *,
    composer_state: dict | None = None,
    cadence_state: dict | None = None,
) -> dict:
    composer = read_json_state(COMPOSER_STATE) if composer_state is None else composer_state
    _cadence = read_json_state(CADENCE_STATE) if cadence_state is None else cadence_state
    amplitude = _clamp(float(analysis.get("rms", 0.0) or 0.0) * 12.0, 0.0, 1.0)
    is_playing = amplitude > 0.01
    centroid = float(analysis.get("spectral_centroid_hz", 0.0) or 0.0) if is_playing else 0.0
    onset_rate = float(analysis.get("onset_rate_hz", 0.0) or 0.0) if is_playing else 0.0
    pitch_confidence = float(analysis.get("pitch_confidence", 0.0) or 0.0)
    if is_playing:
        flatness = _clamp(0.18 + (1.0 - pitch_confidence) * 0.72, 0.0, 1.0)
    else:
        flatness = 0.0
    visual_bias = composer.get("glyph_visual_bias", {})
    if not isinstance(visual_bias, dict):
        visual_bias = {}
    base = glyph_features_from_audio(
        AudioFeatureFrame(
            amplitude=amplitude,
            spectral_centroid_hz=centroid,
            spectral_flatness=flatness,
            onset_rate_hz=onset_rate,
        )
    )
    if is_playing and visual_bias:
        for key in ("brightness", "motion", "texture", "density", "salience"):
            bias_value = visual_bias.get(key)
            if isinstance(bias_value, (int, float)) and key in base:
                base[key] = round(
                    _clamp(base[key] * 0.72 + float(bias_value) * 0.28, 0.0, 1.0),
                    3,
                )
    if not is_playing:
        base["motion"] = 0.0
        base["density"] = 0.0

    combined_blocks = _string_list(base.get("dsp_blocks", []))
    if not combined_blocks:
        combined_blocks = _string_list(composer.get("dsp_blocks", []))

    return {
        "timestamp": _round(timestamp, 3),
        "brightness": base["brightness"],
        "motion": base["motion"],
        "texture": base["texture"],
        "density": base["density"],
        "salience": base.get("salience", 0.0),
        "dsp_blocks": combined_blocks,
        "mapping_hints": base.get("mapping_hints", {}),
        "gestures": base.get("gestures", []),
        "visual_bias": dict(visual_bias),
        "arc_phase": str(composer.get("arc_phase", "")),
        "arc_transition_intent": str(composer.get("arc_transition_intent", "")),
        "sample_source": str(composer.get("sample_source", "")),
        "sample_transforms": _string_list(composer.get("sample_transforms", [])),
        "sample_density": float(composer.get("sample_density", 0.0) or 0.0),
        "dsp_source_focus": str(composer.get("dsp_source_focus", "")),
        "artistic_identity": str(composer.get("artistic_identity", "")),
        "pitch_hz": round(float(analysis.get("pitch_hz", 0.0) or 0.0), 1),
        "pitch_confidence": round(pitch_confidence, 3),
        "spectral_centroid_hz": round(centroid, 1),
        "onset_rate_hz": round(onset_rate, 3),
        "rms": _round(analysis.get("rms", 0.0) or 0.0),
        "peak": _round(analysis.get("peak", 0.0) or 0.0),
        "click_count": int(click_info.get("count", 0) or 0),
    }


def build_state(
    timestamp: float,
    analysis: dict,
    rolling_peak: float,
    click_info: dict,
    *,
    capture_backend: str,
) -> dict:
    """Build the externally visible self-listener state payload."""
    events = click_info["events"][:MAX_CLICK_EVENTS]
    tracker_runtime = read_tracker_runtime_state(now=timestamp)
    return {
        "timestamp": timestamp,
        "rms": _round(analysis["rms"]),
        "peak": _round(analysis["peak"]),
        "rolling_peak": _round(rolling_peak),
        "amplitude": _round(analysis["rms"]),  # backwards compat
        "pitch_hz": round(analysis["pitch_hz"], 1),
        "pitch_confidence": round(analysis["pitch_confidence"], 3),
        "spectral_centroid_hz": _round(analysis.get("spectral_centroid_hz", 0.0) or 0.0, 1),
        "onset_rate_hz": _round(analysis.get("onset_rate_hz", 0.0) or 0.0, 3),
        "is_playing": analysis["rms"] > 0.003,
        "is_silent": analysis["rms"] < 0.001,
        "capture_port": CAPTURE_PORT,
        "capture_backend": capture_backend,
        "has_clicks": click_info["count"] > 0,
        "click_count": click_info["count"],
        "click_times_ms": [round(event["time_seconds"] * 1000.0, 3) for event in events],
        "click_max_residual": _round(click_info["max_residual"]),
        "click_max_ratio": _round(click_info["max_ratio"], 3),
        "clicks_suppressed_as_periodic": click_info["suppressed_as_periodic"],
        "tracker_scene_name": tracker_runtime.get("scene_name", ""),
        "tracker_row": tracker_runtime.get("row", -1),
        "tracker_rows_per_beat": tracker_runtime.get("rows_per_beat", 0),
        "tracker_total_rows": tracker_runtime.get("total_rows", 0),
        "tracker_tempo_bpm": tracker_runtime.get("tempo_bpm", 0.0),
        "tracker_scene_metadata": tracker_runtime.get("scene_metadata", {}),
    }


def write_state(state: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(tmp, STATE)


def write_glyph_audio_state(state: dict) -> None:
    tmp = GLYPH_AUDIO_FEATURES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(tmp, GLYPH_AUDIO_FEATURES)


def write_sample_dsp_activity(state: dict) -> None:
    tmp = SAMPLE_DSP_ACTIVITY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(tmp, SAMPLE_DSP_ACTIVITY)


def detect_clicks_for_listener(samples: list[int], sample_rate: int) -> dict:
    """Detect clicks while ignoring capture-edge artifacts from short jack_rec runs."""
    edge_guard_samples = int(sample_rate * CLICK_EDGE_GUARD_MS / 1000.0)
    if edge_guard_samples > 0 and (edge_guard_samples * 2) < len(samples):
        offset = edge_guard_samples
        trimmed = samples[offset : len(samples) - edge_guard_samples]
    else:
        offset = 0
        trimmed = samples

    click_info = detect_click_transients(trimmed, sample_rate)
    if offset and click_info["events"]:
        time_offset = offset / sample_rate
        for event in click_info["events"]:
            event["sample_index"] += offset
            event["time_seconds"] += time_offset
    return click_info


def main() -> None:
    rolling_peaks: list[float] = []
    while True:
        try:
            capture_cmd, capture_env, capture_backend = build_capture_command(CAPTURE_PORT)
            capture_ok = run_capture_once(capture_cmd, capture_env)
            now = time.time()

            if capture_ok and os.path.exists(CLIP) and os.path.getsize(CLIP) > 500:
                analysis = analyze_wav(CLIP)
                persist_capture_alias(CLIP, SELF_CAPTURE)
                click_info = detect_clicks_for_listener(
                    analysis["mono"],
                    analysis["sample_rate"],
                )
                rolling_peaks.append(analysis["peak"])
                if len(rolling_peaks) > ROLLING_WINDOW:
                    rolling_peaks.pop(0)
                state = build_state(
                    now,
                    analysis,
                    max(rolling_peaks) if rolling_peaks else 0.0,
                    click_info,
                    capture_backend=capture_backend,
                )
                if click_info["count"] > 0:
                    append_click_event(state["timestamp"], click_info)
            else:
                fallback_analysis, fallback_backend = load_fallback_capture(now=now)
                if fallback_analysis is not None and fallback_backend is not None:
                    analysis = fallback_analysis
                    click_info = detect_clicks_for_listener(
                        analysis["mono"],
                        analysis["sample_rate"],
                    )
                    rolling_peaks.append(analysis["peak"])
                    if len(rolling_peaks) > ROLLING_WINDOW:
                        rolling_peaks.pop(0)
                    state = build_state(
                        now,
                        analysis,
                        max(rolling_peaks) if rolling_peaks else 0.0,
                        click_info,
                        capture_backend=fallback_backend,
                    )
                else:
                    analysis = {
                        "rms": 0.0,
                        "peak": 0.0,
                        "pitch_hz": 0.0,
                        "pitch_confidence": 0.0,
                        "spectral_centroid_hz": 0.0,
                        "onset_rate_hz": 0.0,
                    }
                    click_info = {"count": 0}
                    state = {
                        "timestamp": now,
                        "rms": 0,
                        "peak": 0,
                        "rolling_peak": 0,
                        "amplitude": 0,
                        "pitch_hz": 0,
                        "pitch_confidence": 0,
                        "is_playing": False,
                        "is_silent": True,
                        "capture_port": CAPTURE_PORT,
                        "capture_backend": capture_backend,
                        "has_clicks": False,
                        "click_count": 0,
                        "click_times_ms": [],
                        "click_max_residual": 0,
                        "click_max_ratio": 0,
                        "clicks_suppressed_as_periodic": False,
                        "tracker_scene_name": "",
                        "tracker_row": -1,
                        "error": "no_capture" if capture_ok else "capture_timeout",
                    }
                    reset_capture_backend_cache()

            write_state(state)
            now = state["timestamp"]
            composer_state = read_json_state(COMPOSER_STATE)
            cadence_state = read_json_state(CADENCE_STATE)
            write_glyph_audio_state(
                build_glyph_audio_state(
                    now,
                    analysis,
                    click_info,
                    composer_state=composer_state,
                    cadence_state=cadence_state,
                )
            )
            write_sample_dsp_activity(
                build_sample_dsp_activity(
                    timestamp=now,
                    composer_state=composer_state,
                    cadence_state=cadence_state,
                    self_state=state,
                    sensor_states={
                        "room_activity": read_json_state("/tmp/room_activity.json"),
                        "room_speech": read_json_state("/tmp/room_speech.json"),
                        "theramini": read_json_state("/tmp/theramini_state.json"),
                    },
                    capture_meta=_capture_meta(
                        str(composer_state.get("sample_capture_path", "")),
                        now=now,
                    ),
                    capture_registry=_capture_registry(now),
                )
            )
        except Exception:
            pass

        time.sleep(SLEEP_BETWEEN)


if __name__ == "__main__":
    main()
