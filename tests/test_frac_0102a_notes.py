"""Documentation contract for frac-0102a render-ablation coverage notes."""
from __future__ import annotations

from pathlib import Path


NOTES_PATH = Path("sdp/notes/frac-0102a-render-ablation-depth.md")


def test_frac_0102a_notes_document_render_ablation_depth_gaps() -> None:
    assert NOTES_PATH.exists(), "missing frac-0102a render-ablation notes file"

    text = NOTES_PATH.read_text()

    required_fragments = [
        "tests/test_render_ablation.py",
        "my-claw/tools/senseweave/render/ablation.py",
        "Pre-Depth-2 Baseline",
        "Exercised Paths",
        "Smoke-Checked Outputs",
        "Concrete Gaps",
        "ablate",
        "build_ablation_cases",
        "run_ablation_suite",
        "summarize_ablation_suite",
        "RenderAblationEndToEndTests",
    ]
    for fragment in required_fragments:
        assert fragment in text

    gap_lines = [
        line for line in text.splitlines() if line.startswith("- Gap:")
    ]
    assert len(gap_lines) >= 4
