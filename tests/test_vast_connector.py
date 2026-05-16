from __future__ import annotations

import json
from pathlib import Path

from promptclaw.vast_connector import VAST_LIFECYCLE_ACTIONS, default_vast_connector_boundary


def test_default_vast_connector_boundary_blocks_lifecycle_actions() -> None:
    boundary = default_vast_connector_boundary()

    assert boundary.provider == "vast"
    assert boundary.callable_action_names() == ()
    assert boundary.blocked_action_names() == VAST_LIFECYCLE_ACTIONS
    for action_name in ("rent", "destroy", "start", "stop"):
        assert boundary.is_action_callable(action_name) is False
        assert not hasattr(boundary, action_name)

    payload = boundary.to_dict()
    assert payload["provider"] == "vast"
    assert payload["callable_actions"] == []
    assert payload["blocked_actions"] == ["rent", "destroy", "start", "stop"]
    assert payload["status"] == "stubbed"


def test_persisted_vast_connector_boundary_rejects_api_key_value(
    monkeypatch,
    tmp_path: Path,
) -> None:
    api_key = "vast-test-api-key-should-never-persist"
    monkeypatch.setenv("VAST_API_KEY", api_key)

    payload = default_vast_connector_boundary().to_dict()
    target = tmp_path / "vast-boundary.json"
    target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    persisted = target.read_text(encoding="utf-8")
    assert api_key not in persisted
