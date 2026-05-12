#!/usr/bin/env python3
"""Guided capture harness for PromptClaw contact-mic calibration."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import wave
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Callable, Protocol, Sequence


DEFAULT_INTERFACE_LABEL = "Scarlett 4i4 USB"
DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_CHANNELS = 2
DEFAULT_ANALYSIS_WINDOW_SECONDS = 1.0
DEFAULT_OUTPUT_ROOT = Path("artifacts/contact-mic-calibration")
CHANNEL_LABELS = {
    1: "The Membrane",
    2: "The Heartbeat",
}


@dataclass(frozen=True, slots=True)
class CalibrationScenario:
    slug: str
    title: str
    duration_seconds: int
    instructions: tuple[str, ...]
    purpose: str


class CaptureBackend(Protocol):
    def capture(
        self,
        output_path: Path,
        *,
        duration_seconds: int,
        channels: int,
        sample_rate: int,
        device: str | None,
    ) -> None:
        """Capture audio into ``output_path`` as a 16-bit PCM WAV file."""


class CommandCaptureBackend:
    """Capture audio through the host command-line audio stack."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self._runner = runner
        self._which = which

    def capture(
        self,
        output_path: Path,
        *,
        duration_seconds: int,
        channels: int,
        sample_rate: int,
        device: str | None,
    ) -> None:
        arecord = self._which("arecord")
        if arecord:
            command = [
                arecord,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(sample_rate),
                "-c",
                str(channels),
                "-d",
                str(duration_seconds),
                "-t",
                "wav",
            ]
            if device:
                command.extend(["-D", device])
            command.append(str(output_path))
            self._runner(command, check=True, text=True, capture_output=True)
            return

        ffmpeg = self._which("ffmpeg")
        if ffmpeg:
            command = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "alsa",
                "-i",
                device or "default",
                "-ac",
                str(channels),
                "-ar",
                str(sample_rate),
                "-t",
                str(duration_seconds),
                str(output_path),
            ]
            self._runner(command, check=True, text=True, capture_output=True)
            return

        raise RuntimeError("No supported capture backend found. Install arecord or ffmpeg.")


def default_scenarios() -> list[CalibrationScenario]:
    return [
        CalibrationScenario(
            slug="quiet_ambient_180s",
            title="Quiet Ambient",
            duration_seconds=180,
            instructions=(
                "Leave the room and server in their normal idle state.",
                "Do not touch the window, case, or input devices during capture.",
            ),
            purpose="Establish the passive baseline and noise floor for both voices.",
        ),
        CalibrationScenario(
            slug="bass_environment_180s",
            title="Bass / Structural Excitation",
            duration_seconds=180,
            instructions=(
                "Play deep bass music in the room.",
                "Do not tap the sensors during capture.",
            ),
            purpose="Measure structural coupling into the window and case paths.",
        ),
        CalibrationScenario(
            slug="directed_events_60s",
            title="Directed Events",
            duration_seconds=60,
            instructions=(
                "0s-20s: tap or scratch only the window path.",
                "20s-40s: tap or scratch only the case path.",
                "40s-60s: remain still and silent.",
            ),
            purpose="Verify channel identity, transient strength, and cross-talk.",
        ),
        CalibrationScenario(
            slug="machine_load_180s",
            title="Machine Load Change",
            duration_seconds=180,
            instructions=(
                "0s-60s: idle baseline.",
                "60s-120s: apply a repeatable machine load.",
                "120s-180s: return to idle.",
            ),
            purpose="Measure how the case mic responds to machine-state changes.",
        ),
    ]


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_output_dir() -> Path:
    return DEFAULT_OUTPUT_ROOT / _timestamp_slug()


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def analyze_wav(path: Path, *, analysis_window_seconds: float = DEFAULT_ANALYSIS_WINDOW_SECONDS) -> dict[str, object]:
    with wave.open(str(path), "rb") as handle:
        if handle.getcomptype() != "NONE":
            raise ValueError(f"Compressed WAV is not supported: {handle.getcomptype()}")
        if handle.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM WAV files are supported.")

        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        total_frames = handle.getnframes()
        window_frames = max(1, int(sample_rate * analysis_window_seconds))
        rms_windows: dict[int, list[float]] = {channel: [] for channel in range(1, channels + 1)}
        peak_windows: dict[int, list[float]] = {channel: [] for channel in range(1, channels + 1)}

        while True:
            raw = handle.readframes(window_frames)
            if not raw:
                break
            samples = array("h")
            samples.frombytes(raw)
            if sys.byteorder == "big":
                samples.byteswap()

            sum_squares = [0.0] * channels
            max_abs = [0] * channels
            counts = [0] * channels

            for index, sample in enumerate(samples):
                channel_index = index % channels
                absolute = abs(int(sample))
                sum_squares[channel_index] += absolute * absolute
                if absolute > max_abs[channel_index]:
                    max_abs[channel_index] = absolute
                counts[channel_index] += 1

            for channel_index in range(channels):
                if counts[channel_index] == 0:
                    continue
                rms = math.sqrt(sum_squares[channel_index] / counts[channel_index]) / 32768.0
                peak = max_abs[channel_index] / 32768.0
                rms_windows[channel_index + 1].append(rms)
                peak_windows[channel_index + 1].append(peak)

    channel_metrics: dict[str, dict[str, object]] = {}
    for channel in range(1, channels + 1):
        rms_values = rms_windows[channel] or [0.0]
        peak_values = peak_windows[channel] or [0.0]
        median_rms = median(rms_values)
        p95_rms = _quantile(rms_values, 0.95)
        p99_rms = _quantile(rms_values, 0.99)
        median_peak = median(peak_values)
        max_peak = max(peak_values)
        active_windows = sum(1 for value in rms_values if value > (median_rms * 1.5) and value > 0.0)
        activation_ratio = p95_rms / max(median_rms, 1e-9)

        channel_metrics[str(channel)] = {
            "label": CHANNEL_LABELS.get(channel, f"Channel {channel}"),
            "median_rms": _round_metric(median_rms),
            "p95_rms": _round_metric(p95_rms),
            "p99_rms": _round_metric(p99_rms),
            "median_peak": _round_metric(median_peak),
            "max_peak": _round_metric(max_peak),
            "active_windows": active_windows,
            "activation_ratio": _round_metric(activation_ratio),
        }

    return {
        "capture_path": str(path),
        "channels": channels,
        "sample_rate": sample_rate,
        "duration_seconds": round(total_frames / sample_rate, 3) if sample_rate else 0.0,
        "analysis_window_seconds": analysis_window_seconds,
        "window_count": len(next(iter(rms_windows.values()), [])),
        "channel_metrics": channel_metrics,
    }


