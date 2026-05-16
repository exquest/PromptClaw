from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


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


@dataclass(frozen=True)
class PALDeploymentLocalFile:
    source: str
    target: str
    mode: str
    owner: str
    group: str
    kind: str
    service_impact: str
    required: bool
    exists: bool
    sha256: str | None
    size_bytes: int | None

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
            "exists": self.exists,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class PALDeploymentRemoteFile:
    target: str
    exists: bool
    sha256: str | None
    mode: str | None
    owner: str | None
    group: str | None
    size_bytes: int | None
    source: str = "fake-remote"
    content_bytes: bytes | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "exists": self.exists,
            "sha256": self.sha256,
            "mode": self.mode,
            "owner": self.owner,
            "group": self.group,
            "size_bytes": self.size_bytes,
            "source": self.source,
            "content_available": self.content_bytes is not None,
        }


@dataclass(frozen=True)
class PALDeploymentDiffEntry:
    target: str
    status: str
    source: str | None
    kind: str | None
    service_impact: str | None
    local_sha256: str | None
    remote_sha256: str | None
    local_mode: str | None
    remote_mode: str | None
    local_owner: str | None
    remote_owner: str | None
    local_group: str | None
    remote_group: str | None
    changed_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "status": self.status,
            "source": self.source,
            "kind": self.kind,
            "service_impact": self.service_impact,
            "local_sha256": self.local_sha256,
            "remote_sha256": self.remote_sha256,
            "local_mode": self.local_mode,
            "remote_mode": self.remote_mode,
            "local_owner": self.local_owner,
            "remote_owner": self.remote_owner,
            "local_group": self.local_group,
            "remote_group": self.remote_group,
            "changed_fields": list(self.changed_fields),
        }


@dataclass(frozen=True)
class PALDeploymentDiff:
    manifest_path: Path
    deployment_root: str
    added: tuple[PALDeploymentDiffEntry, ...]
    changed: tuple[PALDeploymentDiffEntry, ...]
    missing: tuple[PALDeploymentDiffEntry, ...]
    unchanged: tuple[PALDeploymentDiffEntry, ...]
    unmanaged_remote: tuple[PALDeploymentDiffEntry, ...]

    @property
    def summary_counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "changed": len(self.changed),
            "missing": len(self.missing),
            "unchanged": len(self.unchanged),
            "unmanaged_remote": len(self.unmanaged_remote),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "deployment_root": self.deployment_root,
            "summary_counts": self.summary_counts,
            "added": [entry.to_dict() for entry in self.added],
            "changed": [entry.to_dict() for entry in self.changed],
            "missing": [entry.to_dict() for entry in self.missing],
            "unchanged": [entry.to_dict() for entry in self.unchanged],
            "unmanaged_remote": [entry.to_dict() for entry in self.unmanaged_remote],
        }


@dataclass(frozen=True)
class PALDeploymentPlan:
    manifest: PALDeploymentManifest
    diff: PALDeploymentDiff
    remote_inventory_source: str
    workflow_id: str = "pal_deploy_plan"
    dry_run: bool = True
    remote_writes: bool = False
    approval_required_for_apply: bool = True

    @property
    def planned_changes(self) -> tuple[PALDeploymentDiffEntry, ...]:
        return self.diff.added + self.diff.changed + self.diff.missing

    @property
    def service_impacts(self) -> dict[str, dict[str, int]]:
        impacts: dict[str, dict[str, int]] = {}
        for status, entries in (
            ("added", self.diff.added),
            ("changed", self.diff.changed),
            ("missing", self.diff.missing),
        ):
            for entry in entries:
                impact = entry.service_impact or "unknown"
                impacts.setdefault(impact, {})
                impacts[impact][status] = impacts[impact].get(status, 0) + 1
        return {impact: impacts[impact] for impact in sorted(impacts)}

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "dry_run": self.dry_run,
            "remote_writes": self.remote_writes,
            "approval_required_for_apply": self.approval_required_for_apply,
            "manifest": {
                "path": str(self.manifest.manifest_path),
                "name": self.manifest.name,
                "mode": self.manifest.mode,
                "file_count": len(self.manifest.files),
            },
            "deployment_root": self.manifest.deployment_root,
            "remote_inventory_source": self.remote_inventory_source,
            "summary_counts": self.diff.summary_counts,
            "service_impacts": self.service_impacts,
            "planned_changes": [entry.to_dict() for entry in self.planned_changes],
            "unchanged": [entry.to_dict() for entry in self.diff.unchanged],
            "unmanaged_remote": [entry.to_dict() for entry in self.diff.unmanaged_remote],
        }


