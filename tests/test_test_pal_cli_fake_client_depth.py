"""Coverage gate for PAL fake-client CLI tests."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


REQUIRED_TESTS = {
    "test_pal_kb_cli_round_trip_uses_local_index_without_router_client",
    "test_pal_agent_actions_cli_executes_approved_fake_client_action",
    "test_pal_restart_validation_workflow_cli_uses_fake_client_and_writes_artifact",
    "test_pal_deploy_plan_cli_uses_fake_inventory_without_router_client",
}


def _classify_depth(path: str) -> int:
    spec = importlib.util.spec_from_file_location(
        "local_sdp_fractal",
        Path("sdp/fractal.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.classify_depth(path)
    return result.depth


def test_pal_fake_client_cli_tests_cover_required_command_families() -> None:
    test_path = Path("tests/test_pal_cli_fake_client.py")
    tree = ast.parse(test_path.read_text(encoding="utf-8"))
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    assert REQUIRED_TESTS <= function_names
    assert _classify_depth(str(test_path)) >= 2
