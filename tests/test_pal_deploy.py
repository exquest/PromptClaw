from __future__ import annotations

import argparse
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from promptclaw import cli as promptclaw_cli
from promptclaw.pal_deploy import (
    PALDeploymentManifest,
    PALDeploymentManifestError,
    backup_pal_deployment_changes,
    build_fake_pal_remote_inventory,
    diff_pal_deployment,
    load_pal_deployment_manifest,
    validate_pal_deployment_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PAL_PROJECT_ROOT = REPO_ROOT / "pal-2026"


def test_default_pal_deployment_manifest_loads_from_repo() -> None:
    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)

    assert manifest.manifest_path == PAL_PROJECT_ROOT / "ops" / "deployment-manifest.json"
    assert manifest.manifest_version == 1
    assert manifest.name == "pal-2026-phase1"
    assert manifest.deployment_root == "/opt/pal"
    assert manifest.mode == "host-managed"
    assert manifest.files
    assert json.dumps(manifest.to_dict(), sort_keys=True)


def test_default_pal_deployment_manifest_lists_intended_opt_pal_files() -> None:
    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)
    managed = {entry.target: entry for entry in manifest.files}

    expected_targets = {
        "/opt/pal/scripts/start_all.sh",
        "/opt/pal/scripts/start_ollama.sh",
        "/opt/pal/scripts/start_router.sh",
        "/opt/pal/scripts/auto_shutdown.sh",
        "/opt/pal/config/shutdown.conf",
        "/opt/pal/router/app.py",
        "/opt/pal/DEPLOYMENT_INFO.md",
        "/opt/pal/router/Dockerfile",
        "/opt/pal/docker-compose.yml",
    }
    assert expected_targets.issubset(set(managed))
    assert managed["/opt/pal/scripts/start_router.sh"].source == "ops/templates/start_router.sh"
    assert managed["/opt/pal/scripts/start_router.sh"].mode == "0755"
    assert managed["/opt/pal/scripts/start_router.sh"].kind == "script"
    assert managed["/opt/pal/scripts/start_router.sh"].service_impact == "router"
    assert managed["/opt/pal/router/app.py"].source == "ops/templates/router-app.py"
    assert managed["/opt/pal/docker-compose.yml"].service_impact == "docker-fallback"


def test_default_pal_deployment_manifest_has_valid_targets_modes_and_sources() -> None:
    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)
    validation = validate_pal_deployment_manifest(manifest, PAL_PROJECT_ROOT)

    assert validation.passed, validation.errors
    assert validation.errors == ()
    assert len({entry.target for entry in manifest.files}) == len(manifest.files)
    for entry in manifest.files:
        assert entry.target.startswith("/opt/pal/")
        assert entry.mode in {"0644", "0755"}
        if entry.required:
            assert entry.source_path(PAL_PROJECT_ROOT).is_file()


def test_default_pal_deployment_manifest_excludes_runtime_state_files() -> None:
    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)
    managed_targets = {entry.target for entry in manifest.files}

    assert "/opt/pal/logs/router.log" not in managed_targets
    assert "/opt/pal/logs/ollama.log" not in managed_targets
    assert "/opt/pal/logs/shutdown.log" not in managed_targets
    assert "/opt/pal/config/override.flag" not in managed_targets
    assert "/opt/pal/ollama" not in managed_targets
    assert "/opt/pal/logs" in manifest.runtime_directories
    assert "/opt/pal/ollama" in manifest.runtime_directories
    assert "/opt/pal/logs/*.log" in manifest.excluded_paths
    assert "/opt/pal/config/override.flag" in manifest.excluded_paths


def test_default_pal_deployment_manifest_contains_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAL_SSH_KEY", "/Users/anthony/.ssh/pal_2026_vast")
    monkeypatch.setenv("VAST_API_KEY", "vast-test-api-key-should-never-persist")
    monkeypatch.setenv("TAILSCALE_AUTH_KEY", "tskey-auth-test-secret")

    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)
    validation = validate_pal_deployment_manifest(manifest, PAL_PROJECT_ROOT)
    raw_manifest = manifest.manifest_path.read_text(encoding="utf-8")
    persisted = json.dumps(manifest.to_dict(), sort_keys=True)

    assert validation.passed, validation.errors
    for forbidden in (
        "PAL_SSH_KEY",
        "VAST_API_KEY",
        "TAILSCALE_AUTH_KEY",
        "tskey-auth-",
        "Authorization",
        "BEGIN OPENSSH PRIVATE KEY",
        "/Users/anthony/.ssh/pal_2026_vast",
        "vast-test-api-key-should-never-persist",
    ):
        assert forbidden not in raw_manifest
        assert forbidden not in persisted