@dataclass(frozen=True)
class PALDeploymentBackupEntry:
    target: str
    status: str
    backup_path: str
    remote_sha256: str | None
    remote_mode: str | None
    remote_owner: str | None
    remote_group: str | None
    size_bytes: int | None
    changed_fields: tuple[str, ...]
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "status": self.status,
            "backup_path": self.backup_path,
            "remote_sha256": self.remote_sha256,
            "remote_mode": self.remote_mode,
            "remote_owner": self.remote_owner,
            "remote_group": self.remote_group,
            "size_bytes": self.size_bytes,
            "changed_fields": list(self.changed_fields),
            "source": self.source,
        }


@dataclass(frozen=True)
class PALDeploymentBackup:
    backup_id: str
    backup_path: Path
    manifest_path: Path
    deployment_root: str
    entries: tuple[PALDeploymentBackupEntry, ...]
    workflow_id: str = "pal_deploy_backup"
    remote_writes: bool = False

    @property
    def summary_counts(self) -> dict[str, int]:
        return {"stored": len(self.entries)}

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "backup_id": self.backup_id,
            "backup_path": str(self.backup_path),
            "manifest_path": str(self.manifest_path),
            "deployment_root": self.deployment_root,
            "remote_writes": self.remote_writes,
            "summary_counts": self.summary_counts,
            "entries": [entry.to_dict() for entry in self.entries],
        }


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


def build_fake_pal_remote_inventory(
    files: Mapping[str, object],
    *,
    default_mode: str = "0644",
    default_owner: str = "root",
    default_group: str = "root",
) -> tuple[PALDeploymentRemoteFile, ...]:
    """Build deterministic remote file snapshots for deploy diff tests."""
    remote_files: list[PALDeploymentRemoteFile] = []
    for target in sorted(files):
        value = files[target]
        if isinstance(value, PALDeploymentRemoteFile):
            remote_files.append(value)
            continue
        if isinstance(value, Mapping):
            content = value.get("content", "")
            exists = bool(value.get("exists", True))
            mode = str(value.get("mode", default_mode)) if exists else None
            owner = str(value.get("owner", default_owner)) if exists else None
            group = str(value.get("group", default_group)) if exists else None
            source = str(value.get("source", "fake-remote"))
        else:
            content = value
            exists = True
            mode = default_mode
            owner = default_owner
            group = default_group
            source = "fake-remote"
        content_bytes = _coerce_content_bytes(content) if exists else None
        remote_files.append(
            PALDeploymentRemoteFile(
                target=target,
                exists=exists,
                sha256=_sha256_bytes(content_bytes) if content_bytes is not None else None,
                mode=mode,
                owner=owner,
                group=group,
                size_bytes=len(content_bytes) if content_bytes is not None else None,
                source=source,
                content_bytes=content_bytes,
            )
        )
    return tuple(remote_files)


