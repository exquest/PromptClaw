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
    PALDeploymentMetadata,
    backup_pal_deployment_changes,
    build_fake_pal_remote_inventory,
    compute_pal_cost_burn,
    diff_pal_deployment,
    load_pal_deployment_manifest,
    load_pal_remote_inventory_snapshot,
    rollback_pal_deployment_backup,
    validate_pal_deployment_manifest,
    write_pal_remote_inventory_snapshot,
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


def test_pal_deploy_rollback_primitive_restores_backed_up_fake_remote_files(
    tmp_path: Path,
) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    original_remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/changed.txt": {
            "content": "remote old\n",
            "mode": "0600",
            "owner": "pal",
            "group": "pal",
        },
        "/opt/pal/manual.txt": {"content": "operator managed\n"},
        "/opt/pal/unchanged.txt": {
            "content": "same\n",
            "mode": "0600",
            "owner": "pal",
            "group": "pal",
        },
    })
    backup_root = tmp_path / ".promptclaw" / "pal-deploy" / "backups"
    backup = backup_pal_deployment_changes(
        manifest,
        tmp_path,
        remote_inventory=original_remote_inventory,
        backup_root=backup_root,
        backup_id="test-rollback",
    )
    remote_inventory_path = tmp_path / "remote-inventory.json"
    write_pal_remote_inventory_snapshot(
        remote_inventory_path,
        build_fake_pal_remote_inventory({
            "/opt/pal/added.txt": {"content": "add me\n", "source": "fake-apply"},
            "/opt/pal/changed.txt": {"content": "local new\n", "source": "fake-apply"},
            "/opt/pal/manual.txt": {"content": "operator managed\n"},
            "/opt/pal/unchanged.txt": {"content": "same\n", "source": "fake-apply"},
        }),
    )

    rollback = rollback_pal_deployment_backup(
        backup,
        remote_inventory=load_pal_remote_inventory_snapshot(remote_inventory_path),
        remote_inventory_path=remote_inventory_path,
        approved=True,
    )

    assert rollback.workflow_id == "pal_deploy_rollback"
    assert rollback.status == "complete"
    assert rollback.approved is True
    assert rollback.remote_writes is True
    assert rollback.live_ssh is False
    assert rollback.service_restarts is False
    assert rollback.summary_counts == {"restored": 2}
    assert [entry.target for entry in rollback.restored_entries] == [
        "/opt/pal/changed.txt",
        "/opt/pal/unchanged.txt",
    ]
    assert [entry.backup_path for entry in rollback.restored_entries] == [
        "files/opt/pal/changed.txt",
        "files/opt/pal/unchanged.txt",
    ]
    assert json.dumps(rollback.to_dict(), sort_keys=True)

    snapshot = json.loads(remote_inventory_path.read_text(encoding="utf-8"))
    assert snapshot["/opt/pal/changed.txt"]["content"] == "remote old\n"
    assert snapshot["/opt/pal/changed.txt"]["mode"] == "0600"
    assert snapshot["/opt/pal/changed.txt"]["owner"] == "pal"
    assert snapshot["/opt/pal/changed.txt"]["group"] == "pal"
    assert snapshot["/opt/pal/changed.txt"]["source"] == "pal-deploy-rollback"
    assert snapshot["/opt/pal/unchanged.txt"]["content"] == "same\n"
    assert snapshot["/opt/pal/unchanged.txt"]["mode"] == "0600"
    assert snapshot["/opt/pal/unchanged.txt"]["owner"] == "pal"
    assert snapshot["/opt/pal/unchanged.txt"]["group"] == "pal"
    assert snapshot["/opt/pal/added.txt"]["content"] == "add me\n"
    assert snapshot["/opt/pal/manual.txt"]["content"] == "operator managed\n"


