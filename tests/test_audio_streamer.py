"""Tests for audio_streamer.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from audio_streamer import (  # noqa: E402
    DEFAULT_BITRATE_KBPS,
    DEFAULT_CLIENT_NAME,
    DEFAULT_SEGMENT_SECONDS,
    SegmentProbe,
    StreamerConfig,
    build_ffmpeg_command,
    check_process_cpu,
    start_streamer,
    validate_segment_probe,
)


def _value_after(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def test_ffmpeg_command_segments_jack_output_to_constrained_96k_opus(tmp_path: Path) -> None:
    config = StreamerConfig(output_dir=tmp_path, jack_wrapper=("pw-jack",))

    command = build_ffmpeg_command(config)

    assert command[:2] == ["pw-jack", "ffmpeg"]
    assert _value_after(command, "-f") == "jack"
    assert _value_after(command, "-ac") == "2"
    assert _value_after(command, "-i") == DEFAULT_CLIENT_NAME
    assert _value_after(command, "-c:a") == "libopus"
    assert _value_after(command, "-b:a") == f"{DEFAULT_BITRATE_KBPS}k"
    assert _value_after(command, "-vbr") == "constrained"
    assert _value_after(command, "-application") == "audio"
    assert _value_after(command, "-frame_duration") == "20"
    assert _value_after(command, "-threads") == "1"
    assert _value_after(command, "-segment_time") == str(DEFAULT_SEGMENT_SECONDS)
    assert _value_after(command, "-segment_format") == "ogg"
    assert _value_after(command, "-reset_timestamps") == "1"
    assert command[max(i for i, value in enumerate(command) if value == "-f") + 1] == "segment"
    assert command[-1].startswith(str(tmp_path))
    assert command[-1].endswith(".opus")


class _FakeProcess:
    pid = 4321

    def __init__(self, command: list[str]) -> None:
        self.command = command
        self.terminated = False
        self.waited = False

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0


def test_start_streamer_bootstraps_identity_waits_for_ports_and_connects_output_bus(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "streamer.pid"
    config = StreamerConfig(
        output_dir=tmp_path / "segments",
        pid_file=pid_file,
        jack_wrapper=("pw-jack",),
        identity_mode="federated",
        identity_release="3.1.0",
        identity_parent_id="parent-1",
    )
    events: list[str] = []
    processes: list[_FakeProcess] = []
    run_commands: list[list[str]] = []
    identity_calls: list[dict[str, Any]] = []

    def fake_bootstrap_identity(**kwargs: Any) -> object:
        events.append("bootstrap")
        identity_calls.append(kwargs)
        return object()

    def fake_popen(command: list[str], **_kwargs: Any) -> _FakeProcess:
        events.append("popen")
        process = _FakeProcess(command)
        processes.append(process)
        return process

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        events.append("run")
        run_commands.append(command)
        if command == ["pw-jack", "jack_lsp"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "cypherclaw-opus-stream:input_1\n"
                    "cypherclaw-opus-stream:input_2\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    process = start_streamer(
        config,
        popen_factory=fake_popen,
        run_command=fake_run,
        bootstrap_identity_fn=fake_bootstrap_identity,
    )

    assert process is processes[0]
    assert events[:2] == ["bootstrap", "popen"]
    assert identity_calls == [
        {"mode": "federated", "release": "3.1.0", "parent_id": "parent-1"}
    ]
    assert config.output_dir.exists()
    assert pid_file.read_text().strip() == "4321"
    assert processes[0].command[:2] == ["pw-jack", "ffmpeg"]
    assert ["pw-jack", "jack_lsp"] in run_commands
    assert [
        "pw-jack",
        "jack_connect",
        "SuperCollider:out_1",
        "cypherclaw-opus-stream:input_1",
    ] in run_commands
    assert [
        "pw-jack",
        "jack_connect",
        "SuperCollider:out_2",
        "cypherclaw-opus-stream:input_2",
    ] in run_commands


def test_segment_validation_accepts_expected_duration_and_bitrate() -> None:
    valid = SegmentProbe(
        path=Path("segment.opus"),
        duration_seconds=5.92,
        bitrate_bps=96_320,
    )

    result = validate_segment_probe(
        valid,
        expected_duration_seconds=6.0,
        duration_tolerance_seconds=0.5,
        expected_bitrate_bps=96_000,
        bitrate_tolerance_ratio=0.2,
    )

    assert result.ok is True
    assert result.duration_ok is True
    assert result.bitrate_ok is True
    assert result.duration_delta_seconds < 0.5
    assert result.bitrate_delta_ratio < 0.01

    invalid = SegmentProbe(
        path=Path("bad.opus"),
        duration_seconds=4.0,
        bitrate_bps=150_000,
    )

    invalid_result = validate_segment_probe(
        invalid,
        expected_duration_seconds=6.0,
        duration_tolerance_seconds=0.5,
        expected_bitrate_bps=96_000,
        bitrate_tolerance_ratio=0.2,
    )

    assert invalid_result.ok is False
    assert invalid_result.duration_ok is False
    assert invalid_result.bitrate_ok is False
    assert "duration" in " ".join(invalid_result.errors)
    assert "bitrate" in " ".join(invalid_result.errors)


def test_cpu_check_reports_under_and_over_limit_from_ps() -> None:
    def under_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == ["ps", "-p", "4321", "-o", "%cpu="]
        return subprocess.CompletedProcess(command, 0, stdout=" 7.4\n", stderr="")

    under = check_process_cpu(4321, max_cpu_percent=10.0, run_command=under_run)

    assert under.ok is True
    assert under.cpu_percent == 7.4

    def over_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == ["ps", "-p", "4321", "-o", "%cpu="]
        return subprocess.CompletedProcess(command, 0, stdout=" 12.1\n", stderr="")

    over = check_process_cpu(4321, max_cpu_percent=10.0, run_command=over_run)

    assert over.ok is False
    assert over.cpu_percent == 12.1
    assert "cpu" in " ".join(over.errors)
