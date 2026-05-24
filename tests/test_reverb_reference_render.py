"""Tests for T-056a feature-1 reverb-spaces reference render."""

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

from reverb_reference_render import (  # noqa: E402
    CHECKPOINT_PREFIX,
    DEFAULT_STAGING_DIR,
    REQUIRED_REVERB_VOICES,
    ReverbRenderConfig,
    assert_per_voice_reverb_active,
    render_reverb_reference_sample,
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
            "/api/cypherclaw/segment/cypherclaw/live/2026-05-23/seg-1.opus",
        )
    )


def test_required_voice_set_matches_design_statement() -> None:
    assert set(REQUIRED_REVERB_VOICES) == {
        "pluck",
        "breath",
        "choir",
        "kotekan",
        "pad",
        "bowed",
        "tabla_tin",
    }


def test_assert_per_voice_reverb_active_passes_with_full_profiles() -> None:
    profiles = {voice: object() for voice in REQUIRED_REVERB_VOICES}
    assert_per_voice_reverb_active(profiles)


def test_assert_per_voice_reverb_active_rejects_missing_voice() -> None:
    profiles = {voice: object() for voice in REQUIRED_REVERB_VOICES if voice != "choir"}
    with pytest.raises(RuntimeError, match="choir"):
        assert_per_voice_reverb_active(profiles)


def test_render_writes_to_staging_path_with_checkpoint_prefix(tmp_path: Path) -> None:
    staging_dir = tmp_path / "checkpoints" / "feature-1-reverb-spaces"
    config = ReverbRenderConfig(
        playlist_url="https://example.test/api/cypherclaw/live.m3u8",
        staging_dir=staging_dir,
        timestamp="20260523T204500Z",
    )
    rendered = b"OggS synthetic T-056a reverb-spaces capture\n"
    commands: list[list[str]] = []

    def fake_urlopen(_request: Any, *, timeout: float) -> _FakeHttpResponse:
        del timeout
        return _FakeHttpResponse(_playlist_with_segments())

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(rendered)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = render_reverb_reference_sample(
        config,
        run_command=fake_run,
        urlopen_fn=fake_urlopen,
    )

    expected_output = staging_dir / f"{CHECKPOINT_PREFIX}-20260523T204500Z.opus"
    assert result.output_path == expected_output
    assert result.sha256 == hashlib.sha256(rendered).hexdigest()
    assert result.duration_seconds == 60.0

    log_records = [
        json.loads(line)
        for line in (staging_dir / "checksums.jsonl").read_text().splitlines()
    ]
    assert len(log_records) == 1
    assert log_records[0]["output_path"] == str(expected_output)
    assert log_records[0]["sha256"] == result.sha256


def test_render_refuses_to_overwrite_existing_staging_file(tmp_path: Path) -> None:
    staging_dir = tmp_path / "checkpoints" / "feature-1-reverb-spaces"
    staging_dir.mkdir(parents=True)
    existing = staging_dir / f"{CHECKPOINT_PREFIX}-20260523T204500Z.opus"
    existing.write_bytes(b"existing")
    config = ReverbRenderConfig(
        staging_dir=staging_dir, timestamp="20260523T204500Z"
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        render_reverb_reference_sample(config)

    assert existing.read_bytes() == b"existing"


def test_dry_run_emits_plan_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    staging_dir = tmp_path / "checkpoints" / "feature-1-reverb-spaces"
    exit_code = run(
        [
            "--dry-run",
            "--staging-dir",
            str(staging_dir),
            "--timestamp",
            "20260523T204500Z",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["checkpoint_prefix"] == CHECKPOINT_PREFIX
    assert payload["output_path"].endswith(
        f"{CHECKPOINT_PREFIX}-20260523T204500Z.opus"
    )
    assert payload["staging_dir"] == str(staging_dir)
    assert payload["required_reverb_voices"] == list(REQUIRED_REVERB_VOICES)
    assert payload["ffmpeg_command"][-1] == payload["output_path"]
    assert not Path(payload["output_path"]).exists()


def test_default_staging_dir_targets_checkpoint_subtree() -> None:
    assert DEFAULT_STAGING_DIR == Path(
        "/home/user/cypherclaw/var/reference-renders/checkpoints/feature-1-reverb-spaces"
    )
