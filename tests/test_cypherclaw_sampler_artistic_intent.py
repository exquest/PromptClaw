"""Static regression tests for docs/cypherclaw-sampler-artistic-intent.md."""
from __future__ import annotations

from pathlib import Path


DOC_PATH = Path("docs/cypherclaw-sampler-artistic-intent.md")
PRD_PATH = Path("my-claw/sdp/prd-cypherclaw-sampler.md")
ARCHITECTURE_PATH = Path("docs/cypherclaw-sampler-architecture.md")
ROADMAP_PATH = Path("docs/cypherclaw-musicianship-roadmap.md")


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_doc_exists_and_stays_concise() -> None:
    assert DOC_PATH.exists(), f"{DOC_PATH} must exist"
    content = _doc_text()
    lowered = content.lower()
    words = content.split()

    assert "# cypherclaw sampler artistic intent" in lowered
    assert "artistic intent" in lowered
    assert 250 <= len(words) <= 1000


def test_doc_names_aesthetic_goals_and_three_usages() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "aesthetic goals" in lowered
    assert "memory of place" in lowered
    assert "self-quotation" in lowered
    assert "found-sound" in lowered or "found sound" in lowered


def test_doc_describes_sampler_role_in_ensemble() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "role in the ensemble" in lowered
    assert "quintet" in lowered
    assert "memory voice" in lowered
    assert "sw_sampler" in content


def test_doc_describes_listener_experience_and_principles() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "listener experience" in lowered
    assert "five principles" in lowered
    assert "granular" in lowered
    assert "mood-aware" in lowered or "mood aware" in lowered
    assert "effects bus" in lowered
    assert "self-listening" in lowered or "self listening" in lowered
    assert "restraint" in lowered
    assert "heard back" in lowered or "hears itself back" in lowered


def test_doc_cross_links_adjacent_sampler_docs() -> None:
    content = _doc_text()

    assert "prd-cypherclaw-sampler.md" in content
    assert "cypherclaw-sampler-architecture.md" in content
    assert "cypherclaw-musicianship-roadmap.md" in content

    assert PRD_PATH.exists()
    assert ARCHITECTURE_PATH.exists()
    assert ROADMAP_PATH.exists()

    assert "cypherclaw-sampler-artistic-intent.md" in ARCHITECTURE_PATH.read_text(
        encoding="utf-8"
    )
    assert "cypherclaw-sampler-artistic-intent.md" in ROADMAP_PATH.read_text(
        encoding="utf-8"
    )