def parse_alsa_devices(listing: str) -> list[dict[str, object]]:
    devices: list[dict[str, object]] = []
    for line in listing.splitlines():
        line = line.strip()
        if not line.startswith("card "):
            continue
        try:
            prefix, remainder = line.split(":", 1)
            card = int(prefix.split()[1])
            before_device, device_part = remainder.split(", device ", 1)
            device = int(device_part.split(":", 1)[0])
        except (ValueError, IndexError):
            continue
        devices.append(
            {
                "card": card,
                "device": device,
                "hw": f"hw:{card},{device}",
                "line": line,
                "matches_default_interface": DEFAULT_INTERFACE_LABEL.lower() in line.lower(),
            }
        )
    return devices


def find_alsa_hw_device(listing: str, *, preferred_name: str = DEFAULT_INTERFACE_LABEL) -> str | None:
    preferred_lower = preferred_name.lower()
    for device in parse_alsa_devices(listing):
        if preferred_lower in str(device["line"]).lower():
            return str(device["hw"])
    return None


def list_capture_devices() -> dict[str, object]:
    arecord = shutil.which("arecord")
    if not arecord:
        return {"backend": None, "devices": [], "message": "arecord is not installed on this host."}
    result = subprocess.run([arecord, "-l"], check=True, capture_output=True, text=True)
    listing = result.stdout.strip()
    return {
        "backend": "arecord",
        "devices": parse_alsa_devices(listing),
        "raw": listing,
        "auto_selected": find_alsa_hw_device(listing),
    }


def auto_select_device() -> str | None:
    try:
        devices = list_capture_devices()
    except (OSError, subprocess.CalledProcessError):
        return None
    auto_selected = devices.get("auto_selected")
    if isinstance(auto_selected, str) and auto_selected:
        return auto_selected
    return None


def _default_wait_for_ready(scenario: CalibrationScenario) -> None:
    print(f"\n{scenario.title} ({scenario.duration_seconds}s)")
    print(f"Purpose: {scenario.purpose}")
    for instruction in scenario.instructions:
        print(f"- {instruction}")
    input("Press Enter when the scene is ready and capture should begin...")


