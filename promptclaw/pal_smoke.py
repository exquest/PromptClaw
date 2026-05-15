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


def _default_report_path(project_root: Path, started_at: str) -> Path:
    stamp = started_at.replace("-", "").replace(":", "")
    stamp = stamp.replace("+0000", "Z").replace("+00:00", "Z")
    return project_root / ".promptclaw" / "pal-smoke" / f"pal-smoke-{stamp}.json"


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
