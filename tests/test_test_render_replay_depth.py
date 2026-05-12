"""Depth gate for render-replay tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_render_replay_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_render_replay.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RenderReplayEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    result = classify_depth(str(test_path))

    assert "RenderReplayEndToEndTests" in class_names
    assert (
        "test_mapping_score_sidecar_delta_audio_export_and_diagnostics_round_trip"
        in e2e_method_names
    )
    assert result.depth >= 2, result.reason
