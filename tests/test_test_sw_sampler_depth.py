"""Depth gate for sw_sampler tests."""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path


_DEPTH_TWO_MARKER_RE = re.compile(r"\bdepth\s*[:=]\s*2\b", re.IGNORECASE)


def _classify_depth(path: str) -> int:
    spec = importlib.util.spec_from_file_location(
        "local_sdp_fractal", Path("sdp/fractal.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.classify_depth(path)
    return result.depth


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    return set()


def _literal_value(node: ast.expr | None) -> object:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (SyntaxError, TypeError, ValueError):
        return None


def _has_machine_readable_depth_two_marker(tree: ast.Module) -> bool:
    docstring = ast.get_docstring(tree) or ""
    if _DEPTH_TWO_MARKER_RE.search(docstring):
        return True

    for node in tree.body:
        names: set[str]
        value: object
        if isinstance(node, ast.Assign):
            names = {
                name
                for target in node.targets
                for name in _target_names(target)
            }
            value = _literal_value(node.value)
        elif isinstance(node, ast.AnnAssign):
            names = _target_names(node.target)
            value = _literal_value(node.value)
        else:
            continue

        if not any("DEPTH" in name.upper() for name in names):
            continue
        if value == 2:
            return True
        if isinstance(value, str) and _DEPTH_TWO_MARKER_RE.search(value):
            return True

    return False


def test_test_sw_sampler_reaches_depth_two_with_e2e_class() -> None:
    test_path = Path("tests/test_sw_sampler.py")
    tree = ast.parse(test_path.read_text())
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    e2e_method_names = {
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "SwSamplerEndToEndTests"
        for item in node.body
        if isinstance(item, ast.FunctionDef)
    }

    assert "SwSamplerEndToEndTests" in class_names
    assert (
        "test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic"
        in e2e_method_names
    )
    assert _classify_depth(str(test_path)) >= 2


def test_test_sw_sampler_declares_machine_readable_depth_two_marker() -> None:
    test_path = Path("tests/test_sw_sampler.py")
    tree = ast.parse(test_path.read_text())

    assert _has_machine_readable_depth_two_marker(tree), (
        "tests/test_sw_sampler.py must declare depth: 2 in the module "
        "docstring or a top-level DEPTH constant so the coverage tier is "
        "machine-readable"
    )
