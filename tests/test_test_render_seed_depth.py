"""Depth gate for render-seed tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_render_seed_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_render_seed.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RenderSeedEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    result = classify_depth(str(test_path))

    assert "RenderSeedEndToEndTests" in class_names
    assert (
        "test_full_seed_derivation_lifecycle_is_json_safe_and_event_round_trip_safe"
        in e2e_method_names
    )
    assert result.depth >= 2, result.reason
