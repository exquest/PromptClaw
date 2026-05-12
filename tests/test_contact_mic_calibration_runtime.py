"""Tests for the contact mic calibration harness."""

from __future__ import annotations

import json
import math
import pytest
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import contact_mic_calibration


def _write_wav(
    path: Path,
    *,
    channels: int,
    sample_rate: int,
    frames: list[tuple[int, ...]],
) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = b"".join(struct.pack("<" + ("h" * channels), *frame) for frame in frames)
        handle.writeframes(payload)


def test_required_scenarios_match_protocol_defaults() -> None:
    scenarios = {scenario.slug: scenario for scenario in contact_mic_calibration.default_scenarios()}

    assert list(scenarios) == [
        "quiet_ambient_180s",
        "bass_environment_180s",
        "directed_events_60s",
        "machine_load_180s",
    ]
    assert scenarios["quiet_ambient_180s"].duration_seconds == 180
    assert scenarios["bass_environment_180s"].duration_seconds == 180
    assert scenarios["directed_events_60s"].duration_seconds == 60
    assert scenarios["machine_load_180s"].duration_seconds == 180


def test_analyze_wav_reports_channel_metrics_and_activity(tmp_path: Path) -> None:
    capture = tmp_path / "capture.wav"
    sample_rate = 10
    frames: list[tuple[int, int]] = []

    frames.extend((0, 2000) for _ in range(sample_rate))
    frames.extend((12000, 2000) for _ in range(sample_rate))
    frames.extend((0, 2000) for _ in range(sample_rate))

    _write_wav(capture, channels=2, sample_rate=sample_rate, frames=frames)

    report = contact_mic_calibration.analyze_wav(capture, analysis_window_seconds=1.0)

    assert report["channels"] == 2
    assert report["sample_rate"] == sample_rate
    assert report["duration_seconds"] == 3.0

    membrane = report["channel_metrics"]["1"]
    heartbeat = report["channel_metrics"]["2"]

    assert membrane["label"] == "The Membrane"
    assert membrane["active_windows"] == 1
    assert membrane["max_peak"] > heartbeat["max_peak"]
    assert membrane["p95_rms"] > membrane["median_rms"]

    assert heartbeat["label"] == "The Heartbeat"
    assert heartbeat["active_windows"] == 0
    assert math.isclose(heartbeat["median_peak"], heartbeat["max_peak"], rel_tol=1e-6)


def test_run_calibration_writes_summary_bundle(tmp_path: Path) -> None:
    class FakeBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, int]] = []

        def capture(
            self,
            output_path: Path,
            *,
            duration_seconds: int,
            channels: int,
            sample_rate: int,
            device: str | None,
        ) -> None:
            self.calls.append((output_path, duration_seconds))
            frames = [(0, 1000)] * sample_rate
            _write_wav(output_path, channels=channels, sample_rate=sample_rate, frames=frames)

    backend = FakeBackend()
    output_dir = tmp_path / "calibration"
    scenarios = [
        contact_mic_calibration.CalibrationScenario(
            slug="quiet_ambient_180s",
            title="Quiet Ambient",
            duration_seconds=1,
            instructions=("Stay still.",),
            purpose="Baseline.",
        ),
        contact_mic_calibration.CalibrationScenario(
            slug="directed_events_60s",
            title="Directed Events",
            duration_seconds=1,
            instructions=("Tap the window.",),
            purpose="Identity check.",
        ),
    ]

    manifest = contact_mic_calibration.run_calibration(
        output_dir=output_dir,
        backend=backend,
        scenarios=scenarios,
        device="hw:0,0",
        sample_rate=10,
        channels=2,
        analysis_window_seconds=1.0,
        wait_for_ready=lambda _scenario: None,
    )

    assert [call[1] for call in backend.calls] == [1, 1]
    assert (output_dir / "quiet_ambient_180s.wav").exists()
    assert (output_dir / "directed_events_60s.wav").exists()
    assert (output_dir / "summary.json").exists()
    assert manifest["device"] == "hw:0,0"
    assert [entry["slug"] for entry in manifest["scenarios"]] == [
        "quiet_ambient_180s",
        "directed_events_60s",
    ]

    summary = json.loads((output_dir / "summary.json").read_text())
    assert summary["channel_labels"] == {"1": "The Membrane", "2": "The Heartbeat"}
    assert summary["scenarios"][0]["analysis"]["channel_metrics"]["2"]["median_rms"] > 0


def test_parse_arecord_device_lines_finds_scarlett_address() -> None:
    listing = """
card 0: USB [Scarlett 4i4 USB], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: PCH [HDA Intel PCH], device 0: ALC245 Analog [ALC245 Analog]
""".strip()

    assert contact_mic_calibration.find_alsa_hw_device(listing, preferred_name="Scarlett 4i4 USB") == "hw:0,0"


