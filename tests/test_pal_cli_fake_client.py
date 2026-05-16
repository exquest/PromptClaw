"""Fake-client CLI integration coverage for PAL workflows.

depth: 2
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from promptclaw import cli as promptclaw_cli
from promptclaw import pal_agent
from promptclaw.config import default_project_config, save_config
from promptclaw.models import PALConfig
from promptclaw.pal_client import PALQueryResult


class FakePALClient:
    base_url = "http://pal-cloud-a6000:8000"
    default_model = "llama3.3:70b-instruct-q4_K_M"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.health_calls = 0
        self.query_calls: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        self.health_calls += 1
        return {
            "status": "green",
            "phase": "phase-1-a6000",
            "loaded_models": [self.default_model],
        }

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        self.query_calls.append({
            "prompt": prompt,
            "system": system,
            "model": model,
            "temperature": temperature,
        })
        text = self.responses.pop(0) if self.responses else "Fake PAL response."
        return PALQueryResult(
            text=text,
            raw={
                "response": text,
                "model": model or self.default_model,
                "total_duration": 1_000_000_000,
                "eval_count": 12,
                "eval_duration": 500_000_000,
            },
        )


def test_pal_kb_cli_round_trip_uses_local_index_without_router_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_bootstrap_identity(monkeypatch)
    _patch_no_router_client(monkeypatch)
    _save_pal_project(tmp_path, knowledge_sources=["docs/*.md"])
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "router.md").write_text(
        "# Router\nPAL router restart validates health and smoke evidence.\n",
        encoding="utf-8",
    )

    build_rc, build_stdout, build_stderr = _run_cli([
        "pal",
        "kb",
        "build",
        str(tmp_path),
        "--max-chars",
        "200",
        "--json",
    ])

    assert build_rc == 0
    assert build_stderr == ""
    build_payload = json.loads(build_stdout)
    assert build_payload["source_count"] == 1
    assert build_payload["chunk_count"] == 1
    assert Path(build_payload["index_path"]).is_file()

    query_rc, query_stdout, query_stderr = _run_cli([
        "pal",
        "kb",
        "query",
        str(tmp_path),
        "--query",
        "router restart",
        "--json",
    ])

    assert query_rc == 0
    assert query_stderr == ""
    results = json.loads(query_stdout)
    assert len(results) == 1
    assert results[0]["source_path"] == "docs/router.md"
    assert "PAL router restart validates health" in results[0]["snippet"]


def test_pal_agent_actions_cli_executes_approved_fake_client_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_bootstrap_identity(monkeypatch)
    _patch_optional_remote_tools_offline(monkeypatch)
    _save_pal_project(tmp_path)
    fake_client = FakePALClient([
        json.dumps({
            "actions": ["inspect_logs_deep"],
            "rationale": "Inspect PAL logs before any mutation.",
        }),
        "Approved log inspection completed.",
    ])
    _patch_pal_agent_client(monkeypatch, fake_client)

    rc, stdout, stderr = _run_cli([
        "pal",
        "agent",
        "actions",
        str(tmp_path),
        "--task",
        "Inspect PAL logs.",
        "--approve",
        "inspect_logs_deep",
        "--json",
    ])

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["status"] == "complete"
    assert payload["proposed_actions"] == ["inspect_logs_deep"]
    assert payload["executed_actions"] == ["inspect_logs_deep"]
    assert payload["pending_approval"] == []
    assert payload["ignored_actions"] == []
    assert len(fake_client.query_calls) == 2

    action_results_path = (
        tmp_path
        / ".promptclaw"
        / "runs"
        / payload["run_id"]
        / "outputs"
        / "action-results.json"
    )
    action_results = json.loads(action_results_path.read_text(encoding="utf-8"))
    assert action_results["approved_actions"] == ["inspect_logs_deep"]
    assert action_results["actions"][0]["status"] == "skipped"
    assert action_results["actions"][0]["mutating"] is False


def test_pal_restart_validation_workflow_cli_uses_fake_client_and_writes_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_bootstrap_identity(monkeypatch)
    _patch_optional_remote_tools_offline(monkeypatch)
    _save_pal_project(tmp_path)
    fake_client = FakePALClient([
        "Restart validation direct query succeeded.",
        "Reachability smoke response.",
        "Configuration smoke response.",
        "Operational triage smoke response.",
    ])
    _patch_pal_agent_client(monkeypatch, fake_client)

    rc, stdout, stderr = _run_cli([
        "pal",
        "validate",
        "restart",
        str(tmp_path),
        "--json",
    ])

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["workflow_id"] == "restart_validation"
    assert payload["status"] == "complete"
    assert payload["validation_status"] == "warn"
    assert payload["mutating_actions"] == []
    assert payload["executed_tools"] == [
        "pal_health",
        "pal_direct_query",
        "pal_smoke",
        "tailscale_status",
        "ssh_process_check",
    ]
    assert fake_client.health_calls == 2
    assert len(fake_client.query_calls) == 4

    validation_path = tmp_path / payload["validation_path"]
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation_payload["workflow_id"] == "restart_validation"
    assert validation_payload["mutating_actions"] == []
    assert (tmp_path / ".promptclaw" / "pal-smoke").is_dir()


def test_pal_deploy_plan_cli_uses_fake_inventory_without_router_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_bootstrap_identity(monkeypatch)
    _patch_no_router_client(monkeypatch)
    _write_deploy_plan_project(tmp_path)
    remote_inventory_path = tmp_path / "remote-inventory.json"
    remote_inventory_path.write_text(
        json.dumps({
            "/opt/pal/router/app.py": {"content": "old router\n"},
        }),
        encoding="utf-8",
    )

    rc, stdout, stderr = _run_cli([
        "pal",
        "deploy",
        "plan",
        str(tmp_path),
        "--remote-inventory",
        str(remote_inventory_path),
        "--json",
    ])

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["workflow_id"] == "pal_deploy_plan"
    assert payload["dry_run"] is True
    assert payload["remote_writes"] is False
    assert payload["remote_inventory_source"] == str(remote_inventory_path)
    assert payload["summary_counts"]["changed"] == 1
    assert payload["planned_changes"][0]["target"] == "/opt/pal/router/app.py"
    assert not (tmp_path / ".promptclaw").exists()


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = promptclaw_cli.main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def _save_pal_project(
    project_root: Path,
    *,
    knowledge_sources: list[str] | None = None,
) -> None:
    config = default_project_config("PAL Fake CLI")
    config.pal = PALConfig(
        enabled=True,
        base_url="http://pal-cloud-a6000:8000",
        default_model="llama3.3:70b-instruct-q4_K_M",
        knowledge_sources=knowledge_sources or [],
    )
    save_config(project_root, config)


def _patch_bootstrap_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda: None)


def _patch_optional_remote_tools_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pal_agent, "_tailscale_executable", lambda: None)
    for key in ("PAL_SSH_HOST", "PAL_SSH_PORT", "PAL_SSH_KEY"):
        monkeypatch.delenv(key, raising=False)


def _patch_pal_agent_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakePALClient,
) -> None:
    class FakeClientFactory:
        @classmethod
        def from_config(cls, config: Any) -> FakePALClient:
            return fake_client

    monkeypatch.setattr(pal_agent, "PALRouterClient", FakeClientFactory)


def _patch_no_router_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoRouterClient:
        @classmethod
        def from_config(cls, config: Any) -> None:
            raise AssertionError("PAL router client must not be constructed")

    monkeypatch.setattr(promptclaw_cli, "PALRouterClient", NoRouterClient)
    monkeypatch.setattr(pal_agent, "PALRouterClient", NoRouterClient)


def _write_deploy_plan_project(project_root: Path) -> None:
    templates = project_root / "ops" / "templates"
    templates.mkdir(parents=True)
    (templates / "router-app.py").write_text("new router\n", encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "name": "fake-client-pal-deploy",
        "deployment_root": "/opt/pal",
        "mode": "host-managed",
        "files": [
            {
                "source": "ops/templates/router-app.py",
                "target": "/opt/pal/router/app.py",
                "mode": "0644",
                "owner": "root",
                "group": "root",
                "kind": "router",
                "service_impact": "router",
                "required": True,
            }
        ],
        "runtime_directories": ["/opt/pal/logs"],
        "excluded_paths": ["/opt/pal/logs/*.log"],
    }
    manifest_path = project_root / "ops" / "deployment-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
