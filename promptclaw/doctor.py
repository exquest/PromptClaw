from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_config, validate_config
from .utils import executable_exists


@dataclass(slots=True)
class DoctorCheck:
    status: str
    message: str
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "details": list(self.details),
        }


@dataclass(slots=True)
class DoctorReport:
    checks: dict[str, dict[str, Any]]

    @property
    def ok(self) -> bool:
        return all(check["status"] != "fail" for check in self.checks.values())

    def to_text(self) -> str:
        lines = []
        for name, check in self.checks.items():
            lines.append(f"- {name}: {check['status'].upper()} — {check['message']}")
            for detail in check.get("details", []):
                lines.append(f"  - {detail}")
        lines.append("Doctor OK ✅" if self.ok else "Doctor found issues:")
        return "\n".join(lines)


def _validate_command_agents(project_root: Path) -> list[str]:
    config = load_config(project_root)
    issues = validate_config(config)
    for name, agent in config.agents.items():
        if not (agent.enabled and agent.kind == "command"):
            continue
        if agent.command:
            program = str(agent.command[0])
            program_path = Path(program)
            if not program_path.is_absolute() and str(program_path) != program_path.name:
                resolved = (project_root / program_path).resolve()
                if resolved.exists():
                    program = str(resolved)
            if not executable_exists(program):
                issues.append(f"agent '{name}' command executable not found: {program}")
    return issues


def _looks_like_runtime_root(project_root: Path) -> bool:
    required = [
        project_root / ".git",
        project_root / ".sdp" / "state.db",
        project_root / ".promptclaw" / "observatory.db",
        project_root / "sdp.toml",
    ]
    return all(path.exists() for path in required)


def _load_runtime_preflight(project_root: Path):
    script_path = project_root / "tools" / "preflight.py"
    if not script_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("project_runtime_preflight", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load runtime preflight from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_preflight_check(project_root: Path) -> DoctorCheck:
    script_path = project_root / "tools" / "preflight.py"
    if not script_path.exists():
        return DoctorCheck(status="skipped", message="No runtime preflight script found")
    if not _looks_like_runtime_root(project_root):
        return DoctorCheck(status="skipped", message="Runtime markers missing; skipping runtime preflight")
    module = _load_runtime_preflight(project_root)
    if module is None or not hasattr(module, "run_preflight"):
        return DoctorCheck(status="fail", message=f"Runtime preflight missing run_preflight() in {script_path}")
    report = module.run_preflight(project_root, workdir=project_root)
    details = []
    checks = getattr(report, "checks", {}) or {}
    for name, check in checks.items():
        if isinstance(check, dict):
            state = "OK" if check.get("ok") else "FAIL"
            message = check.get("message", "")
            details.append(f"{name}: {state}{f' — {message}' if message else ''}")
    return DoctorCheck(
        status="pass" if getattr(report, "ok", False) else "fail",
        message=str(getattr(report, "summary", "Runtime preflight finished")),
        details=details,
    )


def run_doctor(project_root: Path) -> DoctorReport:
    checks: dict[str, dict[str, Any]] = {}

    config_issues = _validate_command_agents(project_root)
    if config_issues:
        config_check = DoctorCheck(
            status="fail",
            message="PromptClaw config validation failed",
            details=config_issues,
        )
    else:
        config_check = DoctorCheck(
            status="pass",
            message="PromptClaw config is valid",
        )
    checks["config"] = config_check.as_dict()

    checks["runtime_preflight"] = _runtime_preflight_check(project_root).as_dict()
    return DoctorReport(checks=checks)