def test_pal_deploy_rollback_primitive_requires_explicit_approval(tmp_path: Path) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    original_remote_inventory = build_fake_pal_remote_inventory({
        "/opt/pal/changed.txt": {"content": "remote old\n"},
    })
    backup = backup_pal_deployment_changes(
        manifest,
        tmp_path,
        remote_inventory=original_remote_inventory,
        backup_root=tmp_path / ".promptclaw" / "pal-deploy" / "backups",
        backup_id="test-rollback-rejected",
    )
    remote_inventory_path = tmp_path / "remote-inventory.json"
    write_pal_remote_inventory_snapshot(
        remote_inventory_path,
        build_fake_pal_remote_inventory({
            "/opt/pal/changed.txt": {"content": "local new\n", "source": "fake-apply"},
        }),
    )
    original_snapshot = remote_inventory_path.read_text(encoding="utf-8")

    with pytest.raises(PALDeploymentManifestError, match="--approve-rollback"):
        rollback_pal_deployment_backup(
            backup,
            remote_inventory=load_pal_remote_inventory_snapshot(remote_inventory_path),
            remote_inventory_path=remote_inventory_path,
            approved=False,
        )

    assert remote_inventory_path.read_text(encoding="utf-8") == original_snapshot


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


def test_pal_deploy_apply_parser_exposes_explicit_approval_flag(tmp_path: Path) -> None:
    remote_inventory_path = tmp_path / "remote-inventory.json"
    parser = promptclaw_cli.build_parser()

    parsed_without_approval = parser.parse_args([
        "pal",
        "deploy",
        "apply",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
    ])
    parsed_with_approval = parser.parse_args([
        "pal",
        "deploy",
        "apply",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
        "--approve-apply",
        "--json",
    ])

    assert parsed_without_approval.pal_command == "deploy"
    assert parsed_without_approval.pal_deploy_command == "apply"
    assert parsed_without_approval.project_root == tmp_path
    assert parsed_without_approval.remote_inventory == remote_inventory_path
    assert parsed_without_approval.approve_apply is False
    assert parsed_without_approval.json is False
    assert parsed_with_approval.approve_apply is True
    assert parsed_with_approval.json is True
    assert not hasattr(parsed_with_approval, "approve_rollback")


def test_pal_deploy_apply_cli_requires_approval_flag_for_fake_remote_writes(
    tmp_path: Path,
) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory_path = _write_remote_inventory_snapshot(tmp_path)
    original_inventory = remote_inventory_path.read_text(encoding="utf-8")

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        backup_id="rejected-apply",
        approve_apply=False,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_apply(args)

    assert rc == 1
    payload = json.loads(output.getvalue())
    assert payload["workflow_id"] == "pal_deploy_apply"
    assert payload["status"] == "rejected"
    assert payload["approved"] is False
    assert payload["remote_writes"] is False
    assert payload["live_ssh"] is False
    assert payload["service_restarts"] is False
    assert "--approve-apply" in payload["reason"]
    assert payload["remote_inventory_path"] == str(remote_inventory_path)
    assert remote_inventory_path.read_text(encoding="utf-8") == original_inventory
    assert not (tmp_path / ".promptclaw").exists()


