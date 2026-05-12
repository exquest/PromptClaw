"""Documentation contract for frac-0102d render-ablation depth-2 completion."""
from __future__ import annotations

from pathlib import Path


NOTES_PATH = Path("sdp/notes/frac-0102a-render-ablation-depth.md")


def test_render_ablation_notes_record_depth_two_completion() -> None:
    assert NOTES_PATH.exists(), "missing render-ablation depth notes file"

    text = NOTES_PATH.read_text()

    assert "## Depth-2 Completion" in text, (
        "depth-2 completion section missing from render-ablation notes"
    )

    completion_marker = "## Depth-2 Completion"
    completion_index = text.index(completion_marker)
    completion_section = text[completion_index:]

    required_fragments = [
        "RenderAblationEndToEndTests",
        "test_full_pipeline_final_rendered_artifact_shape_and_content",
        "frac-0102",
        "frac-0102c",
        "my-claw/tools/senseweave/render/ablation.py",
        "rule_identifiers",
        "filter_active_rules",
        "ablate",
        "build_ablation_cases",
        "run_ablation_suite",
        "summarize_ablation_suite",
    ]
    for fragment in required_fragments:
        assert fragment in completion_section, (
            f"depth-2 completion section missing fragment: {fragment}"
        )

    closed_lines = [
        line
        for line in completion_section.splitlines()
        if line.startswith("- Closed:")
    ]
    assert len(closed_lines) >= 4, (
        "depth-2 completion section needs at least four `- Closed:` bullets"
    )
