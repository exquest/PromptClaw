"""Tests for layout-aware CypherClaw runtime path resolution."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from runtime_paths import resolve_runtime_paths


def _make_runtime_root(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "sdp").mkdir()


def test_resolve_runtime_paths_from_tools_layout(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "tools" / "cypherclaw_daemon.py"
    anchor.write_text("# stub\n")

    paths = resolve_runtime_paths(anchor)

    assert paths.project_root == runtime_root
    assert paths.tools_dir == runtime_root / "tools"
    assert paths.workspace_dir == runtime_root / "tools" / "workspace"
    assert paths.tasks_dir == runtime_root / "tools" / "workspace" / "tasks"


def test_resolve_runtime_paths_from_src_layout_keeps_workspace_in_tools(tmp_path: Path) -> None:
    runtime_root = tmp_path / "cypherclaw"
    _make_runtime_root(runtime_root)
    anchor = runtime_root / "src" / "cypherclaw" / "daemon.py"
    anchor.parent.mkdir(parents=True)
    anchor.write_text("# stub\n")

    paths = resolve_runtime_paths(anchor)

    assert paths.project_root == runtime_root
    assert paths.tools_dir == runtime_root / "tools"
    assert paths.workspace_dir == runtime_root / "tools" / "workspace"
    assert paths.workspace_dir != anchor.parent / "workspace"
