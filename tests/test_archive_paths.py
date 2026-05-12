"""Tests for heavy archive/storage path selection."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from archive_paths import (
    archive_layout_summary,
    prepare_archive_layout,
    resolve_archive_layout,
    resolve_archive_recordings_root,
    resolve_archive_storage_root,
    resolve_camera_capture_dir,
    resolve_litestream_backup_root,
    resolve_sample_events_dir,
)


def _make_runtime_root(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "sdp").mkdir()


def test_archive_storage_root_prefers_env_override(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")

    result = resolve_archive_storage_root(
        anchor,
        env_root=tmp_path / "custom-archive",
        archive_mount=tmp_path / "missing-mount",
        legacy_storage_root=tmp_path / "legacy",
    )

    assert result == tmp_path / "custom-archive"


def test_archive_storage_root_prefers_mounted_archive_volume(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")
    mount = tmp_path / "mnt" / "archive"
    mount.mkdir(parents=True)

    result = resolve_archive_storage_root(
        anchor,
        archive_mount=mount,
        legacy_storage_root=tmp_path / "legacy",
    )

    assert result == mount / "cypherclaw"


def test_archive_storage_root_falls_back_to_legacy_storage_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")
    legacy = tmp_path / "cypherclaw-data"
    legacy.mkdir()

    result = resolve_archive_storage_root(
        anchor,
        archive_mount=tmp_path / "missing-mount",
        legacy_storage_root=legacy,
    )

    assert result == legacy


def test_archive_storage_root_falls_back_to_project_local_path(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")

    result = resolve_archive_storage_root(
        anchor,
        archive_mount=tmp_path / "missing-mount",
        legacy_storage_root=tmp_path / "missing-legacy",
    )

    assert result == runtime_root / ".promptclaw" / "archive-storage"


def test_derived_archive_paths_share_storage_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "sample_playback_engine.py"
    anchor.write_text("# stub\n")
    mount = tmp_path / "mnt" / "archive"
    mount.mkdir(parents=True)

    assert resolve_archive_recordings_root(anchor, archive_mount=mount) == mount / "cypherclaw" / "archive"
    assert resolve_sample_events_dir(anchor, archive_mount=mount) == mount / "cypherclaw" / "sample_events"
    assert resolve_camera_capture_dir(anchor, "porch_eye", archive_mount=mount) == mount / "cypherclaw" / "camera" / "porch_eye_captures"
    assert resolve_litestream_backup_root(anchor, archive_mount=mount) == mount / "cypherclaw" / "litestream" / "backups"


def test_archive_layout_reports_all_standard_paths_and_source(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")
    mount = tmp_path / "mnt" / "archive"
    mount.mkdir(parents=True)

    layout = resolve_archive_layout(anchor, archive_mount=mount)

    assert layout.storage_root == mount / "cypherclaw"
    assert layout.storage_source == "archive_mount"
    assert layout.archive_recordings_root == mount / "cypherclaw" / "archive"
    assert layout.sample_events_dir == mount / "cypherclaw" / "sample_events"
    assert layout.camera_root == mount / "cypherclaw" / "camera"
    assert layout.camera_capture_dirs == (
        ("porch_eye", mount / "cypherclaw" / "camera" / "porch_eye_captures"),
        ("side_eye", mount / "cypherclaw" / "camera" / "side_eye_captures"),
    )
    assert layout.litestream_backup_root == mount / "cypherclaw" / "litestream" / "backups"


def test_archive_layout_summary_contains_meaningful_operator_output(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "sample_playback_engine.py"
    anchor.write_text("# stub\n")

    layout = resolve_archive_layout(anchor, env_root=tmp_path / "archive-root")
    summary = archive_layout_summary(layout)

    assert summary == {
        "storage_root": str(tmp_path / "archive-root"),
        "storage_source": "env",
        "archive_recordings_root": str(tmp_path / "archive-root" / "archive"),
        "sample_events_dir": str(tmp_path / "archive-root" / "sample_events"),
        "camera_root": str(tmp_path / "archive-root" / "camera"),
        "camera.porch_eye": str(tmp_path / "archive-root" / "camera" / "porch_eye_captures"),
        "camera.side_eye": str(tmp_path / "archive-root" / "camera" / "side_eye_captures"),
        "litestream_backup_root": str(tmp_path / "archive-root" / "litestream" / "backups"),
    }


def test_prepare_archive_layout_creates_end_to_end_directories(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")

    layout = prepare_archive_layout(
        anchor,
        env_root=tmp_path / "archive-root",
        camera_names=("porch_eye", "side_eye", "lab_eye"),
    )

    expected_dirs = {
        layout.storage_root,
        layout.archive_recordings_root,
        layout.sample_events_dir,
        layout.camera_root,
        layout.litestream_backup_root,
        *(path for _, path in layout.camera_capture_dirs),
    }
    assert all(path.is_dir() for path in expected_dirs)


def test_existing_derived_resolvers_match_layout(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "archive_daemon.py"
    anchor.write_text("# stub\n")
    legacy = tmp_path / "cypherclaw-data"
    legacy.mkdir()

    layout = resolve_archive_layout(
        anchor,
        archive_mount=tmp_path / "missing-mount",
        legacy_storage_root=legacy,
    )

    assert resolve_archive_recordings_root(anchor, archive_mount=tmp_path / "missing-mount", legacy_storage_root=legacy) == layout.archive_recordings_root
    assert resolve_sample_events_dir(anchor, archive_mount=tmp_path / "missing-mount", legacy_storage_root=legacy) == layout.sample_events_dir
    assert resolve_camera_capture_dir(anchor, "porch_eye", archive_mount=tmp_path / "missing-mount", legacy_storage_root=legacy) == dict(layout.camera_capture_dirs)["porch_eye"]
    assert resolve_litestream_backup_root(anchor, archive_mount=tmp_path / "missing-mount", legacy_storage_root=legacy) == layout.litestream_backup_root
