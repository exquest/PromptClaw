from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_PAL_DEPLOYMENT_MANIFEST = Path("ops/deployment-manifest.json")
PAL_DEPLOYMENT_ROOT = "/opt/pal"

_MODE_RE = re.compile(r"^0[0-7]{3}$")
_SECRET_LITERAL_MARKERS: tuple[str, ...] = (
    "PAL_SSH_KEY",
    "VAST_API_KEY",
    "TAILSCALE_AUTH_KEY",
    "tskey-auth-",
    "Authorization",
    "BEGIN OPENSSH PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
)
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key|auth[_-]?key|secret|token|authorization)\s*[:=]"),
    re.compile(r"(?i)/(Users|home)/[^\"'\s]+/\.ssh/[^\"'\s]+"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
)


class PALDeploymentManifestError(ValueError):
    """Raised when a PAL deployment manifest cannot be loaded safely."""


@dataclass(frozen=True)
class PALDeploymentFile:
    source: str
    target: str
    mode: str
    owner: str
    group: str
    kind: str
    service_impact: str
    required: bool = True

    def source_path(self, project_root: Path) -> Path:
        return project_root / self.source

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
            "owner": self.owner,
            "group": self.group,
            "kind": self.kind,
            "service_impact": self.service_impact,
            "required": self.required,
        }


@dataclass(frozen=True)
class PALDeploymentManifest:
    manifest_path: Path
    manifest_version: int
    name: str
    deployment_root: str
    mode: str
    files: tuple[PALDeploymentFile, ...]
    runtime_directories: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    raw_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "name": self.name,
            "deployment_root": self.deployment_root,
            "mode": self.mode,
            "files": [entry.to_dict() for entry in self.files],
            "runtime_directories": list(self.runtime_directories),
            "excluded_paths": list(self.excluded_paths),
        }


@dataclass(frozen=True)
class PALDeploymentManifestValidation:
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.errors


def load_pal_deployment_manifest(
    project_root: Path,
    *,
    manifest_path: Path | None = None,
    validate_manifest: bool = True,
) -> PALDeploymentManifest:
    """Load and optionally validate a PAL deployment manifest."""
    root = project_root.resolve()
    path = manifest_path if manifest_path is not None else root / DEFAULT_PAL_DEPLOYMENT_MANIFEST
    raw_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PALDeploymentManifestError(f"Malformed PAL deployment manifest JSON: {path}") from exc

    manifest = _manifest_from_payload(path=path, raw_text=raw_text, payload=payload)
    if validate_manifest:
        validation = validate_pal_deployment_manifest(manifest, root)
        if not validation.passed:
            raise PALDeploymentManifestError("; ".join(validation.errors))
    return manifest


def validate_pal_deployment_manifest(
    manifest: PALDeploymentManifest,
    project_root: Path,
) -> PALDeploymentManifestValidation:
    """Return validation errors for a loaded PAL deployment manifest."""
    errors: list[str] = []
    root = project_root.resolve()
    deployment_root = manifest.deployment_root.rstrip("/")

    if deployment_root != PAL_DEPLOYMENT_ROOT:
        errors.append(f"deployment_root must be {PAL_DEPLOYMENT_ROOT}")
    if manifest.manifest_version != 1:
        errors.append("manifest_version must be 1")
    if manifest.mode != "host-managed":
        errors.append("mode must be host-managed")

    errors.extend(_secret_errors(manifest.raw_text))

    seen_targets: set[str] = set()
    for entry in manifest.files:
        if entry.target in seen_targets:
            errors.append(f"duplicate target: {entry.target}")
        seen_targets.add(entry.target)
        if not _is_child_path(entry.target, deployment_root):
            errors.append(f"managed file target must be under {deployment_root}: {entry.target}")
        if "*" in entry.target:
            errors.append(f"managed file target must not contain globs: {entry.target}")
        if not _MODE_RE.match(entry.mode):
            errors.append(f"invalid mode for {entry.target}: {entry.mode}")
        if not _valid_relative_source(entry.source):
            errors.append(f"source must be repo-relative without parent traversal: {entry.source}")
        if entry.required and not entry.source_path(root).is_file():
            errors.append(f"required source file is missing: {entry.source}")

    for runtime_directory in manifest.runtime_directories:
        if not _is_child_path(runtime_directory, deployment_root):
            errors.append(f"runtime directory must be under {deployment_root}: {runtime_directory}")

    for excluded_path in manifest.excluded_paths:
        if not _is_child_path(excluded_path, deployment_root):
            errors.append(f"excluded path must be under {deployment_root}: {excluded_path}")

    return PALDeploymentManifestValidation(errors=tuple(errors))


def _manifest_from_payload(
    *,
    path: Path,
    raw_text: str,
    payload: Any,
) -> PALDeploymentManifest:
    if not isinstance(payload, dict):
        raise PALDeploymentManifestError("PAL deployment manifest root must be an object")

    try:
        files_payload = payload["files"]
    except KeyError as exc:
        raise PALDeploymentManifestError("PAL deployment manifest is missing files") from exc
    if not isinstance(files_payload, list):
        raise PALDeploymentManifestError("PAL deployment manifest files must be a list")

    return PALDeploymentManifest(
        manifest_path=path,
        manifest_version=int(payload["manifest_version"]),
        name=str(payload["name"]),
        deployment_root=str(payload["deployment_root"]),
        mode=str(payload["mode"]),
        files=tuple(_file_from_payload(item) for item in files_payload),
        runtime_directories=tuple(str(item) for item in payload.get("runtime_directories", [])),
        excluded_paths=tuple(str(item) for item in payload.get("excluded_paths", [])),
        raw_text=raw_text,
    )


def _file_from_payload(payload: Any) -> PALDeploymentFile:
    if not isinstance(payload, dict):
        raise PALDeploymentManifestError("PAL deployment manifest file entries must be objects")
    try:
        return PALDeploymentFile(
            source=str(payload["source"]),
            target=str(payload["target"]),
            mode=str(payload["mode"]),
            owner=str(payload["owner"]),
            group=str(payload["group"]),
            kind=str(payload["kind"]),
            service_impact=str(payload["service_impact"]),
            required=bool(payload.get("required", True)),
        )
    except KeyError as exc:
        raise PALDeploymentManifestError(f"PAL deployment manifest file entry missing {exc}") from exc


def _is_child_path(candidate: str, root: str) -> bool:
    normalized = PurePosixPath(candidate).as_posix()
    normalized_root = PurePosixPath(root).as_posix().rstrip("/")
    return normalized.startswith(f"{normalized_root}/")


def _valid_relative_source(source: str) -> bool:
    path = PurePosixPath(source)
    return not path.is_absolute() and ".." not in path.parts and bool(path.parts)


def _secret_errors(text: str) -> tuple[str, ...]:
    errors: list[str] = []
    for marker in _SECRET_LITERAL_MARKERS:
        if marker in text:
            errors.append(f"secret marker found in PAL deployment manifest: {marker}")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            errors.append("secret-like value found in PAL deployment manifest")
    return tuple(errors)
