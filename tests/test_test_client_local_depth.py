"""Depth gate for local-client tests."""
from __future__ import annotations

import ast
from pathlib import Path

from sdp.fractal import classify_depth


def test_test_client_local_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_client_local.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }

    result = classify_depth(str(test_path))

    assert "TestLocalAdaClientEndToEnd" in class_names
    assert result.depth >= 2, result.reason