class ContactMicCalibrationEndToEndTests:
    """Hardware-free coverage for the public calibration harness path."""

    __test__ = True

    def test_analysis_report_is_json_safe_and_identifies_channel_dynamics(
        self,
        tmp_path: Path,
    ) -> None:
        capture = tmp_path / "dynamics.wav"
        sample_rate = 20
        window_levels = [
            (1000, 400),
            (1000, 4000),
            (9000, 400),
            (1000, 400),
        ]
        frames: list[tuple[int, int]] = []
        for level in window_levels:
            frames.extend(level for _ in range(sample_rate))

        _write_wav(capture, channels=2, sample_rate=sample_rate, frames=frames)

        report = contact_mic_calibration.analyze_wav(
            capture,
            analysis_window_seconds=1.0,
        )
        encoded = json.dumps(report, sort_keys=True)
        decoded = json.loads(encoded)
        membrane = decoded["channel_metrics"]["1"]
        heartbeat = decoded["channel_metrics"]["2"]

        assert decoded["capture_path"] == str(capture)
        assert decoded["duration_seconds"] == 4.0
        assert decoded["window_count"] == 4
        assert set(decoded["channel_metrics"]) == {"1", "2"}
        assert membrane["label"] == "The Membrane"
        assert heartbeat["label"] == "The Heartbeat"
        assert membrane["active_windows"] == 1
        assert heartbeat["active_windows"] == 1
        assert membrane["activation_ratio"] > 1.0
        assert heartbeat["activation_ratio"] > 1.0
        assert membrane["max_peak"] > heartbeat["median_peak"]

    def test_run_calibration_bundle_persists_manifest_reports_and_captures(
        self,
        tmp_path: Path,
    ) -> None:
        class FakeBackend:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def capture(
                self,
                output_path: Path,
                *,
                duration_seconds: int,
                channels: int,
                sample_rate: int,
                device: str | None,
            ) -> None:
                self.calls.append(
                    {
                        "path": output_path,
                        "duration_seconds": duration_seconds,
                        "channels": channels,
                        "sample_rate": sample_rate,
                        "device": device,
                    }
                )
                if output_path.stem == "quiet_ambient_180s":
                    frame = (1000, 3000)
                else:
                    frame = (7000, 2000)
                frames = [frame] * (duration_seconds * sample_rate)
                _write_wav(
                    output_path,
                    channels=channels,
                    sample_rate=sample_rate,
                    frames=frames,
                )

        scenarios = [
            contact_mic_calibration.CalibrationScenario(
                slug="quiet_ambient_180s",
                title="Quiet Ambient",
                duration_seconds=2,
                instructions=("Stay still.", "Keep the machine idle."),
                purpose="Baseline.",
            ),
            contact_mic_calibration.CalibrationScenario(
                slug="machine_load_180s",
                title="Machine Load Change",
                duration_seconds=2,
                instructions=("Idle, then apply load.",),
                purpose="Machine-state check.",
            ),
        ]
        ready_slugs: list[str] = []
        output_dir = tmp_path / "session"
        backend = FakeBackend()

        manifest = contact_mic_calibration.run_calibration(
            output_dir=output_dir,
            backend=backend,
            scenarios=scenarios,
            device="hw:9,1",
            sample_rate=10,
            channels=2,
            analysis_window_seconds=1.0,
            wait_for_ready=lambda scenario: ready_slugs.append(scenario.slug),
        )
        summary = json.loads((output_dir / "summary.json").read_text())
        reports = {
            path.stem: json.loads(path.read_text())
            for path in sorted(output_dir.glob("*.json"))
            if path.name != "summary.json"
        }

        assert ready_slugs == ["quiet_ambient_180s", "machine_load_180s"]
        assert [call["device"] for call in backend.calls] == ["hw:9,1", "hw:9,1"]
        assert summary == manifest
        assert summary["sample_rate"] == 10
        assert summary["channels"] == 2
        assert summary["channel_labels"] == {"1": "The Membrane", "2": "The Heartbeat"}
        assert set(reports) == {"quiet_ambient_180s", "machine_load_180s"}
        for scenario in scenarios:
            wav_path = output_dir / f"{scenario.slug}.wav"
            report = reports[scenario.slug]
            assert wav_path.exists()
            assert report["slug"] == scenario.slug
            assert report["capture_path"] == str(wav_path)
            assert report["instructions"] == list(scenario.instructions)
            assert report["analysis"]["duration_seconds"] == 2.0
            assert report["analysis"]["channel_metrics"]["1"]["max_peak"] > 0.0

    def test_cli_json_paths_emit_parseable_payloads(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        capture = tmp_path / "cli.wav"
        frames = [(0, 1200)] * 10 + [(8000, 1200)] * 10
        _write_wav(capture, channels=2, sample_rate=10, frames=frames)

        scenario_code = contact_mic_calibration.main(["list-scenarios", "--json"])
        scenario_stdout = capsys.readouterr().out
        scenario_payload = json.loads(scenario_stdout)

        analyze_code = contact_mic_calibration.main(
            ["analyze", str(capture), "--analysis-window", "1.0", "--json"]
        )
        analyze_stdout = capsys.readouterr().out
        analyze_payload = json.loads(analyze_stdout)

        assert scenario_code == 0
        assert [entry["slug"] for entry in scenario_payload["scenarios"]] == [
            "quiet_ambient_180s",
            "bass_environment_180s",
            "directed_events_60s",
            "machine_load_180s",
        ]
        assert analyze_code == 0
        assert analyze_payload["capture_path"] == str(capture)
        assert analyze_payload["channel_metrics"]["1"]["active_windows"] == 1
        assert analyze_payload["channel_metrics"]["2"]["active_windows"] == 0

    def test_alsa_device_parsing_marks_defaults_and_handles_missing_preferred(
        self,
    ) -> None:
        listing = """
card 0: PCH [HDA Intel PCH], device 0: ALC245 Analog [ALC245 Analog]
card 2: Loopback [Loopback], device 1: Loopback PCM [Loopback PCM]
card 3: USB [Scarlett 4i4 USB], device 2: USB Audio [USB Audio]
""".strip()

        devices = contact_mic_calibration.parse_alsa_devices(listing)
        scarlett = [
            device
            for device in devices
            if device["hw"] == "hw:3,2" and device["matches_default_interface"]
        ]

        assert [device["hw"] for device in devices] == ["hw:0,0", "hw:2,1", "hw:3,2"]
        assert len(scarlett) == 1
        assert contact_mic_calibration.find_alsa_hw_device(listing) == "hw:3,2"
        assert (
            contact_mic_calibration.find_alsa_hw_device(
                listing,
                preferred_name="Missing Interface",
            )
            is None
        )