def run_calibration(
    *,
    output_dir: Path,
    backend: CaptureBackend | None = None,
    scenarios: Sequence[CalibrationScenario] | None = None,
    device: str | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    analysis_window_seconds: float = DEFAULT_ANALYSIS_WINDOW_SECONDS,
    wait_for_ready: Callable[[CalibrationScenario], None] | None = None,
) -> dict[str, object]:
    selected_scenarios = list(scenarios or default_scenarios())
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = backend or CommandCaptureBackend()
    device = device or auto_select_device()
    wait_for_ready = wait_for_ready or _default_wait_for_ready

    scenario_reports: list[dict[str, object]] = []
    for scenario in selected_scenarios:
        wait_for_ready(scenario)
        capture_path = output_dir / f"{scenario.slug}.wav"
        backend.capture(
            capture_path,
            duration_seconds=scenario.duration_seconds,
            channels=channels,
            sample_rate=sample_rate,
            device=device,
        )
        analysis = analyze_wav(capture_path, analysis_window_seconds=analysis_window_seconds)
        report = {
            "slug": scenario.slug,
            "title": scenario.title,
            "purpose": scenario.purpose,
            "duration_seconds": scenario.duration_seconds,
            "instructions": list(scenario.instructions),
            "capture_path": str(capture_path),
            "analysis": analysis,
        }
        scenario_reports.append(report)
        (output_dir / f"{scenario.slug}.json").write_text(json.dumps(report, indent=2, sort_keys=True))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "sample_rate": sample_rate,
        "channels": channels,
        "analysis_window_seconds": analysis_window_seconds,
        "channel_labels": {str(channel): label for channel, label in CHANNEL_LABELS.items()},
        "scenarios": scenario_reports,
    }
    (output_dir / "summary.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PromptClaw contact-mic calibration captures.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_scenarios_parser = subparsers.add_parser("list-scenarios", help="List the built-in capture scenarios.")
    list_scenarios_parser.add_argument("--json", action="store_true")

    list_devices_parser = subparsers.add_parser("list-devices", help="List available ALSA capture devices.")
    list_devices_parser.add_argument("--json", action="store_true")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze an existing WAV capture.")
    analyze_parser.add_argument("capture", type=Path)
    analyze_parser.add_argument("--analysis-window", type=float, default=DEFAULT_ANALYSIS_WINDOW_SECONDS)
    analyze_parser.add_argument("--json", action="store_true")

    run_parser = subparsers.add_parser("run", help="Capture and analyze one or more calibration scenarios.")
    run_parser.add_argument(
        "--scenario",
        action="append",
        choices=[scenario.slug for scenario in default_scenarios()],
        help="Scenario slug to run. Repeat for multiple scenarios. Defaults to the full baseline set.",
    )
    run_parser.add_argument("--device", default=None, help="Explicit ALSA device, for example hw:0,0.")
    run_parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    run_parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    run_parser.add_argument("--analysis-window", type=float, default=DEFAULT_ANALYSIS_WINDOW_SECONDS)
    run_parser.add_argument("--output-dir", type=Path, default=None)
    run_parser.add_argument("--yes", action="store_true", help="Skip the interactive ready prompt.")
    run_parser.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.command == "list-scenarios":
        scenarios = [
            {
                "slug": scenario.slug,
                "title": scenario.title,
                "duration_seconds": scenario.duration_seconds,
                "purpose": scenario.purpose,
                "instructions": list(scenario.instructions),
            }
            for scenario in default_scenarios()
        ]
        if args.json:
            print(json.dumps({"scenarios": scenarios}, indent=2, sort_keys=True))
        else:
            for scenario in scenarios:
                print(f"{scenario['slug']} ({scenario['duration_seconds']}s)")
                print(f"  {scenario['purpose']}")
        return 0

    if args.command == "list-devices":
        payload = list_capture_devices()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            message = payload.get("message")
            if isinstance(message, str):
                print(message)
            for device in payload.get("devices", []):
                if not isinstance(device, dict):
                    continue
                marker = " [auto]" if device.get("hw") == payload.get("auto_selected") else ""
                print(f"{device['hw']}: {device['line']}{marker}")
        return 0

    if args.command == "analyze":
        report = analyze_wav(args.capture, analysis_window_seconds=args.analysis_window)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    selected = {scenario.slug: scenario for scenario in default_scenarios()}
    scenarios = [selected[slug] for slug in args.scenario] if args.scenario else list(selected.values())
    wait_for_ready = (lambda _scenario: None) if args.yes else _default_wait_for_ready
    output_dir = args.output_dir or default_output_dir()
    manifest = run_calibration(
        output_dir=output_dir,
        scenarios=scenarios,
        device=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels,
        analysis_window_seconds=args.analysis_window,
        wait_for_ready=wait_for_ready,
    )
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(f"Wrote calibration bundle to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
