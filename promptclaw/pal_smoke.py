from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .pal_client import PALQueryResult


class PALSmokeClient(Protocol):
    base_url: str
    default_model: str

    def health(self) -> dict[str, Any]:
        ...

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        ...


@dataclass(frozen=True)
class SmokePrompt:
    prompt_id: str
    prompt: str
    system: str = "You are PAL 2026. Respond concisely and operationally."
    temperature: float = 0.2


DEFAULT_SMOKE_PROMPTS: tuple[SmokePrompt, ...] = (
    SmokePrompt(
        prompt_id="reachability",
        prompt="Confirm PAL 2026 Phase 1 is reachable through the PromptClaw PAL client.",
    ),
    SmokePrompt(
        prompt_id="configuration",
        prompt="Describe your current PAL 2026 Phase 1 configuration in two concise sentences.",
    ),
    SmokePrompt(
        prompt_id="operational_triage",
        prompt="A scheduled auto-shutdown did not happen. List the first three checks an operator should run.",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pal_smoke(
    client: PALSmokeClient,
    *,
    prompts: tuple[SmokePrompt, ...] = DEFAULT_SMOKE_PROMPTS,
    now: Callable[[], str] = _utc_now,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    started_at = now()
    health_start = timer()
    health = client.health()
    health_latency_s = round(timer() - health_start, 3)

    checks: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    total_latency_s = health_latency_s

    for smoke_prompt in prompts:
        check_start = timer()
        try:
            result = client.query(
                smoke_prompt.prompt,
                system=smoke_prompt.system,
                temperature=smoke_prompt.temperature,
            )
            latency_s = round(timer() - check_start, 3)
            total_latency_s += latency_s
            passed += 1
            checks.append(
                {
                    "id": smoke_prompt.prompt_id,
                    "status": "pass",
                    "latency_s": latency_s,
                    "prompt": smoke_prompt.prompt,
                    "response": result.text,
                    "model": result.raw.get("model", ""),
                    "router_total_duration_s": _ns_to_seconds(result.raw.get("total_duration")),
                    "tokens_per_second": _tokens_per_second(result.raw),
                    "raw": result.raw,
                }
            )
        except Exception as exc:
            latency_s = round(timer() - check_start, 3)
            total_latency_s += latency_s
            failed += 1
            checks.append(
                {
                    "id": smoke_prompt.prompt_id,
                    "status": "fail",
                    "latency_s": latency_s,
                    "prompt": smoke_prompt.prompt,
                    "error": str(exc),
                }
            )

    return {
        "status": "pass" if failed == 0 else "fail",
        "started_at": started_at,
        "router": {
            "base_url": client.base_url,
            "default_model": client.default_model,
        },
        "health": health,
        "health_latency_s": health_latency_s,
        "checks": checks,
        "summary": {
            "prompt_count": len(prompts),
            "passed": passed,
            "failed": failed,
            "total_latency_s": round(total_latency_s, 3),
        },
    }


def write_smoke_report(project_root: Path, report: dict[str, Any], output: Path | None = None) -> Path:
    path = output if output is not None else _default_report_path(project_root, report["started_at"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def load_smoke_reports(project_root: Path) -> list[dict[str, Any]]:
    reports_dir = project_root / ".promptclaw" / "pal-smoke"
    reports: list[dict[str, Any]] = []
    for path in sorted(reports_dir.glob("pal-smoke-*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            reports.append(data)
    return reports


def summarize_smoke_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return {
            "report_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "pass_rate": 0.0,
            "latest_started_at": "",
            "total_latency_s": {"avg": None, "min": None, "max": None},
            "prompts": {},
        }

    pass_count = sum(1 for report in reports if report.get("status") == "pass")
    fail_count = len(reports) - pass_count
    total_latencies = [
        float(summary["total_latency_s"])
        for report in reports
        if isinstance((summary := report.get("summary")), dict)
        and isinstance(summary.get("total_latency_s"), int | float)
    ]

    prompt_rows: dict[str, dict[str, Any]] = {}
    for report in reports:
        checks = report.get("checks", [])
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            prompt_id = str(check.get("id", "unknown"))
            row = prompt_rows.setdefault(
                prompt_id,
                {
                    "runs": 0,
                    "failures": 0,
                    "latencies": [],
                    "tokens_per_second": [],
                },
            )
            row["runs"] += 1
            if check.get("status") != "pass":
                row["failures"] += 1
            if isinstance(check.get("latency_s"), int | float):
                row["latencies"].append(float(check["latency_s"]))
            if isinstance(check.get("tokens_per_second"), int | float):
                row["tokens_per_second"].append(float(check["tokens_per_second"]))

    prompts: dict[str, dict[str, Any]] = {}
    for prompt_id, row in sorted(prompt_rows.items()):
        prompts[prompt_id] = {
            "runs": row["runs"],
            "failures": row["failures"],
            "avg_latency_s": _avg(row["latencies"]),
            "avg_tokens_per_second": _avg(row["tokens_per_second"]),
        }

    started_values = [str(report.get("started_at", "")) for report in reports]
    return {
        "report_count": len(reports),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": round(pass_count / len(reports), 4),
        "latest_started_at": max(started_values),
        "total_latency_s": {
            "avg": _avg(total_latencies),
            "min": min(total_latencies) if total_latencies else None,
            "max": max(total_latencies) if total_latencies else None,
        },
        "prompts": prompts,
    }


def format_baseline_summary(summary: dict[str, Any]) -> str:
    if summary.get("report_count", 0) == 0:
        return "PAL baseline: no smoke reports found"

    total_latency = summary.get("total_latency_s", {})
    lines = [
        "PAL baseline: "
        f"reports={summary['report_count']} "
        f"pass_rate={float(summary['pass_rate']) * 100:.1f}% "
        f"latency_avg={total_latency.get('avg')}s "
        f"latest={summary.get('latest_started_at', '')}"
    ]
    prompts = summary.get("prompts", {})
    if isinstance(prompts, dict):
        for prompt_id, prompt_summary in prompts.items():
            lines.append(
                f"{prompt_id}: "
                f"runs={prompt_summary['runs']} "
                f"failures={prompt_summary['failures']} "
                f"avg_latency_s={prompt_summary['avg_latency_s']} "
                f"avg_tps={prompt_summary['avg_tokens_per_second']}"
            )
    return "\n".join(lines)


def _default_report_path(project_root: Path, started_at: str) -> Path:
    stamp = started_at.replace("-", "").replace(":", "")
    stamp = stamp.replace("+0000", "Z").replace("+00:00", "Z")
    return project_root / ".promptclaw" / "pal-smoke" / f"pal-smoke-{stamp}.json"


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _ns_to_seconds(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return value / 1_000_000_000


def _tokens_per_second(raw: dict[str, Any]) -> float | None:
    eval_count = raw.get("eval_count")
    eval_duration = raw.get("eval_duration")
    if not isinstance(eval_count, int | float) or not isinstance(eval_duration, int | float):
        return None
    if eval_duration <= 0:
        return None
    return round(eval_count / (eval_duration / 1_000_000_000), 2)
