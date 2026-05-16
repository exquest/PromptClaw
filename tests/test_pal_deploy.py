from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from promptclaw.pal_deploy import (
    PALDeploymentManifestError,
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
