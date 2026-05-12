"""Depth gate for dashboard-generator tests."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

_FRACTAL_PATH = Path(__file__).resolve().parent.parent / "sdp" / "fractal.py"
_FRACTAL_SPEC = importlib.util.spec_from_file_location("_promptclaw_local_dashboard_fractal", _FRACTAL_PATH)
assert _FRACTAL_SPEC is not None
assert _FRACTAL_SPEC.loader is not None
_FRACTAL_MODULE = importlib.util.module_from_spec(_FRACTAL_SPEC)
sys.modules[_FRACTAL_SPEC.name] = _FRACTAL_MODULE
_FRACTAL_SPEC.loader.exec_module(_FRACTAL_MODULE)
classify_depth = _FRACTAL_MODULE.classify_depth


def test_test_dashboard_generator_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_dashboard_generator.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }

    assert "DashboardGeneratorEndToEndTests" in class_names

    result = classify_depth(str(test_path))
    assert result.depth >= 2, result.reason
