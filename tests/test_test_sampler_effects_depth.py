"""Depth gate for sampler-effects tests."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _classify_depth(path: str) -> int:
    spec = importlib.util.spec_from_file_location(
        "local_sdp_fractal", Path("sdp/fractal.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.classify_depth(path)
    return result.depth


def test_test_sampler_effects_reaches_depth_two_with_e2e_class() -> None:
    test_path = Path("tests/test_sampler_effects.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "SamplerEffectsEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    assert "SamplerEffectsEndToEndTests" in class_names
    assert (
        "test_sampler_effects_source_and_runtime_harness_round_trip_json_diagnostic"
        in e2e_method_names
    )
    assert _classify_depth(str(test_path)) >= 2
