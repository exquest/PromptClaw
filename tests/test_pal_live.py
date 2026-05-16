"""Opt-in live PAL router verification.

Skipped by default. Enable with `pytest --run-live-pal`. Override the router
endpoint with the `PROMPTCLAW_PAL_BASE_URL` environment variable.
"""

from __future__ import annotations

import os

import pytest

from promptclaw.models import PALConfig
from promptclaw.pal_client import PALClientError, PALRouterClient


@pytest.mark.live_pal
def test_pal_router_health_is_reachable() -> None:
    base_url = os.environ.get("PROMPTCLAW_PAL_BASE_URL", PALConfig().base_url)
    client = PALRouterClient(base_url=base_url)

    try:
        health = client.health()
    except PALClientError as exc:
        pytest.fail(f"PAL router at {base_url} unreachable: {exc}")

    assert isinstance(health, dict)
    assert "status" in health