def load_pal_remote_inventory_snapshot(path: Path) -> tuple[PALDeploymentRemoteFile, ...]:
    """Load a local JSON remote-inventory snapshot for dry-run planning."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PALDeploymentManifestError(f"Malformed PAL remote inventory JSON: {path}") from exc
    return _remote_inventory_from_payload(payload)


def diff_pal_deployment(
    manifest: PALDeploymentManifest,
    project_root: Path,
    *,
    remote_inventory: Iterable[PALDeploymentRemoteFile],
) -> PALDeploymentDiff:
    """Compare manifest-managed local files against a remote inventory."""
    local_files = tuple(
        _local_file_from_manifest_entry(entry, project_root.resolve()) for entry in manifest.files
    )
    managed_targets = {entry.target for entry in local_files}
    remote_by_target = {
        entry.target: entry
        for entry in sorted(remote_inventory, key=lambda item: item.target)
        if entry.exists
    }

    added: list[PALDeploymentDiffEntry] = []
    changed: list[PALDeploymentDiffEntry] = []
    missing: list[PALDeploymentDiffEntry] = []
    unchanged: list[PALDeploymentDiffEntry] = []

    for local_file in sorted(local_files, key=lambda item: item.target):
        remote_file = remote_by_target.get(local_file.target)
        if not local_file.exists:
            missing.append(_diff_entry(local_file, remote_file, status="missing"))
        elif remote_file is None:
            added.append(_diff_entry(local_file, None, status="added"))
        else:
            changed_fields = _changed_fields(local_file, remote_file)
            if changed_fields:
                changed.append(
                    _diff_entry(
                        local_file,
                        remote_file,
                        status="changed",
                        changed_fields=changed_fields,
                    )
                )
            else:
                unchanged.append(_diff_entry(local_file, remote_file, status="unchanged"))

    unmanaged_remote = tuple(
        _remote_only_diff_entry(remote_file)
        for remote_file in sorted(remote_by_target.values(), key=lambda item: item.target)
        if remote_file.target not in managed_targets
        and not _matches_excluded_path(remote_file.target, manifest.excluded_paths)
    )

    return PALDeploymentDiff(
        manifest_path=manifest.manifest_path,
        deployment_root=manifest.deployment_root,
        added=tuple(added),
        changed=tuple(changed),
        missing=tuple(missing),
        unchanged=tuple(unchanged),
        unmanaged_remote=unmanaged_remote,
    )


def backup_pal_deployment_changes(
    manifest: PALDeploymentManifest,
    project_root: Path,
    *,
    remote_inventory: Iterable[PALDeploymentRemoteFile],
    backup_root: Path,
    backup_id: str,
) -> PALDeploymentBackup:
    """Store existing remote bytes for changed managed PAL deployment files."""
    remote_files = tuple(remote_inventory)
    diff = diff_pal_deployment(manifest, project_root, remote_inventory=remote_files)
    remote_by_target = {entry.target: entry for entry in remote_files if entry.exists}

    backup_path = backup_root / backup_id
    files_root = backup_path / "files"
    entries: list[PALDeploymentBackupEntry] = []
    for diff_entry in diff.changed:
        remote_file = remote_by_target[diff_entry.target]
        if remote_file.content_bytes is None:
            raise PALDeploymentManifestError(
                f"changed remote file has no backup content: {diff_entry.target}"
            )
        relative_target = _backup_relative_target_path(diff_entry.target)
        relative_backup_path = PurePosixPath("files", relative_target.as_posix())
        output_path = files_root / Path(relative_target.as_posix())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(remote_file.content_bytes)
        entries.append(
            PALDeploymentBackupEntry(
                target=diff_entry.target,
                status=diff_entry.status,
                backup_path=relative_backup_path.as_posix(),
                remote_sha256=remote_file.sha256,
                remote_mode=remote_file.mode,
                remote_owner=remote_file.owner,
                remote_group=remote_file.group,
                size_bytes=remote_file.size_bytes,
                changed_fields=diff_entry.changed_fields,
                source=remote_file.source,
            )
        )

    backup_path.mkdir(parents=True, exist_ok=True)
    backup = PALDeploymentBackup(
        backup_id=backup_id,
        backup_path=backup_path,
        manifest_path=manifest.manifest_path,
        deployment_root=manifest.deployment_root,
        entries=tuple(entries),
    )
    (backup_path / "backup-manifest.json").write_text(
        json.dumps(backup.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return backup


def build_pal_deploy_plan(
    project_root: Path,
    *,
    manifest_path: Path | None = None,
    remote_inventory: Iterable[PALDeploymentRemoteFile] = (),
    remote_inventory_source: str = "empty",
) -> PALDeploymentPlan:
    """Build a stdout-safe dry-run PAL deployment plan with no remote writes."""
    manifest = load_pal_deployment_manifest(project_root, manifest_path=manifest_path)
    diff = diff_pal_deployment(
        manifest,
        project_root,
        remote_inventory=remote_inventory,
    )
    return PALDeploymentPlan(
        manifest=manifest,
        diff=diff,
        remote_inventory_source=remote_inventory_source,
    )


def format_pal_deploy_plan(plan: PALDeploymentPlan) -> str:
    """Render a concise human-readable dry-run deploy plan."""
    counts = plan.diff.summary_counts
    impact_names = ",".join(plan.service_impacts) or "none"
    lines = [
        f"PAL deploy plan: DRY-RUN manifest={plan.manifest.manifest_path} root={plan.manifest.deployment_root}",
        (
            f"dry_run={str(plan.dry_run).lower()} "
            f"remote_writes={str(plan.remote_writes).lower()} "
            f"approval_required_for_apply={str(plan.approval_required_for_apply).lower()}"
        ),
        (
            "summary "
            f"added={counts['added']} "
            f"changed={counts['changed']} "
            f"missing={counts['missing']} "
            f"unchanged={counts['unchanged']} "
            f"unmanaged_remote={counts['unmanaged_remote']}"
        ),
        f"planned_changes={len(plan.planned_changes)} service_impacts={impact_names}",
        "planned file changes:",
    ]
    if plan.planned_changes:
        for entry in plan.planned_changes:
            fields = ",".join(entry.changed_fields) or "none"
            lines.append(
                f"- {entry.status.upper()} {entry.target} <- {entry.source} "
                f"impact={entry.service_impact or 'unknown'} fields={fields}"
            )
    else:
        lines.append("- none")

    lines.append("unmanaged remote files:")
    if plan.diff.unmanaged_remote:
        for entry in plan.diff.unmanaged_remote:
            lines.append(f"- {entry.status.upper()} {entry.target}")
    else:
        lines.append("- none")
    return "\n".join(lines)


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


def _remote_inventory_from_payload(payload: Any) -> tuple[PALDeploymentRemoteFile, ...]:
    if isinstance(payload, list):
        return tuple(_remote_file_from_payload(item) for item in payload)
    if isinstance(payload, dict):
        if "target" in payload:
            return (_remote_file_from_payload(payload),)
        files_payload = payload.get("files", payload)
        if isinstance(files_payload, list):
            return tuple(_remote_file_from_payload(item) for item in files_payload)
        if isinstance(files_payload, dict):
            return build_fake_pal_remote_inventory(files_payload)
    raise PALDeploymentManifestError("PAL remote inventory must be a list, target map, or object with files")


def _remote_file_from_payload(payload: Any) -> PALDeploymentRemoteFile:
    if not isinstance(payload, dict):
        raise PALDeploymentManifestError("PAL remote inventory entries must be objects")
    if "content" in payload:
        target = str(payload.get("target", ""))
        if not target:
            raise PALDeploymentManifestError("PAL remote inventory content entry missing target")
        return build_fake_pal_remote_inventory({target: payload})[0]
    try:
        exists = bool(payload.get("exists", True))
        return PALDeploymentRemoteFile(
            target=str(payload["target"]),
            exists=exists,
            sha256=str(payload["sha256"]) if payload.get("sha256") is not None else None,
            mode=str(payload["mode"]) if exists and payload.get("mode") is not None else None,
            owner=str(payload["owner"]) if exists and payload.get("owner") is not None else None,
            group=str(payload["group"]) if exists and payload.get("group") is not None else None,
            size_bytes=int(payload["size_bytes"]) if exists and payload.get("size_bytes") is not None else None,
            source=str(payload.get("source", "local-snapshot")),
        )
    except KeyError as exc:
        raise PALDeploymentManifestError(f"PAL remote inventory entry missing {exc}") from exc


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


def _local_file_from_manifest_entry(
    entry: PALDeploymentFile,
    project_root: Path,
) -> PALDeploymentLocalFile:
    source_path = entry.source_path(project_root)
    if not source_path.is_file():
        return PALDeploymentLocalFile(
            source=entry.source,
            target=entry.target,
            mode=entry.mode,
            owner=entry.owner,
            group=entry.group,
            kind=entry.kind,
            service_impact=entry.service_impact,
            required=entry.required,
            exists=False,
            sha256=None,
            size_bytes=None,
        )
    content = source_path.read_bytes()
    return PALDeploymentLocalFile(
        source=entry.source,
        target=entry.target,
        mode=entry.mode,
        owner=entry.owner,
        group=entry.group,
        kind=entry.kind,
        service_impact=entry.service_impact,
        required=entry.required,
        exists=True,
        sha256=_sha256_bytes(content),
        size_bytes=len(content),
    )


def _diff_entry(
    local_file: PALDeploymentLocalFile,
    remote_file: PALDeploymentRemoteFile | None,
    *,
    status: str,
    changed_fields: tuple[str, ...] = (),
) -> PALDeploymentDiffEntry:
    return PALDeploymentDiffEntry(
        target=local_file.target,
        status=status,
        source=local_file.source,
        kind=local_file.kind,
        service_impact=local_file.service_impact,
        local_sha256=local_file.sha256,
        remote_sha256=remote_file.sha256 if remote_file else None,
        local_mode=local_file.mode,
        remote_mode=remote_file.mode if remote_file else None,
        local_owner=local_file.owner,
        remote_owner=remote_file.owner if remote_file else None,
        local_group=local_file.group,
        remote_group=remote_file.group if remote_file else None,
        changed_fields=changed_fields,
    )


def _remote_only_diff_entry(remote_file: PALDeploymentRemoteFile) -> PALDeploymentDiffEntry:
    return PALDeploymentDiffEntry(
        target=remote_file.target,
        status="unmanaged_remote",
        source=None,
        kind=None,
        service_impact=None,
        local_sha256=None,
        remote_sha256=remote_file.sha256,
        local_mode=None,
        remote_mode=remote_file.mode,
        local_owner=None,
        remote_owner=remote_file.owner,
        local_group=None,
        remote_group=remote_file.group,
    )


def _changed_fields(
    local_file: PALDeploymentLocalFile,
    remote_file: PALDeploymentRemoteFile,
) -> tuple[str, ...]:
    fields: list[str] = []
    if local_file.sha256 != remote_file.sha256:
        fields.append("content_sha256")
    if local_file.mode != remote_file.mode:
        fields.append("mode")
    if local_file.owner != remote_file.owner:
        fields.append("owner")
    if local_file.group != remote_file.group:
        fields.append("group")
    return tuple(fields)


def _matches_excluded_path(target: str, excluded_paths: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(target, pattern) for pattern in excluded_paths)


def _backup_relative_target_path(target: str) -> PurePosixPath:
    path = PurePosixPath(target)
    if not path.is_absolute() or ".." in path.parts:
        raise PALDeploymentManifestError(f"unsafe PAL backup target path: {target}")
    parts = tuple(part for part in path.parts if part != "/")
    if not parts:
        raise PALDeploymentManifestError(f"unsafe PAL backup target path: {target}")
    return PurePosixPath(*parts)


def _coerce_content_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"fake PAL remote content must be str or bytes, got {type(value).__name__}")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