def test_pal_deploy_apply_cli_writes_approved_fake_remote_inventory_and_backup(
    tmp_path: Path,
) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    remote_inventory_path = _write_remote_inventory_snapshot(tmp_path)

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        backup_id="test-apply",
        approve_apply=True,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_apply(args)

    assert rc == 0
    payload = json.loads(output.getvalue())
    assert payload["workflow_id"] == "pal_deploy_apply"
    assert payload["status"] == "complete"
    assert payload["approved"] is True
    assert payload["remote_writes"] is True
    assert payload["live_ssh"] is False
    assert payload["service_restarts"] is False
    assert payload["remote_inventory_path"] == str(remote_inventory_path)
    assert payload["backup"]["backup_id"] == "test-apply"
    assert payload["summary_counts"] == {
        "applied": 2,
        "backed_up": 1,
        "skipped": 1,
        "unmanaged_remote": 1,
    }
    assert [entry["target"] for entry in payload["applied_entries"]] == [
        "/opt/pal/added.txt",
        "/opt/pal/changed.txt",
    ]
    assert [entry["status"] for entry in payload["applied_entries"]] == ["added", "changed"]
    assert [entry["target"] for entry in payload["skipped_entries"]] == ["/opt/pal/missing.txt"]

    snapshot = json.loads(remote_inventory_path.read_text(encoding="utf-8"))
    assert snapshot["/opt/pal/added.txt"]["content"] == "add me\n"
    assert snapshot["/opt/pal/changed.txt"]["content"] == "local new\n"
    assert snapshot["/opt/pal/changed.txt"]["mode"] == "0644"
    assert snapshot["/opt/pal/manual.txt"]["content"] == "operator managed\n"
    assert "/opt/pal/missing.txt" not in snapshot

    backup_file = (
        tmp_path
        / ".promptclaw"
        / "pal-deploy"
        / "backups"
        / "test-apply"
        / "files"
        / "opt"
        / "pal"
        / "changed.txt"
    )
    assert backup_file.read_text(encoding="utf-8") == "remote old\n"

    post_apply_diff = diff_pal_deployment(
        manifest,
        tmp_path,
        remote_inventory=load_pal_remote_inventory_snapshot(remote_inventory_path),
    )
    assert post_apply_diff.summary_counts == {
        "added": 0,
        "changed": 0,
        "missing": 1,
        "unchanged": 3,
        "unmanaged_remote": 1,
    }


def test_pal_deploy_rollback_parser_exposes_explicit_approval_flag(tmp_path: Path) -> None:
    remote_inventory_path = tmp_path / "remote-inventory.json"
    parser = promptclaw_cli.build_parser()

    parsed_without_approval = parser.parse_args([
        "pal",
        "deploy",
        "rollback",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
        "--backup-id",
        "test-rollback",
    ])
    parsed_with_approval = parser.parse_args([
        "pal",
        "deploy",
        "rollback",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
        "--backup-id",
        "test-rollback",
        "--approve-rollback",
        "--json",
    ])

    assert parsed_without_approval.pal_command == "deploy"
    assert parsed_without_approval.pal_deploy_command == "rollback"
    assert parsed_without_approval.project_root == tmp_path
    assert parsed_without_approval.remote_inventory == remote_inventory_path
    assert parsed_without_approval.backup_id == "test-rollback"
    assert parsed_without_approval.approve_rollback is False
    assert parsed_without_approval.json is False
    assert parsed_with_approval.approve_rollback is True
    assert parsed_with_approval.json is True
    assert not hasattr(parsed_with_approval, "approve_apply")


def test_pal_deploy_rollback_cli_requires_approval_flag_for_fake_remote_writes(
    tmp_path: Path,
) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    backup_root = tmp_path / ".promptclaw" / "pal-deploy" / "backups"
    backup_pal_deployment_changes(
        manifest,
        tmp_path,
        remote_inventory=build_fake_pal_remote_inventory({
            "/opt/pal/changed.txt": {"content": "remote old\n"},
        }),
        backup_root=backup_root,
        backup_id="test-rollback-rejected",
    )
    remote_inventory_path = tmp_path / "remote-inventory.json"
    write_pal_remote_inventory_snapshot(
        remote_inventory_path,
        build_fake_pal_remote_inventory({
            "/opt/pal/changed.txt": {"content": "local new\n", "source": "fake-apply"},
        }),
    )
    original_inventory = remote_inventory_path.read_text(encoding="utf-8")

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        backup_id="test-rollback-rejected",
        approve_rollback=False,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_rollback(args)

    assert rc == 1
    payload = json.loads(output.getvalue())
    assert payload["workflow_id"] == "pal_deploy_rollback"
    assert payload["status"] == "rejected"
    assert payload["approved"] is False
    assert payload["remote_writes"] is False
    assert payload["live_ssh"] is False
    assert payload["service_restarts"] is False
    assert "--approve-rollback" in payload["reason"]
    assert payload["backup_id"] == "test-rollback-rejected"
    assert payload["remote_inventory_path"] == str(remote_inventory_path)
    assert remote_inventory_path.read_text(encoding="utf-8") == original_inventory


