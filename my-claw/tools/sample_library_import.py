"""Import curated source audio into the CypherClaw sample library."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from senseweave.sample_library import SampleLibrary, SampleRecord


AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
)


@dataclass(frozen=True)
class ImportEntry:
    path: Path
    character_tags: tuple[str, ...]
    captured_by: str
    recursive: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    source: str = "library"
    pitch_hz: float | None = None
    arc_phase: str | None = None
    mood: float | None = None
    extras: dict[str, str] = field(default_factory=dict)


def import_manifest(
    manifest_path: Path | str,
    *,
    library_root: Path | str = "samples",
) -> list[SampleRecord]:
    manifest = Path(manifest_path)
    payload = tomllib.loads(manifest.read_text())
    imports_payload = payload.get("imports")
    if not isinstance(imports_payload, list) or not imports_payload:
        raise ValueError("manifest must define a non-empty [[imports]] list")

    defaults = {
        "captured_by": _coerce_string(payload.get("captured_by"), ""),
        "source": _coerce_string(payload.get("source"), "library") or "library",
    }
    library_root_path = Path(library_root)
    library_root_path.mkdir(parents=True, exist_ok=True)
    destination_dir = library_root_path / "library"
    destination_dir.mkdir(parents=True, exist_ok=True)

    imported: list[SampleRecord] = []
    library = SampleLibrary(library_root_path)
    try:
        for raw_entry in imports_payload:
            entry = _parse_entry(raw_entry, manifest.parent, defaults)
            for source_path in _resolve_source_files(entry):
                imported.append(
                    _import_one(
                        source_path,
                        entry,
                        destination_dir=destination_dir,
                        library=library,
                    )
                )
    finally:
        library.close()
    return imported


def _parse_entry(
    raw_entry: object,
    manifest_dir: Path,
    defaults: dict[str, str],
) -> ImportEntry:
    if not isinstance(raw_entry, dict):
        raise TypeError("each [[imports]] entry must be a TOML table")
    raw_path = raw_entry.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("each [[imports]] entry requires a non-empty path")

    resolved_path = Path(raw_path)
    if not resolved_path.is_absolute():
        resolved_path = manifest_dir / resolved_path
    captured_by = _coerce_string(
        raw_entry.get("captured_by"),
        defaults["captured_by"],
    )
    if not captured_by:
        raise ValueError(f"captured_by is required for import path {raw_path!r}")

    extras_raw = raw_entry.get("extras", {})
    extras = _coerce_str_dict(extras_raw)
    return ImportEntry(
        path=resolved_path,
        character_tags=tuple(_coerce_str_list(raw_entry.get("character_tags"))),
        captured_by=captured_by,
        recursive=bool(raw_entry.get("recursive", False)),
        include=tuple(_coerce_str_list(raw_entry.get("include"))),
        exclude=tuple(_coerce_str_list(raw_entry.get("exclude"))),
        source=_coerce_string(raw_entry.get("source"), defaults["source"]) or "library",
        pitch_hz=_coerce_optional_float(raw_entry.get("pitch_hz")),
        arc_phase=_coerce_optional_string(raw_entry.get("arc_phase")),
        mood=_coerce_optional_float(raw_entry.get("mood")),
        extras=extras,
    )


def _resolve_source_files(entry: ImportEntry) -> list[Path]:
    source_path = entry.path.expanduser().resolve()
    if source_path.is_file():
        if not _is_audio_file(source_path):
            raise ValueError(f"unsupported audio extension: {source_path}")
        return [source_path]
    if not source_path.is_dir():
        raise FileNotFoundError(f"import path does not exist: {source_path}")

    iterator = source_path.rglob("*") if entry.recursive else source_path.glob("*")
    files = [
        candidate.resolve()
        for candidate in iterator
        if candidate.is_file()
        and _is_audio_file(candidate)
        and _matches_patterns(candidate, entry.include, entry.exclude, root=source_path)
    ]
    return sorted(files)


def _matches_patterns(
    candidate: Path,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    *,
    root: Path,
) -> bool:
    relative = candidate.relative_to(root).as_posix()
    name = candidate.name
    relative_lower = relative.lower()
    name_lower = name.lower()
    if include and not any(
        fnmatch.fnmatch(name_lower, pattern.lower())
        or fnmatch.fnmatch(relative_lower, pattern.lower())
        for pattern in include
    ):
        return False
    if exclude and any(
        fnmatch.fnmatch(name_lower, pattern.lower())
        or fnmatch.fnmatch(relative_lower, pattern.lower())
        for pattern in exclude
    ):
        return False
    return True


def _import_one(
    source_path: Path,
    entry: ImportEntry,
    *,
    destination_dir: Path,
    library: SampleLibrary,
) -> SampleRecord:
    original_path = source_path.expanduser().resolve()
    sample_id = hashlib.sha1(str(original_path).encode("utf-8")).hexdigest()[:32]
    suffix = original_path.suffix.lower()
    stem = _slugify(original_path.stem)
    destination_path = destination_dir / f"{stem}_{sample_id}{suffix}"
    shutil.copy2(original_path, destination_path)

    extras = dict(entry.extras)
    extras["original_path"] = str(original_path)
    extras["captured_by"] = entry.captured_by
    captured_at = datetime.fromtimestamp(
        original_path.stat().st_mtime,
        tz=timezone.utc,
    )
    record = SampleRecord(
        character_tags=frozenset(entry.character_tags),
        sample_id=sample_id,
        path=destination_path,
        source=entry.source,
        pitch_hz=entry.pitch_hz,
        arc_phase=entry.arc_phase,
        mood=entry.mood,
        captured_at=captured_at,
        extras=extras,
    )
    library.add(record)
    return record


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "sample"


def _coerce_string(value: object, default: str) -> str:
    if isinstance(value, str):
        return value.strip()
    return default


def _coerce_optional_string(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise TypeError(f"expected float-compatible value, got {value!r}")


def _coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"expected list[str], got {value!r}")
    return [str(item) for item in value]


def _coerce_str_dict(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"expected table/dict, got {value!r}")
    return {str(key): str(item) for key, item in value.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="TOML import manifest")
    parser.add_argument(
        "--library-root",
        default="samples",
        help="sample library root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    imported = import_manifest(args.manifest, library_root=args.library_root)
    print(f"Imported {len(imported)} samples into {Path(args.library_root) / 'library'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
