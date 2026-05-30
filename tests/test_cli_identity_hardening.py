"""Integration test for CLI startup identity hardening [frac-0046]."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
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


def test_cli_startup_persists_identity_between_boots(tmp_path: Path) -> None:
    """Running CLI startup twice must mint once and reuse the persisted identity."""
    import cypherclaw.first_boot as first_boot

    identity_path = tmp_path / "identity.json"
    real_bootstrap = first_boot.bootstrap_identity
    booted_ids: list[str] = []

    def bootstrap_for_test(**kwargs: Any) -> object:
        identity = real_bootstrap(mode="standalone", identity_path=identity_path)
        booted_ids.append(identity.instance_id)
        return identity

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "promptclaw.json").write_text(
        json.dumps(
            {
                "project": {"name": "Test", "description": "Test"},
                "agents": {"mock": {"enabled": True, "kind": "mock"}},
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "cypherclaw.first_boot.bootstrap_identity",
        side_effect=bootstrap_for_test,
    ), patch("sys.stdout"):
        assert main(["show-config", str(project_root)]) == 0
        assert main(["show-config", str(project_root)]) == 0

    assert identity_path.exists()
    assert booted_ids[0] == booted_ids[1]
