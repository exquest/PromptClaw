"""Tests for CypherClaw session_archiver.py."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from cypherclaw.first_boot import bootstrap_identity as real_bootstrap_identity  # noqa: E402
from session_archiver import (  # noqa: E402
    DEFAULT_CHECKPOINT_ARCHIVE_PREFIX,
    DEFAULT_PUBLIC_ARCHIVE_BASE_URL,
    ArchiveConfig,
    CheckpointUpload,
    archive_due_sessions,
    build_session_title,
    plan_checkpoint_upload,
    run,
    run_once,
    upload_checkpoint,
)


TITLE_PATTERN = re.compile(r"^[A-Za-z]+-[A-Za-z]+ / [A-Za-z]+-[A-Za-z]+ — \d{2} [A-Za-z]+$")


@dataclass(frozen=True)
class UploadedObject:
    body: bytes
    content_type: str
    metadata: dict[str, str]


@dataclass
class FakeR2Client:
    objects: dict[str, UploadedObject] = field(default_factory=dict)
    puts: list[dict[str, Any]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def put_object(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None:
        self.events.append(f"put:{key}")
        self.puts.append(
            {
                "key": key,
                "body": body,
                "content_type": content_type,
                "metadata": dict(metadata),
            }
        )
        self.objects[key] = UploadedObject(
            body=body,
            content_type=content_type,
            metadata=dict(metadata),
        )


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _write_segment(
    directory: Path,
    *,
    sequence: int,
    captured_at: datetime,
    duration: float = 60.0,
    patch_name: str = "house_monastery",
    tuning: str = "slendro",
    midi_fragments: list[str] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"seg-{sequence:04d}.opus"
    path.write_bytes(f"OggS synthetic segment {sequence:04d}\n".encode())
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "captured_at": _iso(captured_at),
                "duration": duration,
                "scene": f"synthetic-{sequence:04d}",
                "patch_name": patch_name,
                "tuning": tuning,
                "rms": 0.14,
                "midi_fragments": midi_fragments or [],
            }
        )
    )
    return path


def _write_minute_segments(
    directory: Path,
    *,
    start: datetime,
    minutes: int,
    patch_name: str = "house_monastery",
    tuning: str = "slendro",
) -> None:
    for minute in range(minutes):
        _write_segment(
            directory,
            sequence=minute,
            captured_at=start + timedelta(minutes=minute),
            patch_name=patch_name,
            tuning=tuning,
        )


def _metadata_objects(client: FakeR2Client) -> list[dict[str, Any]]:
    metadata_keys = sorted(key for key in client.objects if key.endswith("/metadata.json"))
    return [json.loads(client.objects[key].body.decode()) for key in metadata_keys]


def test_thirty_minutes_of_synthetic_uptime_uploads_three_named_sessions_to_r2(
    tmp_path: Path,
) -> None:
    segment_dir = tmp_path / "segments"
    start = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    _write_minute_segments(segment_dir, start=start, minutes=30)
    client = FakeR2Client()
    config = ArchiveConfig(
        segment_dir=segment_dir,
        state_path=tmp_path / "session-archiver-state.json",
    )

    sessions = archive_due_sessions(
        config,
        client,
        now=start + timedelta(minutes=30),
        bootstrap_identity_fn=lambda **_kwargs: object(),
    )

    assert len(sessions) == 3
    assert len([key for key in client.objects if key.endswith("/session.opus")]) == 3
    assert len([key for key in client.objects if key.endswith("/metadata.json")]) == 3
    assert all(key.startswith("cypherclaw/archive/") for key in client.objects)

    metadata_items = _metadata_objects(client)
    assert all(TITLE_PATTERN.match(item["title"]) for item in metadata_items)
    assert {item["dominant_house"] for item in metadata_items} == {"house_monastery"}
    assert {item["primary_tuning"] for item in metadata_items} == {"slendro"}
    assert [item["segment_count"] for item in metadata_items] == [8, 8, 8]
    assert all(item["duration_seconds"] >= 480 for item in metadata_items)

    first_audio_key = sorted(key for key in client.objects if key.endswith("/session.opus"))[0]
    assert client.objects[first_audio_key].content_type == "audio/ogg; codecs=opus"
    assert b"OggS synthetic segment 0000" in client.objects[first_audio_key].body
    assert b"OggS synthetic segment 0007" in client.objects[first_audio_key].body


def test_session_title_uses_dominant_house_primary_tuning_and_date() -> None:
    assert (
        build_session_title(
            dominant_house="house_monastery",
            primary_tuning="slendro",
            date=datetime(2026, 5, 23, 9, 30, tzinfo=UTC),
        )
        == "Monastery-Stone / Slendro-Drift — 23 May"
    )
    assert (
        build_session_title(
            dominant_house="house_garden",
            primary_tuning="just_intonation_5_limit",
            date=datetime(2026, 6, 14, 18, 0, tzinfo=UTC),
        )
        == "Garden-Dusk / Just-Choir — 14 June"
    )


def test_repeat_archiver_run_skips_already_uploaded_sessions(tmp_path: Path) -> None:
    segment_dir = tmp_path / "segments"
    start = datetime(2026, 5, 23, 8, 0, tzinfo=UTC)
    _write_minute_segments(segment_dir, start=start, minutes=16)
    client = FakeR2Client()
    config = ArchiveConfig(
        segment_dir=segment_dir,
        state_path=tmp_path / "session-archiver-state.json",
    )

    first = archive_due_sessions(
        config,
        client,
        now=start + timedelta(minutes=16),
        bootstrap_identity_fn=lambda **_kwargs: object(),
    )
    second = archive_due_sessions(
        config,
        client,
        now=start + timedelta(minutes=16),
        bootstrap_identity_fn=lambda **_kwargs: object(),
    )

    assert len(first) == 2
    assert second == []
    assert len(client.puts) == 4
    state = json.loads(config.state_path.read_text())
    assert state["archived_session_ids"] == [session.session_id for session in first]


def test_archiver_startup_bootstraps_identity_before_upload_and_persists_between_boots(
    tmp_path: Path,
) -> None:
    segment_dir = tmp_path / "segments"
    start = datetime(2026, 5, 23, 6, 0, tzinfo=UTC)
    _write_minute_segments(segment_dir, start=start, minutes=8)
    client = FakeR2Client()
    config = ArchiveConfig(
        segment_dir=segment_dir,
        state_path=tmp_path / "session-archiver-state.json",
        identity_path=tmp_path / "identity.json",
        identity_mode="federated",
        identity_release="test-release",
        identity_parent_id="parent-home",
    )
    events: list[tuple[str, dict[str, Any]]] = []

    def bootstrap_identity(**kwargs: Any) -> object:
        events.append(("bootstrap", kwargs))
        client.events.append("bootstrap")
        return real_bootstrap_identity(**kwargs)

    sessions = run_once(
        config,
        client,
        now=start + timedelta(minutes=8),
        bootstrap_identity_fn=bootstrap_identity,
    )

    assert len(sessions) == 1
    assert client.events[0] == "bootstrap"
    assert any(event.startswith("put:cypherclaw/archive/") for event in client.events[1:])
    assert events[0][1]["mode"] == "federated"
    assert events[0][1]["release"] == "test-release"
    assert events[0][1]["parent_id"] == "parent-home"
    assert events[0][1]["identity_path"] == config.identity_path

    first_identity = json.loads(config.identity_path.read_text())
    assert first_identity["mode"] == "federated"
    assert first_identity["parent_id"] == "parent-home"

    second = run_once(
        config,
        client,
        now=start + timedelta(minutes=8),
        bootstrap_identity_fn=bootstrap_identity,
    )
    second_identity = json.loads(config.identity_path.read_text())

    assert second == []
    assert second_identity["instance_id"] == first_identity["instance_id"]

    standalone_config = ArchiveConfig(
        segment_dir=tmp_path / "empty-segments",
        state_path=tmp_path / "standalone-state.json",
        identity_path=tmp_path / "standalone-identity.json",
        identity_mode="standalone",
    )
    run_once(
        standalone_config,
        client,
        now=start + timedelta(minutes=8),
        bootstrap_identity_fn=bootstrap_identity,
    )
    standalone_identity = json.loads(standalone_config.identity_path.read_text())
    assert standalone_identity["mode"] == "standalone"


def _write_checkpoint_source(tmp_path: Path, body: bytes) -> Path:
    source = tmp_path / "feature-1-reverb-spaces-20260523T204500Z.opus"
    source.write_bytes(body)
    return source


def test_upload_checkpoint_writes_audio_and_metadata_under_checkpoints_prefix(
    tmp_path: Path,
) -> None:
    body = b"OggS T-056b reverb-spaces checkpoint body\n"
    source = _write_checkpoint_source(tmp_path, body)
    client = FakeR2Client()

    result = upload_checkpoint(
        source_path=source,
        slug="feature-1-reverb-spaces",
        client=client,
        timestamp="20260523T204500Z",
    )

    folder = "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T204500Z"
    expected_audio_key = f"{folder}/{source.name}"
    expected_metadata_key = f"{folder}/metadata.json"

    assert isinstance(result, CheckpointUpload)
    assert result.audio_key == expected_audio_key
    assert result.metadata_key == expected_metadata_key
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.size_bytes == len(body)
    assert set(client.objects) == {expected_audio_key, expected_metadata_key}
    assert client.objects[expected_audio_key].body == body
    assert client.objects[expected_audio_key].content_type == "audio/ogg; codecs=opus"

    metadata_payload = json.loads(client.objects[expected_metadata_key].body.decode())
    assert metadata_payload["sha256"] == result.sha256
    assert metadata_payload["audio_key"] == expected_audio_key
    assert metadata_payload["audio_url"] == result.audio_url
    assert metadata_payload["metadata_url"] == result.metadata_url
    assert metadata_payload["uploaded_at"].endswith("Z")


def test_upload_checkpoint_returns_constructed_public_archive_url(
    tmp_path: Path,
) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS small\n")
    client = FakeR2Client()

    result = upload_checkpoint(
        source_path=source,
        slug="feature-1-reverb-spaces",
        client=client,
        timestamp="20260523T204500Z",
    )

    assert result.audio_url == (
        "https://cypherclaw.holdenu.com/"
        "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T204500Z/"
        f"{source.name}"
    )
    assert result.metadata_url == (
        "https://cypherclaw.holdenu.com/"
        "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T204500Z/"
        "metadata.json"
    )
    assert result.audio_url.startswith(DEFAULT_PUBLIC_ARCHIVE_BASE_URL + "/")
    assert DEFAULT_CHECKPOINT_ARCHIVE_PREFIX in result.audio_key


def test_upload_checkpoint_uses_now_when_no_timestamp_supplied(tmp_path: Path) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")
    client = FakeR2Client()
    fixed_now = datetime(2026, 5, 23, 22, 15, 30, tzinfo=UTC)

    result = upload_checkpoint(
        source_path=source,
        slug="feature-1-reverb-spaces",
        client=client,
        now=fixed_now,
    )

    assert result.timestamp == "20260523T221530Z"
    assert "feature-1-reverb-spaces-20260523T221530Z/" in result.audio_key


def test_upload_checkpoint_honours_custom_prefix_and_public_base_url(
    tmp_path: Path,
) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")
    client = FakeR2Client()

    result = upload_checkpoint(
        source_path=source,
        slug="feature-1-reverb-spaces",
        client=client,
        timestamp="20260523T204500Z",
        checkpoint_prefix="custom/checkpoints",
        public_base_url="https://archive.example.test/api",
    )

    assert result.audio_key.startswith(
        "custom/checkpoints/feature-1-reverb-spaces-20260523T204500Z/"
    )
    assert result.audio_url.startswith(
        "https://archive.example.test/api/custom/checkpoints/"
    )


def test_upload_checkpoint_rejects_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.opus"
    client = FakeR2Client()

    with pytest.raises(FileNotFoundError, match="does-not-exist.opus"):
        upload_checkpoint(
            source_path=missing,
            slug="feature-1-reverb-spaces",
            client=client,
        )

    assert client.objects == {}


def test_upload_checkpoint_rejects_empty_slug(tmp_path: Path) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")
    client = FakeR2Client()

    with pytest.raises(ValueError, match="non-empty"):
        upload_checkpoint(source_path=source, slug="   ", client=client)

    assert client.objects == {}


def test_plan_checkpoint_upload_reports_keys_urls_and_source_presence(
    tmp_path: Path,
) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")

    plan = plan_checkpoint_upload(
        source_path=source,
        slug="feature-1-reverb-spaces",
        timestamp="20260523T204500Z",
    )

    assert plan["ok"] if "ok" in plan else True
    assert plan["audio_key"] == (
        "cypherclaw/archive/checkpoints/"
        "feature-1-reverb-spaces-20260523T204500Z/"
        f"{source.name}"
    )
    assert plan["metadata_key"].endswith("/metadata.json")
    assert plan["audio_url"].startswith("https://cypherclaw.holdenu.com/")
    assert plan["source_exists"] is True
    assert plan["checkpoint_prefix"] == "cypherclaw/archive/checkpoints"


def test_run_checkpoint_dry_run_prints_plan_without_uploading(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")

    exit_code = run(
        [
            "--dry-run",
            "--checkpoint-source",
            str(source),
            "--checkpoint-slug",
            "feature-1-reverb-spaces",
            "--checkpoint-timestamp",
            "20260523T204500Z",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    checkpoint = payload["checkpoint"]
    assert checkpoint["audio_key"].startswith(
        "cypherclaw/archive/checkpoints/feature-1-reverb-spaces-20260523T204500Z/"
    )
    assert checkpoint["audio_url"].startswith("https://cypherclaw.holdenu.com/")
    assert checkpoint["source_exists"] is True


def test_run_checkpoint_requires_both_source_and_slug(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_checkpoint_source(tmp_path, b"OggS\n")

    exit_code = run(["--checkpoint-source", str(source)])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "checkpoint-source" in payload["error"]
    assert "checkpoint-slug" in payload["error"]
