"""Depth gate for the primary render-path tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_render_pass_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_render_pass.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }

    result = classify_depth(str(test_path))

    assert "RenderPassEndToEndTests" in class_names
    assert result.depth >= 2, result.reason
