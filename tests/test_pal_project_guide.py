from __future__ import annotations

from pathlib import Path

PROJECT_GUIDE = Path(__file__).resolve().parents[1] / "pal-2026" / "docs" / "PROJECT_GUIDE.md"


def test_project_guide_names_operator_loop() -> None:
    text = PROJECT_GUIDE.read_text()
    assert "Local-First Build → Query → Plan" in text
