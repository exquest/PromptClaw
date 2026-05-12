"""Static regression tests for docs/cypherclaw-sampler-architecture.md.

These tests pin the architectural contract of the sampler subsystem
documentation. They guard against silent rot: if a referenced module
moves, an anti-pattern is renamed, or a section is removed, the doc
must be updated alongside the code.
"""
from __future__ import annotations

from pathlib import Path

DOC_PATH = Path("docs/cypherclaw-sampler-architecture.md")
ROADMAP_PATH = Path("docs/cypherclaw-musicianship-roadmap.md")
PRD_PATH = Path("my-claw/sdp/prd-cypherclaw-sampler.md")

LANDED_COMPONENTS = (
    "my-claw/tools/sample_capture_daemon.py",
    "my-claw/tools/sample_capture_verify.py",
    "my-claw/tools/sampler_fx_mode_verify.py",
    "my-claw/tools/senseweave/sampler_buffers.py",
    "my-claw/tools/senseweave/sampler_dispatch.py",
    "my-claw/tools/senseweave/synthesis/sampler_effects.scd",
    "my-claw/tools/senseweave/render/antipatterns.py",
)

LIVE_ANTIPATTERNS = (
    "sampler_dominating",
    "sampler_silent_quintet_member",
)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_doc_exists_and_declares_scope() -> None:
    assert DOC_PATH.exists(), f"{DOC_PATH} must exist"
    content = _doc_text()
    lowered = content.lower()

    assert "# cypherclaw sampler architecture" in lowered
    assert "## scope" in lowered or "## overview" in lowered
    # Cross-links to the upstream PRD and the roadmap so readers can
    # find the artistic intent and the broader status snapshot.
    assert "cypherclaw-musicianship-roadmap.md" in content
    assert "prd-cypherclaw-sampler.md" in content


def test_doc_lists_landed_components_and_paths_resolve() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "## components" in lowered

    for path in LANDED_COMPONENTS:
        assert path in content, f"doc must reference landed component {path}"
        assert Path(path).exists(), (
            f"doc references {path} but the file does not exist in the tree"
        )


def test_doc_describes_full_signal_flow() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "## signal flow" in lowered

    # The end-to-end chain that a captured moment travels through.
    for stage in (
        "jack",
        "rolling buffer",
        "interesting",
        "tag",
        "index.sqlite",
        "dispatch",
        "sampler effects",
        "master bus",
    ):
        assert stage in lowered, f"signal flow must mention '{stage}'"


def test_doc_names_live_antipatterns() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "## antipatterns" in lowered or "## anti-patterns" in lowered

    for name in LIVE_ANTIPATTERNS:
        assert name in content, (
            f"doc must name live anti-pattern detector '{name}'"
        )


def test_doc_records_sampler_density_semantics_and_mode_values() -> None:
    content = _doc_text()

    assert "## mode density reference" in content.lower()
    assert "It does not mean gain, wetness, or prominence in the mix." in content
    assert "floor(density * total_phrases) + Bernoulli(density)" in content

    for mode, density in (
        ("solitary", "0.70"),
        ("companion", "0.25"),
        ("working_ambience", "0.10"),
        ("evening_reflection", "0.65"),
        ("storm", "0.45"),
    ):
        row = f"| `{mode}` | `{density}` |"
        assert row in content, f"doc must pin sampler_density for {mode}"


def test_doc_lists_integration_points() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "## integration points" in lowered

    for seam in (
        "artist_identity",
        "cast_planner",
        "master_bus",
        "duet_composer",
        "operator_diagnostics",
    ):
        assert seam in content, f"integration points must call out '{seam}'"


def test_doc_records_partial_rollout_and_cross_links() -> None:
    content = _doc_text()
    lowered = content.lower()

    assert "## status" in lowered or "## status delta" in lowered

    # The doc must not pretend the unbuilt pieces are present; it must
    # explicitly mark them as still pending and point readers at the
    # roadmap and PRD for the longer plan.
    for pending in (
        "SampleLibrary",
        "SampleSelector",
        "sw_sampler.scd",
    ):
        assert pending in content, (
            f"status section must flag '{pending}' as still pending"
        )

    assert "partial" in lowered
    assert ROADMAP_PATH.exists()
    assert PRD_PATH.exists()
