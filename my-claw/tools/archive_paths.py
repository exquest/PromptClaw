"""Shared storage-path resolution for large CypherClaw artifacts."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from runtime_paths import resolve_runtime_paths


ARCHIVE_ROOT_ENV = "CYPHERCLAW_ARCHIVE_ROOT"
DEFAULT_ARCHIVE_MOUNT = Path("/mnt/archive")
LEGACY_STORAGE_ROOT = Path("/home/user/cypherclaw-data")
PROJECT_FALLBACK_RELATIVE = Path(".promptclaw") / "archive-storage"
DEFAULT_CAMERA_NAMES = ("porch_eye", "side_eye")


@dataclass(frozen=True)
class ArchivePathLayout:
    """Resolved archive storage paths for long-lived CypherClaw artifacts."""

    storage_root: Path
    storage_source: str
    archive_recordings_root: Path
    sample_events_dir: Path
    camera_root: Path
    camera_capture_dirs: tuple[tuple[str, Path], ...]
    litestream_backup_root: Path


def _is_writable_dir(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def _resolve_archive_storage_root_with_source(
    anchor: str | Path,
    *,
    env_root: str | Path | None = None,
    archive_mount: str | Path = DEFAULT_ARCHIVE_MOUNT,
    legacy_storage_root: str | Path = LEGACY_STORAGE_ROOT,
) -> tuple[Path, str]:
    if env_root is None:
        env_root = os.environ.get(ARCHIVE_ROOT_ENV)
    if env_root:
        return Path(env_root), "env"

    mount = Path(archive_mount)
    if _is_writable_dir(mount):
        return mount / "cypherclaw", "archive_mount"

    legacy = Path(legacy_storage_root)
    if _is_writable_dir(legacy):
        return legacy, "legacy_storage"

    fallback = resolve_runtime_paths(anchor).project_root / PROJECT_FALLBACK_RELATIVE
    return fallback, "project_fallback"


def resolve_archive_storage_root(
    anchor: str | Path,
    *,
    env_root: str | Path | None = None,
    archive_mount: str | Path = DEFAULT_ARCHIVE_MOUNT,
    legacy_storage_root: str | Path = LEGACY_STORAGE_ROOT,
) -> Path:
    """Resolve the preferred root for large persistent CypherClaw artifacts."""
    root, _source = _resolve_archive_storage_root_with_source(
        anchor,
        env_root=env_root,
        archive_mount=archive_mount,
        legacy_storage_root=legacy_storage_root,
    )
    return root


def resolve_archive_layout(
    anchor: str | Path,
    *,
    env_root: str | Path | None = None,
    archive_mount: str | Path = DEFAULT_ARCHIVE_MOUNT,
    legacy_storage_root: str | Path = LEGACY_STORAGE_ROOT,
    camera_names: Iterable[str] = DEFAULT_CAMERA_NAMES,
) -> ArchivePathLayout:
    """Resolve the complete archive directory layout for one runtime."""
    storage_root, storage_source = _resolve_archive_storage_root_with_source(
        anchor,
        env_root=env_root,
        archive_mount=archive_mount,
        legacy_storage_root=legacy_storage_root,
    )
    camera_root = storage_root / "camera"
    camera_capture_dirs = []
    for camera_name in camera_names:
        camera_capture_dirs.append((camera_name, camera_root / f"{camera_name}_captures"))

    return ArchivePathLayout(
        storage_root=storage_root,
        storage_source=storage_source,
        archive_recordings_root=storage_root / "archive",
        sample_events_dir=storage_root / "sample_events",
        camera_root=camera_root,
        camera_capture_dirs=tuple(camera_capture_dirs),
        litestream_backup_root=storage_root / "litestream" / "backups",
    )


def archive_layout_summary(layout: ArchivePathLayout) -> dict[str, str]:
    """Return stable operator-readable archive path fields."""
    summary = {
        "storage_root": str(layout.storage_root),
        "storage_source": layout.storage_source,
        "archive_recordings_root": str(layout.archive_recordings_root),
        "sample_events_dir": str(layout.sample_events_dir),
        "camera_root": str(layout.camera_root),
        "litestream_backup_root": str(layout.litestream_backup_root),
    }
    for camera_name, capture_dir in layout.camera_capture_dirs:
        summary[f"camera.{camera_name}"] = str(capture_dir)
    return summary


def prepare_archive_layout(
    anchor: str | Path,
    *,
    env_root: str | Path | None = None,
    archive_mount: str | Path = DEFAULT_ARCHIVE_MOUNT,
    legacy_storage_root: str | Path = LEGACY_STORAGE_ROOT,
    camera_names: Iterable[str] = DEFAULT_CAMERA_NAMES,
) -> ArchivePathLayout:
    """Resolve and create the standard archive directories."""
    layout = resolve_archive_layout(
        anchor,
        env_root=env_root,
        archive_mount=archive_mount,
        legacy_storage_root=legacy_storage_root,
        camera_names=camera_names,
    )
    directories = [
        layout.storage_root,
        layout.archive_recordings_root,
        layout.sample_events_dir,
        layout.camera_root,
        layout.litestream_backup_root,
    ]
    for _camera_name, capture_dir in layout.camera_capture_dirs:
        directories.append(capture_dir)
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return layout


def resolve_archive_recordings_root(anchor: str | Path, **kwargs: object) -> Path:
    """Directory for long-lived archive daemon outputs."""
    return resolve_archive_storage_root(anchor, **kwargs) / "archive"


def resolve_sample_events_dir(anchor: str | Path, **kwargs: object) -> Path:
    """Directory for rendered sample-event files."""
    return resolve_archive_storage_root(anchor, **kwargs) / "sample_events"


def resolve_camera_capture_dir(anchor: str | Path, camera_name: str, **kwargs: object) -> Path:
    """Directory for long-lived camera capture rings."""
    layout = resolve_archive_layout(anchor, camera_names=(camera_name,), **kwargs)
    for resolved_name, capture_dir in layout.camera_capture_dirs:
        if resolved_name == camera_name:
            return capture_dir
    return layout.camera_root / f"{camera_name}_captures"


def resolve_litestream_backup_root(anchor: str | Path, **kwargs: object) -> Path:
    """Directory for Litestream file-replica backups."""
    return resolve_archive_storage_root(anchor, **kwargs) / "litestream" / "backups"