def test_pal_deployment_manifest_validation_rejects_invalid_entries(tmp_path: Path) -> None:
    (tmp_path / "ops" / "templates").mkdir(parents=True)
    (tmp_path / "ops" / "templates" / "file.txt").write_text("managed file\n", encoding="utf-8")
    manifest_path = tmp_path / "ops" / "deployment-manifest.json"
    valid_payload = _valid_manifest_payload()

    cases = [
        (
            {
                **copy.deepcopy(valid_payload),
                "files": [
                    valid_payload["files"][0],
                    {**valid_payload["files"][0], "source": "ops/templates/file.txt"},
                ],
            },
            "duplicate target",
        ),
        (
            {
                **copy.deepcopy(valid_payload),
                "files": [{**valid_payload["files"][0], "target": "/etc/pal/file.txt"}],
            },
            "/opt/pal",
        ),
        (
            {
                **copy.deepcopy(valid_payload),
                "files": [{**valid_payload["files"][0], "mode": "777"}],
            },
            "mode",
        ),
        (
            {
                **copy.deepcopy(valid_payload),
                "operator_note": "PAL_SSH_KEY=/Users/anthony/.ssh/pal_2026_vast",
            },
            "secret",
        ),
    ]

    for payload, match in cases:
        manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with pytest.raises(PALDeploymentManifestError, match=match):
            load_pal_deployment_manifest(tmp_path, manifest_path=manifest_path)


def test_pal_deployment_diff_reports_fake_remote_diff_sets(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/changed.txt": {"content": "remote old\n"},
        "/opt/pal/manual.txt": {"content": "operator managed\n"},
        "/opt/pal/unchanged.txt": {"content": "same\n"},
    })

    diff = diff_pal_deployment(manifest, tmp_path, remote_inventory=remote_inventory)

    assert [entry.target for entry in diff.added] == ["/opt/pal/added.txt"]
    assert [entry.target for entry in diff.changed] == ["/opt/pal/changed.txt"]
    assert [entry.target for entry in diff.missing] == ["/opt/pal/missing.txt"]
    assert [entry.target for entry in diff.unchanged] == ["/opt/pal/unchanged.txt"]
    assert [entry.target for entry in diff.unmanaged_remote] == ["/opt/pal/manual.txt"]
    assert diff.summary_counts == {
        "added": 1,
        "changed": 1,
        "missing": 1,
        "unchanged": 1,
        "unmanaged_remote": 1,
    }
    assert json.dumps(diff.to_dict(), sort_keys=True)


def test_pal_deployment_diff_detects_metadata_only_changes(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/unchanged.txt": {
            "content": "same\n",
            "mode": "0600",
            "owner": "pal",
            "group": "root",
        },
    })

    diff = diff_pal_deployment(manifest, tmp_path, remote_inventory=remote_inventory)

    assert [entry.target for entry in diff.changed] == ["/opt/pal/unchanged.txt"]
    assert diff.changed[0].changed_fields == ("mode", "owner")
    assert diff.changed[0].local_sha256 == diff.changed[0].remote_sha256


def test_pal_deployment_diff_ignores_excluded_runtime_remote_paths(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/config/override.flag": {"content": "skip shutdown\n"},
        "/opt/pal/logs/router.log": {"content": "runtime log\n"},
        "/opt/pal/manual.txt": {"content": "operator managed\n"},
        "/opt/pal/ollama/models/blobs/sha256-aa": {"content": "model blob"},
        "/opt/pal/router/__pycache__/app.cpython-311.pyc": {"content": b"\x00\x01"},
    })

    diff = diff_pal_deployment(manifest, tmp_path, remote_inventory=remote_inventory)

    assert [entry.target for entry in diff.unmanaged_remote] == ["/opt/pal/manual.txt"]


