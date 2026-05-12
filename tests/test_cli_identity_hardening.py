"""Integration test for CLI startup identity hardening [frac-0046]."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from promptclaw.cli import main


def test_cli_startup_invokes_bootstrap_identity(tmp_path: Path) -> None:
    """Verifying that running the CLI main function invokes bootstrap_identity."""
    # We use patch to verify that bootstrap_identity is called
    with patch("cypherclaw.first_boot.bootstrap_identity") as mock_bootstrap:
        # Run a simple command that doesn't need much setup
        # 'show-config' needs a project root
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "promptclaw.json").write_text(json.dumps({
            "project": {"name": "Test", "description": "Test"},
            "agents": {"mock": {"enabled": True, "kind": "mock"}}
        }))
        
        # We capture stdout to avoid clutter
        with patch("sys.stdout"):
            main(["show-config", str(project_root)])
        
        mock_bootstrap.assert_called_once()
