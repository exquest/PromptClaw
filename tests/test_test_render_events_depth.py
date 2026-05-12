"""Depth gate for render-events tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_render_events_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_render_events.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RenderEventsEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    result = classify_depth(str(test_path))

    assert "RenderEventsEndToEndTests" in class_names
    assert (
        "test_full_render_events_lifecycle_is_json_and_osc_round_trip_safe"
        in e2e_method_names
    )
    assert result.depth >= 2, result.reason
