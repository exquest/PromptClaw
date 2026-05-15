from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from promptclaw.cli import cmd_pal_smoke
from promptclaw.config import default_project_config, save_config
from promptclaw.pal_client import PALQueryResult
from promptclaw.pal_smoke import DEFAULT_SMOKE_PROMPTS, run_pal_smoke, write_smoke_report


class FakeClient:
    base_url = "http://pal-cloud-a6000:8000"
    default_model = "llama3.3:70b-instruct-q4_K_M"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def health(self) -> dict[str, Any]:
        return {
            "status": "green",
            "phase": "phase-1-a6000",
            "loaded_models": ["llama3.3:70b-instruct-q4_K_M"],
        }

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        self.prompts.append(prompt)
        return PALQueryResult(
            text=f"response for {prompt[:12]}",
            raw={
                "model": model or self.default_model,
                "response": f"response for {prompt[:12]}",
                "total_duration": 123456789,
                "eval_count": 10,
                "eval_duration": 500000000,
            },
        )


def test_run_pal_smoke_records_health_prompts_latency_and_summary() -> None:
    client = FakeClient()
    report = run_pal_smoke(client, now=lambda: "2026-05-15T18:00:00+00:00", timer=_fake_timer())

    assert report["status"] == "pass"
    assert report["started_at"] == "2026-05-15T18:00:00+00:00"
    assert report["router"]["base_url"] == "http://pal-cloud-a6000:8000"
    assert report["health"]["status"] == "green"
    assert len(report["checks"]) == len(DEFAULT_SMOKE_PROMPTS)
    assert report["summary"]["passed"] == len(DEFAULT_SMOKE_PROMPTS)
    assert report["summary"]["failed"] == 0
    assert report["checks"][0]["id"] == DEFAULT_SMOKE_PROMPTS[0].prompt_id
    assert report["checks"][0]["latency_s"] == 1.0
    assert report["checks"][0]["router_total_duration_s"] == 0.123456789
    assert report["checks"][0]["tokens_per_second"] == 20.0
    assert json.dumps(report, sort_keys=True)


def test_run_pal_smoke_records_failed_prompt_without_stopping_suite() -> None:
    class FailingClient(FakeClient):
        def query(
            self,
            prompt: str,
            *,
            system: str | None = None,
            model: str | None = None,
            temperature: float | None = 0.7,
        ) -> PALQueryResult:
            if "configuration" in prompt:
                raise RuntimeError("router timeout")
            return super().query(
                prompt,
                system=system,
                model=model,
                temperature=temperature,
            )

    report = run_pal_smoke(FailingClient(), now=lambda: "2026-05-15T18:00:00+00:00", timer=_fake_timer())

    assert report["status"] == "fail"
    assert report["summary"]["failed"] == 1
    failed = [check for check in report["checks"] if check["status"] == "fail"]
    assert failed[0]["error"] == "router timeout"


def test_write_smoke_report_uses_timestamped_default_path(tmp_path: Path) -> None:
    report = {"started_at": "2026-05-15T18:00:00+00:00", "status": "pass"}

    path = write_smoke_report(tmp_path, report)

    assert path == tmp_path / ".promptclaw" / "pal-smoke" / "pal-smoke-20260515T180000Z.json"
    assert json.loads(path.read_text()) == report


def test_pal_smoke_cli_writes_report_and_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = default_project_config("PAL Smoke CLI")
    save_config(tmp_path, config)

    class FakeClientFactory(FakeClient):
        @classmethod
        def from_config(cls, loaded_config: Any) -> FakeClientFactory:
            return cls()

    monkeypatch.setattr("promptclaw.cli.PALRouterClient", FakeClientFactory)
    monkeypatch.setattr("promptclaw.cli.run_pal_smoke", lambda client: {
        "status": "pass",
        "started_at": "2026-05-15T18:00:00+00:00",
        "summary": {"passed": 3, "failed": 0, "total_latency_s": 4.2},
    })

    output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, output=None, json=False)
    with redirect_stdout(output):
        rc = cmd_pal_smoke(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL smoke: PASS" in rendered
    assert "passed=3 failed=0 total_latency_s=4.2" in rendered
    assert "report=" in rendered
    report_paths = list((tmp_path / ".promptclaw" / "pal-smoke").glob("*.json"))
    assert len(report_paths) == 1


def _fake_timer():
    values = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    return lambda: next(values)
