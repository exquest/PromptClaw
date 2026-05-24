"""Tests for T-058b live HLS reference capture."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from live_reference_capture import (  # noqa: E402
    DEFAULT_DURATION_SECONDS,
    DEFAULT_PREFIX,
    CaptureConfig,
    build_ffmpeg_command,
    capture_reference_sample,
    run,
)


class _FakeHttpResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode()


def _playlist_with_segments() -> str:
    return "\n".join(
        (
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:6",
            "#EXTINF:6.000,",
            "/api/cypherclaw/segment/cypherclaw/live/2026-05-24/seg-1.opus",
        )
    )


def test_capture_live_reference_runs_ffmpeg_and_logs_checksum(tmp_path: Path) -> None:
    output_dir = tmp_path / "reference-renders"
    config = CaptureConfig(
        playlist_url="https://example.test/api/cypherclaw/live.m3u8",
        output_dir=output_dir,
        timestamp="20260524T010203Z",
    )
    rendered = b"OggS synthetic T-058b reference capture\n"
    commands: list[list[str]] = []

    def fake_urlopen(_request: Any, *, timeout: float) -> _FakeHttpResponse:
        assert timeout == config.playlist_timeout_seconds
        return _FakeHttpResponse(_playlist_with_segments())

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == pytest.approx(DEFAULT_DURATION_SECONDS + 30.0)
        Path(command[-1]).write_bytes(rendered)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = capture_reference_sample(
        config,
        run_command=fake_run,
        urlopen_fn=fake_urlopen,
    )

    expected_output = output_dir / "feature-3-stream-20260524T010203Z.opus"
    assert result.output_path == expected_output
    assert result.output_path.read_bytes() == rendered
    assert result.sha256 == hashlib.sha256(rendered).hexdigest()
    assert result.size_bytes == len(rendered)
    assert result.duration_seconds == DEFAULT_DURATION_SECONDS
    assert commands == [build_ffmpeg_command(config, expected_output)]
    assert "-t" in commands[0]
    assert commands[0][commands[0].index("-t") + 1] == "60"
    assert commands[0][-1] == str(expected_output)

    log_lines = (output_dir / "checksums.jsonl").read_text().splitlines()
    assert len(log_lines) == 1
    logged = json.loads(log_lines[0])
    assert logged["output_path"] == str(expected_output)
    assert logged["sha256"] == result.sha256
    assert logged["size_bytes"] == len(rendered)
    assert logged["playlist_url"] == config.playlist_url
    assert logged["duration_seconds"] == DEFAULT_DURATION_SECONDS
    assert logged["ffmpeg_command"] == commands[0]


def test_cold_playlist_fails_before_ffmpeg_runs(tmp_path: Path) -> None:
    config = CaptureConfig(
        playlist_url="https://example.test/api/cypherclaw/live.m3u8",
        output_dir=tmp_path / "reference-renders",
        timestamp="20260524T010203Z",
    )
    commands: list[list[str]] = []

    def fake_urlopen(_request: Any, *, timeout: float) -> _FakeHttpResponse:
        return _FakeHttpResponse(
            "\n".join(
                (
                    "#EXTM3U",
                    "#EXT-X-VERSION:3",
                    "#EXT-X-TARGETDURATION:6",
                    "#EXT-X-MEDIA-SEQUENCE:0",
                )
            )
        )

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(RuntimeError, match="no media segments"):
        capture_reference_sample(
            config,
            run_command=fake_run,
            urlopen_fn=fake_urlopen,
        )

    assert commands == []
    assert not (config.output_dir / "checksums.jsonl").exists()


def test_existing_output_file_is_not_overwritten(tmp_path: Path) -> None:
    output_dir = tmp_path / "reference-renders"
    output_dir.mkdir()
    existing = output_dir / "feature-3-stream-20260524T010203Z.opus"
    existing.write_bytes(b"existing")
    config = CaptureConfig(output_dir=output_dir, timestamp="20260524T010203Z")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        capture_reference_sample(config)

    assert existing.read_bytes() == b"existing"


def test_run_dry_run_prints_planned_capture_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run(
        [
            "--dry-run",
            "--playlist-url",
            "https://example.test/api/cypherclaw/live.m3u8",
            "--output-dir",
            str(tmp_path / "reference-renders"),
            "--timestamp",
            "20260524T010203Z",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["output_path"].endswith(
        f"{DEFAULT_PREFIX}-20260524T010203Z.opus"
    )
    assert payload["checksum_log"].endswith("checksums.jsonl")
    assert payload["ffmpeg_command"][-1] == payload["output_path"]
    assert not Path(payload["output_path"]).exists()


def test_run_invokes_bootstrap_identity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrapped: list[dict[str, Any]] = []

    def fake_bootstrap(**kwargs: Any) -> None:
        bootstrapped.append(kwargs)

    monkeypatch.setattr("live_reference_capture._bootstrap_identity", fake_bootstrap)

    exit_code = run(
        [
            "--dry-run",
            "--identity-mode",
            "federated",
            "--identity-release",
            "v1.2.3",
            "--identity-parent-id",
            "parent-456",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert len(bootstrapped) == 1
    assert bootstrapped[0] == {
        "mode": "federated",
        "release": "v1.2.3",
        "parent_id": "parent-456",
    }
