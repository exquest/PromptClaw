"""Depth gate for render-ablation tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_render_ablation_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_render_ablation.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RenderAblationEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    result = classify_depth(str(test_path))

    assert "RenderAblationEndToEndTests" in class_names
    assert (
        "test_full_pipeline_final_rendered_artifact_shape_and_content"
        in e2e_method_names
    )
    assert result.depth >= 2, result.reason