def test_pal_deploy_rollback_cli_restores_approved_fake_remote_inventory(
    tmp_path: Path,
) -> None:
    manifest = _write_diff_manifest_project(tmp_path)
    backup_root = tmp_path / ".promptclaw" / "pal-deploy" / "backups"
    backup_pal_deployment_changes(
        manifest,
        tmp_path,
        remote_inventory=build_fake_pal_remote_inventory({
            "/opt/pal/changed.txt": {
                "content": "remote old\n",
                "mode": "0600",
                "owner": "pal",
                "group": "pal",
            },
            "/opt/pal/manual.txt": {"content": "operator managed\n"},
            "/opt/pal/unchanged.txt": {
                "content": "same\n",
                "mode": "0600",
                "owner": "pal",
                "group": "pal",
            },
        }),
        backup_root=backup_root,
        backup_id="test-rollback-cli",
    )
    remote_inventory_path = tmp_path / "remote-inventory.json"
    write_pal_remote_inventory_snapshot(
        remote_inventory_path,
        build_fake_pal_remote_inventory({
            "/opt/pal/added.txt": {"content": "add me\n", "source": "fake-apply"},
            "/opt/pal/changed.txt": {"content": "local new\n", "source": "fake-apply"},
            "/opt/pal/manual.txt": {"content": "operator managed\n"},
            "/opt/pal/unchanged.txt": {"content": "same\n", "source": "fake-apply"},
        }),
    )

    output = io.StringIO()
    args = argparse.Namespace(
        project_root=tmp_path,
        manifest=manifest.manifest_path,
        remote_inventory=remote_inventory_path,
        backup_id="test-rollback-cli",
        approve_rollback=True,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_deploy_rollback(args)

    assert rc == 0
    payload = json.loads(output.getvalue())
    assert payload["workflow_id"] == "pal_deploy_rollback"
    assert payload["status"] == "complete"
    assert payload["approved"] is True
    assert payload["remote_writes"] is True
    assert payload["live_ssh"] is False
    assert payload["service_restarts"] is False
    assert payload["backup_id"] == "test-rollback-cli"
    assert payload["remote_inventory_path"] == str(remote_inventory_path)
    assert payload["summary_counts"] == {"restored": 2}
    assert [entry["target"] for entry in payload["restored_entries"]] == [
        "/opt/pal/changed.txt",
        "/opt/pal/unchanged.txt",
    ]

    snapshot = json.loads(remote_inventory_path.read_text(encoding="utf-8"))
    assert snapshot["/opt/pal/changed.txt"]["content"] == "remote old\n"
    assert snapshot["/opt/pal/changed.txt"]["mode"] == "0600"
    assert snapshot["/opt/pal/changed.txt"]["owner"] == "pal"
    assert snapshot["/opt/pal/changed.txt"]["group"] == "pal"
    assert snapshot["/opt/pal/changed.txt"]["source"] == "pal-deploy-rollback"
    assert snapshot["/opt/pal/unchanged.txt"]["content"] == "same\n"
    assert snapshot["/opt/pal/unchanged.txt"]["mode"] == "0600"
    assert snapshot["/opt/pal/unchanged.txt"]["owner"] == "pal"
    assert snapshot["/opt/pal/unchanged.txt"]["group"] == "pal"
    assert snapshot["/opt/pal/added.txt"]["content"] == "add me\n"
    assert snapshot["/opt/pal/manual.txt"]["content"] == "operator managed\n"


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


def test_pal_deployment_metadata_stores_rate_runtime_and_optional_vast_instance() -> None:
    full = PALDeploymentMetadata(
        hourly_rate_usd=0.55,
        runtime_estimate_hours=4.0,
        vast_instance_id="vast-12345",
    )
    minimal = PALDeploymentMetadata(
        hourly_rate_usd=0.40,
        runtime_estimate_hours=2.5,
    )

    assert full.hourly_rate_usd == 0.55
    assert full.runtime_estimate_hours == 4.0
    assert full.vast_instance_id == "vast-12345"
    assert full.estimated_cost_usd == pytest.approx(2.2)
    assert full.to_dict() == {
        "hourly_rate_usd": 0.55,
        "runtime_estimate_hours": 4.0,
        "vast_instance_id": "vast-12345",
    }

    assert minimal.vast_instance_id is None
    assert minimal.to_dict()["vast_instance_id"] is None
    assert minimal.estimated_cost_usd == pytest.approx(1.0)

    with pytest.raises(ValueError, match="hourly_rate_usd"):
        PALDeploymentMetadata(hourly_rate_usd=-0.01, runtime_estimate_hours=1.0)
    with pytest.raises(ValueError, match="runtime_estimate_hours"):
        PALDeploymentMetadata(hourly_rate_usd=0.50, runtime_estimate_hours=-1.0)


def test_compute_pal_cost_burn_projects_hourly_daily_and_monthly() -> None:
    burn = compute_pal_cost_burn(0.55, vast_instance_id="vast-12345")

    assert burn.hourly_rate_usd == pytest.approx(0.55)
    assert burn.daily_burn_usd == pytest.approx(0.55 * 24)
    assert burn.monthly_burn_usd == pytest.approx(0.55 * 24 * 30)
    assert burn.vast_instance_id == "vast-12345"
    assert burn.to_dict() == {
        "hourly_rate_usd": pytest.approx(0.55),
        "daily_burn_usd": pytest.approx(0.55 * 24),
        "monthly_burn_usd": pytest.approx(0.55 * 24 * 30),
        "monthly_days": 30,
        "vast_instance_id": "vast-12345",
    }

    minimal = compute_pal_cost_burn(0.0)
    assert minimal.vast_instance_id is None
    assert minimal.daily_burn_usd == 0.0
    assert minimal.monthly_burn_usd == 0.0

    with pytest.raises(ValueError, match="hourly_rate_usd"):
        compute_pal_cost_burn(-0.01)


def test_pal_cost_cli_prints_hourly_daily_and_monthly_burn() -> None:
    output = io.StringIO()
    args = argparse.Namespace(
        hourly_rate_usd=0.55,
        vast_instance_id="vast-12345",
        json=False,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_cost(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL cost burn:" in rendered
    assert "hourly=$0.5500" in rendered
    assert f"daily=${0.55 * 24:.4f}" in rendered
    assert f"monthly=${0.55 * 24 * 30:.4f}" in rendered
    assert "monthly_days=30" in rendered
    assert "vast_instance_id=vast-12345" in rendered


def test_pal_cost_cli_json_includes_burn_breakdown() -> None:
    output = io.StringIO()
    args = argparse.Namespace(
        hourly_rate_usd=0.40,
        vast_instance_id=None,
        json=True,
    )
    with redirect_stdout(output):
        rc = promptclaw_cli.cmd_pal_cost(args)

    assert rc == 0
    payload = json.loads(output.getvalue())
    assert payload["hourly_rate_usd"] == pytest.approx(0.40)
    assert payload["daily_burn_usd"] == pytest.approx(0.40 * 24)
    assert payload["monthly_burn_usd"] == pytest.approx(0.40 * 24 * 30)
    assert payload["monthly_days"] == 30
    assert payload["vast_instance_id"] is None


def test_pal_cost_parser_requires_hourly_rate(tmp_path: Path) -> None:
    parser = promptclaw_cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["pal", "cost"])

    args = parser.parse_args(["pal", "cost", "--hourly-rate-usd", "0.55"])
    assert args.pal_command == "cost"
    assert args.hourly_rate_usd == pytest.approx(0.55)
    assert args.vast_instance_id is None
    assert args.json is False


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
