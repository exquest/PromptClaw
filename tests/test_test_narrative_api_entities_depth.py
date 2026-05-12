"""Depth gate for narrative API entity tests."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _classify_depth(path: str) -> int:
    spec = importlib.util.spec_from_file_location(
        "local_sdp_fractal", Path("sdp/fractal.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    result = module.classify_depth(path)
    return int(result.depth)


def test_test_narrative_api_entities_reaches_depth_two_with_end_to_end_class() -> None:
    test_path = Path("tests/test_narrative_api_entities.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }

    assert "NarrativeApiEntitiesEndToEndTests" in class_names
    assert _classify_depth(str(test_path)) >= 2
