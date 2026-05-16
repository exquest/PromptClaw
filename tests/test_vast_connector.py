from __future__ import annotations

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