def test_default_pal_deployment_manifest_diff_against_empty_fake_remote_is_json_safe() -> None:
    manifest = load_pal_deployment_manifest(PAL_PROJECT_ROOT)

    diff = diff_pal_deployment(
        manifest,
        PAL_PROJECT_ROOT,
        remote_inventory=build_fake_pal_remote_inventory({}),
    )

    assert len(diff.added) == len(manifest.files)
    assert diff.changed == ()
    assert diff.missing == ()
    assert diff.unchanged == ()
    assert diff.unmanaged_remote == ()
    assert diff.summary_counts["added"] == len(manifest.files)
    assert json.dumps(diff.to_dict(), sort_keys=True)


def test_pal_deploy_backup_primitive_stores_changed_fake_remote_files(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/changed.txt": {"content": "remote old\n"},
        "/opt/pal/manual.txt": {"content": "operator managed\n"},
        "/opt/pal/unchanged.txt": {"content": "same\n", "mode": "0600"},
    })
    backup_root = tmp_path / ".promptclaw" / "pal-deploy" / "backups"

    backup = backup_pal_deployment_changes(
        manifest,
        tmp_path,
        remote_inventory=remote_inventory,
        backup_root=backup_root,
        backup_id="test-backup",
    )

    assert backup.workflow_id == "pal_deploy_backup"
    assert backup.remote_writes is False
    assert [entry.target for entry in backup.entries] == [
        "/opt/pal/changed.txt",
        "/opt/pal/unchanged.txt",
    ]
    assert backup.summary_counts == {"stored": 2}
    assert (
        backup_root / "test-backup" / "files" / "opt" / "pal" / "changed.txt"
    ).read_text(encoding="utf-8") == "remote old\n"
    assert (
        backup_root / "test-backup" / "files" / "opt" / "pal" / "unchanged.txt"
    ).read_text(encoding="utf-8") == "same\n"
    assert not (backup_root / "test-backup" / "files" / "opt" / "pal" / "added.txt").exists()
    assert not (backup_root / "test-backup" / "files" / "opt" / "pal" / "manual.txt").exists()

    manifest_payload = json.loads(
        (backup_root / "test-backup" / "backup-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_payload["workflow_id"] == "pal_deploy_backup"
    assert manifest_payload["backup_id"] == "test-backup"
    assert manifest_payload["summary_counts"] == {"stored": 2}
    assert [entry["target"] for entry in manifest_payload["entries"]] == [
        "/opt/pal/changed.txt",
        "/opt/pal/unchanged.txt",
    ]
    assert manifest_payload["entries"][0]["backup_path"] == "files/opt/pal/changed.txt"
    assert json.dumps(backup.to_dict(), sort_keys=True)


def test_pal_deploy_plan_cli_prints_dry_run_summary_without_remote_writes(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory_path = _write_remote_inventory_snapshot(tmp_path)
    original_inventory = remote_inventory_path.read_text(encoding="utf-8")

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        json=False,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_plan(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL deploy plan: DRY-RUN" in rendered
    assert "dry_run=true remote_writes=false" in rendered
    assert "added=1 changed=1 missing=1 unchanged=1 unmanaged_remote=1" in rendered
    assert "planned_changes=3" in rendered
    assert "service_impacts=none" in rendered
    assert "ADDED /opt/pal/added.txt <- ops/templates/added.txt impact=none" in rendered
    assert "CHANGED /opt/pal/changed.txt <- ops/templates/changed.txt impact=none fields=content_sha256" in rendered
    assert "MISSING /opt/pal/missing.txt <- ops/templates/missing.txt impact=none" in rendered
    assert "UNMANAGED_REMOTE /opt/pal/manual.txt" in rendered
    assert remote_inventory_path.read_text(encoding="utf-8") == original_inventory
    assert not (tmp_path / ".promptclaw").exists()


def test_pal_deploy_plan_cli_json_includes_diff_and_service_impact(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory_path = _write_remote_inventory_snapshot(tmp_path)

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_plan(args)

    assert rc == 0
    payload = json.loads(output.getvalue())
    assert payload["workflow_id"] == "pal_deploy_plan"
    assert payload["dry_run"] is True
    assert payload["remote_writes"] is False
    assert payload["approval_required_for_apply"] is True
    assert payload["manifest"]["name"] == "test-pal-diff"
    assert payload["manifest"]["path"] == str(manifest.manifest_path)
    assert payload["manifest"]["file_count"] == 4
    assert payload["deployment_root"] == "/opt/pal"
    assert payload["remote_inventory_source"] == str(remote_inventory_path)
    assert payload["summary_counts"] == {
        "added": 1,
        "changed": 1,
        "missing": 1,
        "unchanged": 1,
        "unmanaged_remote": 1,
    }
    assert payload["service_impacts"]["none"] == {
        "added": 1,
        "changed": 1,
        "missing": 1,
    }
    assert [entry["target"] for entry in payload["planned_changes"]] == [
        "/opt/pal/added.txt",
        "/opt/pal/changed.txt",
        "/opt/pal/missing.txt",
    ]
    assert payload["planned_changes"][1]["changed_fields"] == ["content_sha256"]
    assert [entry["target"] for entry in payload["unmanaged_remote"]] == ["/opt/pal/manual.txt"]


def test_pal_deploy_plan_parser_has_no_apply_or_approval_surface(tmp_path: Path) -> None:
    remote_inventory_path = tmp_path / "remote-inventory.json"
    parser = promptclaw_cli.build_parser()

    parsed = parser.parse_args([
        "pal",
        "deploy",
        "plan",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
        "--json",
    ])

    assert parsed.pal_command == "deploy"
    assert parsed.pal_deploy_command == "plan"
    assert parsed.project_root == tmp_path
    assert parsed.remote_inventory == remote_inventory_path
    assert parsed.json is True
    assert not hasattr(parsed, "approve")
    assert not hasattr(parsed, "approve_deploy")
    assert not hasattr(parsed, "approve_rollback")
    assert not hasattr(parsed, "apply")


def _valid_manifest_payload() -> dict[str, object]:
    return {
        "manifest_version": 1,
        "name": "test-pal-manifest",
        "deployment_root": "/opt/pal",
        "mode": "host-managed",
        "files": [
            {
                "source": "ops/templates/file.txt",
                "target": "/opt/pal/file.txt",
                "mode": "0644",
                "owner": "root",
                "group": "root",
                "kind": "config",
                "service_impact": "none",
                "required": True,
            }
        ],
        "runtime_directories": ["/opt/pal/logs"],
        "excluded_paths": ["/opt/pal/logs/*.log"],
    }


def _write_diff_manifest_project(tmp_path: Path) -> PALDeploymentManifest:
    templates = tmp_path / "ops" / "templates"
    templates.mkdir(parents=True)
    (templates / "added.txt").write_text("add me\n", encoding="utf-8")
    (templates / "changed.txt").write_text("local new\n", encoding="utf-8")
    (templates / "unchanged.txt").write_text("same\n", encoding="utf-8")
    manifest_path = tmp_path / "ops" / "deployment-manifest.json"
    payload = {
        "manifest_version": 1,
        "name": "test-pal-diff",
        "deployment_root": "/opt/pal",
        "mode": "host-managed",
        "files": [
            _diff_file_entry("ops/templates/added.txt", "/opt/pal/added.txt"),
            _diff_file_entry("ops/templates/changed.txt", "/opt/pal/changed.txt"),
            _diff_file_entry("ops/templates/missing.txt", "/opt/pal/missing.txt", required=False),
            _diff_file_entry("ops/templates/unchanged.txt", "/opt/pal/unchanged.txt"),
        ],
        "runtime_directories": ["/opt/pal/logs", "/opt/pal/ollama"],
        "excluded_paths": [
            "/opt/pal/config/override.flag",
            "/opt/pal/logs/*.log",
            "/opt/pal/ollama/**",
            "/opt/pal/router/__pycache__/**",
        ],
    }
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return load_pal_deployment_manifest(tmp_path, manifest_path=manifest_path)


def _diff_file_entry(source: str, target: str, *, required: bool = True) -> dict[str, object]:
    return {
        "source": source,
        "target": target,
        "mode": "0644",
        "owner": "root",
        "group": "root",
        "kind": "config",
        "service_impact": "none",
        "required": required,
    }


def _write_remote_inventory_snapshot(tmp_path: Path) -> Path:
    remote_inventory_path = tmp_path / "remote-inventory.json"
    remote_inventory_path.write_text(
        json.dumps(
            {
                "/opt/pal/changed.txt": {"content": "remote old\n"},
                "/opt/pal/manual.txt": {"content": "operator managed\n"},
                "/opt/pal/unchanged.txt": {"content": "same\n"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return remote_inventory_path
