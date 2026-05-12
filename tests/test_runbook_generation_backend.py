"""Static regression tests for docs/runbooks/generation-backend.md (T-011)."""
from __future__ import annotations

import re
from pathlib import Path


RUNBOOK = Path("docs/runbooks/generation-backend.md")
COST_MODEL = Path("sdp/telemetry/cost-model.md")
AUDIT_CONFIG_EXAMPLE = Path(
    "my-claw/tools/senseweave/generation/idyom_kl_audit_config.json.example"
)


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_exists_and_follows_style() -> None:
    assert RUNBOOK.exists(), f"{RUNBOOK} must exist"
    content = _text()
    lines = content.splitlines()

    h1 = [ln for ln in lines if ln.startswith("# ")]
    assert h1, "runbook must have an H1 title"
    assert "runbook" in h1[0].lower()
    assert "generation" in h1[0].lower()

    h2 = [ln for ln in lines if ln.startswith("## ")]
    assert any("part" in ln.lower() for ln in h2), (
        "runbook must use part-style H2 sections, matching r750-bare-metal-runbook.md"
    )

    assert "```bash" in content or "```sh" in content, (
        "runbook must include bash command blocks"
    )


def test_runbook_covers_required_workflows() -> None:
    content = _text()
    lowered = content.lower()

    assert "check generation status" in lowered or "generation status" in lowered
    assert "widen" in lowered and "tighten" in lowered
    assert "switch backend" in lowered or "switching the backend" in lowered
    assert "replicate" in lowered
    assert "modal" in lowered
    assert "local" in lowered
    assert "roll back" in lowered or "rollback" in lowered
    assert "idyom" in lowered
    assert "ltm" in lowered
    assert "collapse audit" in lowered or "collapse_audit" in lowered
    assert "stuck" in lowered and "queue" in lowered
    assert "inspect" in lowered and "cache" in lowered
    assert "samples/generated" in content
    assert "sensory_journal.jsonl" in content


def test_runbook_documents_env_vars_with_defaults() -> None:
    content = _text()

    assert "CYPHERCLAW_GENERATION_DAILY_CAP_USD" in content
    assert "5.0" in content or "$5.00" in content or "5.00" in content

    assert "CYPHERCLAW_GENERATION_MONTHLY_CAP_USD" in content
    assert "100.0" in content or "$100.00" in content or "100.00" in content

    assert "IDYOM_KL_AUDIT_CONFIG" in content
    assert "REPLICATE_API_TOKEN" in content
    assert "MODAL_TOKEN_ID" in content
    assert "MODAL_TOKEN_SECRET" in content

    assert "utc" in content.lower(), (
        "runbook must say budget caps roll over at UTC midnight"
    )


def test_runbook_documents_generation_worker_service() -> None:
    content = _text()

    assert "cypherclaw-generation-worker.service" in content
    assert "my-claw/systemd/cypherclaw-generation-worker.service" in content
    assert "EnvironmentFile=/home/user/cypherclaw/.env" in content
    assert "REPLICATE_API_TOKEN" in content
    assert "CYPHERCLAW_GENERATION_DAILY_CAP_USD" in content
    assert "CYPHERCLAW_GENERATION_MONTHLY_CAP_USD" in content
    assert "/home/user/cypherclaw/tools/generation_worker.py" in content


def test_runbook_has_five_debugging_scenarios() -> None:
    content = _text()
    scenario_headings = re.findall(
        r"^###\s+Scenario\s+\d+", content, flags=re.MULTILINE
    )
    assert len(scenario_headings) == 5, (
        f"expected exactly 5 'Scenario N' subsections, found {len(scenario_headings)}: "
        f"{scenario_headings}"
    )


def test_runbook_cites_real_paths_and_cross_links() -> None:
    content = _text()

    assert "/home/user/cypherclaw-data/state/generation_budget.json" in content
    assert "/home/user/cypherclaw-data/idyom/ltm.json" in content
    assert "/home/user/cypherclaw-data/idyom/ltm_week0_snapshot.json" in content
    assert "/home/user/cypherclaw-data/state/sensory_journal.jsonl" in content

    assert "sdp/telemetry/cost-model.md" in content
    assert "idyom_kl_audit_config.json.example" in content

    assert COST_MODEL.exists()
    assert AUDIT_CONFIG_EXAMPLE.exists()
