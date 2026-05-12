"""Static regression test for the 'Lingering' section in ESCALATIONS.md (T-006)."""
from __future__ import annotations

from pathlib import Path

ESCALATIONS = Path("ESCALATIONS.md")


def _text() -> str:
    return ESCALATIONS.read_text(encoding="utf-8")


def test_escalations_has_lingering_section() -> None:
    content = _text()
    assert "## Lingering" in content, "ESCALATIONS.md must have a top-level 'Lingering' section"


def test_lingering_section_documents_enable_linger() -> None:
    content = _text()
    assert "loginctl enable-linger" in content
    assert "loginctl show-user" in content
    assert "-p Linger" in content
    assert "Linger=yes" in content


def test_auth_token_section_documents_runtime_contract() -> None:
    content = _text()
    assert "## Auth Token (optional)" in content
    assert "NARRATIVE_AUTH_TOKEN" in content
    assert "defense-in-depth" in content
    assert "Environment=NARRATIVE_AUTH_TOKEN=" in content
    assert "systemctl --user edit cypherclaw-narrative-api.service" in content
    assert "X-Narrative-Auth" in content


def test_network_allowlist_section_documents_tailscale_lookup() -> None:
    content = _text()
    assert "## Network Allowlist" in content
    assert "Deniable" in content
    assert "Tailscale" in content
    assert "tailscale ip -4" in content
    assert "<DENIABLE_TAILSCALE_IPV4>" in content
