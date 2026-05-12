"""Tests for the CypherClaw narrative health endpoint."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi.testclient import TestClient

from cypherclaw.narrative_api.app import create_app


class HealthyEventStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def list_events(
        self,
        *,
        since_event_id: str | None = None,
        domain_filter: str | list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "since_event_id": since_event_id,
                "domain_filter": domain_filter,
                "limit": limit,
            }
        )
        return []


class BrokenEventStore:
    def list_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("world db unavailable")


class TestHealthEndpoint:
    def test_returns_ok_with_subsystem_statuses(self) -> None:
        store = HealthyEventStore()
        client = TestClient(
            create_app(
                event_store=store,
                narrative_engine_checker=lambda: True,
                ollama_checker=lambda: True,
                auth_token="secret",
            )
        )

        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["narrative_engine_importable"] is True
        assert body["world_db_reachable"] is True
        assert body["ollama_reachable"] is True
        assert body["version"] == "0.1.0"
        assert body["uptime_seconds"] >= 0
        assert store.calls == [
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            }
        ]

    def test_returns_degraded_when_any_check_fails(self) -> None:
        client = TestClient(
            create_app(
                event_store=BrokenEventStore(),
                narrative_engine_checker=lambda: True,
                ollama_checker=lambda: False,
            )
        )

        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["narrative_engine_importable"] is True
        assert body["world_db_reachable"] is False
        assert body["ollama_reachable"] is False


class NarrativeApiHealthEndToEndTests:
    __test__ = True

    def test_health_probe_lifecycle_is_json_safe(self) -> None:
        healthy_store = HealthyEventStore()
        healthy_client = TestClient(
            create_app(
                event_store=healthy_store,
                narrative_engine_checker=lambda: True,
                ollama_checker=lambda: True,
                auth_token="probe-token",
            )
        )

        cold_resp = healthy_client.get("/health")
        assert cold_resp.status_code == 200
        cold = cold_resp.json()
        assert cold["status"] == "ok"
        assert cold["narrative_engine_importable"] is True
        assert cold["world_db_reachable"] is True
        assert cold["ollama_reachable"] is True
        assert cold["version"] == "0.1.0"
        assert cold["uptime_seconds"] >= 0
        assert healthy_store.calls == [
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            }
        ]

        time.sleep(0.01)

        warm_resp = healthy_client.get("/health")
        assert warm_resp.status_code == 200
        warm = warm_resp.json()
        assert warm["status"] == "ok"
        assert warm["uptime_seconds"] >= cold["uptime_seconds"]
        assert healthy_store.calls == [
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            },
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            },
        ]

        degraded_client = TestClient(
            create_app(
                event_store=BrokenEventStore(),
                narrative_engine_checker=lambda: True,
                ollama_checker=lambda: False,
            )
        )

        degraded_resp = degraded_client.get("/health")
        assert degraded_resp.status_code == 200
        degraded = degraded_resp.json()
        assert degraded["status"] == "degraded"
        assert degraded["narrative_engine_importable"] is True
        assert degraded["world_db_reachable"] is False
        assert degraded["ollama_reachable"] is False
        assert degraded["version"] == "0.1.0"
        assert degraded["uptime_seconds"] >= 0

        diagnostic = {
            "cold": cold,
            "warm": warm,
            "degraded": degraded,
            "healthy_store_calls": healthy_store.calls,
        }
        decoded = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert decoded["cold"]["status"] == "ok"
        assert decoded["warm"]["uptime_seconds"] >= decoded["cold"]["uptime_seconds"]
        assert decoded["degraded"]["status"] == "degraded"
        assert decoded["degraded"]["world_db_reachable"] is False
        assert decoded["healthy_store_calls"] == [
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            },
            {
                "since_event_id": None,
                "domain_filter": None,
                "limit": 1,
            },
        ]
