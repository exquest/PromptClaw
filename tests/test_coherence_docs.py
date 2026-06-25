"""Regression checks for coherence documentation."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from promptclaw.coherence.models import CoherenceConfig


ROOT = Path(__file__).resolve().parents[1]


def _read_doc(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_configuration_reference_documents_coherence_config_fields() -> None:
    text = _read_doc("docs/configuration-reference.md")

    assert "### `coherence`" in text
    for field in fields(CoherenceConfig):
        assert f"`{field.name}`" in text
    for mode in ("`monitor`", "`soft`", "`full`"):
        assert mode in text
    assert "`.promptclaw/coherence.db`" in text


def test_coherence_overview_links_operational_surfaces() -> None:
    text = _read_doc("docs/coherence.md")

    expected_links = (
        "[Shadowland Field Guide](Shadowland2/final/field_guide.md)",
        "[protocol.py](../promptclaw/coherence/protocol.py)",
        "[decision_capture.py](../promptclaw/coherence/decision_capture.py)",
        "[tension_capture.py](../promptclaw/coherence/tension_capture.py)",
        "[reentry.py](../promptclaw/coherence/reentry.py)",
        "[trust.py](../promptclaw/coherence/trust.py)",
        "[graduation.py](../promptclaw/coherence/graduation.py)",
    )
    for link in expected_links:
        assert link in text

    for phrase in (
        "```decision",
        "```tension",
        "re-entry digest",
        "trust scoring",
        "graduation",
    ):
        assert phrase in text


def test_coherence_overview_documents_tiers_and_sec001_hardening() -> None:
    text = _read_doc("docs/coherence.md")

    for phrase in (
        "foundation",
        "formula",
        "recut, don't grandfather",
        "SEC-001",
        "PRAGMA table_info(dummy)",
        "FAIL->PASS",
    ):
        assert phrase in text
