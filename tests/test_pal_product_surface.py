from __future__ import annotations

from pathlib import Path

PRODUCT_SURFACE = (
    Path(__file__).resolve().parents[1] / "docs" / "pal-product-surface.md"
)


def _read() -> str:
    return PRODUCT_SURFACE.read_text()


def test_product_surface_lists_pal_commands() -> None:
    text = _read()
    for command in (
        "promptclaw pal health",
        "promptclaw pal query",
        "promptclaw pal smoke",
        "promptclaw pal baseline",
        "promptclaw pal kb build",
        "promptclaw pal kb query",
        "promptclaw pal diagnose slow-inference",
        "promptclaw pal validate restart",
        "promptclaw pal audit shutdown",
        "promptclaw pal report phase2-readiness",
        "promptclaw pal deploy plan",
        "promptclaw pal agent triage",
        "promptclaw pal agent actions",
    ):
        assert command in text, f"missing command: {command}"


def test_product_surface_lists_pal_modules() -> None:
    text = _read()
    for module in (
        "promptclaw.pal_client",
        "promptclaw.pal_smoke",
        "promptclaw.pal_knowledge",
        "promptclaw.pal_agent",
        "promptclaw.pal_deploy",
        "promptclaw.vast_connector",
    ):
        assert module in text, f"missing module: {module}"


def test_product_surface_lists_pal_artifacts() -> None:
    text = _read()
    for artifact in (
        ".promptclaw/pal-kb/index.jsonl",
        ".promptclaw/pal-smoke/pal-smoke-",
        ".promptclaw/runs/<run-id>/",
        "outputs/action-results.json",
        "outputs/slow-inference-diagnosis.json",
        "outputs/restart-validation.json",
        "outputs/shutdown-audit.json",
        "outputs/phase2-readiness.json",
        "pal-2026/ops/deployment-manifest.json",
    ):
        assert artifact in text, f"missing artifact: {artifact}"


def test_product_surface_lists_opt_pal_layout() -> None:
    text = _read()
    for target in (
        "/opt/pal/scripts/start_all.sh",
        "/opt/pal/scripts/start_ollama.sh",
        "/opt/pal/scripts/start_router.sh",
        "/opt/pal/scripts/auto_shutdown.sh",
        "/opt/pal/config/shutdown.conf",
        "/opt/pal/router/app.py",
        "/opt/pal/DEPLOYMENT_INFO.md",
        "/opt/pal/router/Dockerfile",
        "/opt/pal/docker-compose.yml",
        "/opt/pal/config/override.flag",
    ):
        assert target in text, f"missing /opt/pal entry: {target}"
    assert "host-managed" in text
