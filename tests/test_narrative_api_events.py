"""Tests for the CypherClaw narrative event log HTTP endpoint."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from cypherclaw.narrative_api.app import create_app


EVENTS = [
    {
        "id": "evt-001",
        "type": "world.bootstrap",
        "domain": "shared",
        "payload": {"note": "world bootstrapped"},
        "created_at": "2026-05-01T00:00:00Z",
    },
    {
        "id": "evt-002",
        "type": "raid.completed",
        "domain": "deniable",
        "payload": {"squad": "wolfpack", "outcome": "success"},
        "created_at": "2026-05-01T01:00:00Z",
    },
    {
        "id": "evt-003",
        "type": "art.cycle",
        "domain": "cypherclaw",
        "payload": {"piece_id": "pc-9"},
        "created_at": "2026-05-01T02:00:00Z",
    },
    {
        "id": "evt-004",
        "type": "raid.recovery",
        "domain": "deniable",
        "payload": {"member": "dax"},
        "created_at": "2026-05-01T03:00:00Z",
    },
]


class RecordingEventStore:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events = events if events is not None else list(EVENTS)
        self.calls: list[dict[str, Any]] = []
        self.append_calls: list[dict[str, Any]] = []

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
        if since_event_id is None:
            tail = list(self.events)
        else:
            seen = False
            tail = []
            for event in self.events:
                if seen:
                    tail.append(event)
                if event["id"] == since_event_id:
                    seen = True
        if domain_filter is not None:
            allowed = (
                {domain_filter}
                if isinstance(domain_filter, str)
                else set(domain_filter)
            )
            tail = [event for event in tail if event.get("domain") in allowed]
        return tail[:limit]

    def append_event(
        self,
        *,
        event_type: str,
        domain: str,
        payload: dict[str, Any],
        created_at: str | None = None,
    ) -> dict[str, Any]:
        self.append_calls.append(
            {
                "event_type": event_type,
                "domain": domain,
                "payload": payload,
                "created_at": created_at,
            }
        )
        event = {
            "id": f"evt-{len(self.events) + 1:03d}",
            "type": event_type,
            "domain": domain,
            "payload": dict(payload),
            "created_at": created_at or "2026-05-01T04:00:00Z",
        }
        self.events.append(event)
        return event


class ExplodingEventStore:
    def list_events(self, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("world db unavailable")

    def append_event(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("world db unavailable")


class TestEventsEndpoint:
    def test_post_raid_completed_event_persists_and_is_readable(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.post(
            "/events",
            json={
                "type": "raid.completed",
                "domain": "deniable",
                "payload": {
                    "raid_id": "raid-17",
                    "outcome": "success",
                    "survivors": ["dax", "mira"],
                },
                "created_at": "2026-05-01T04:15:00Z",
            },
        )

        assert response.status_code == 201
        created = response.json()
        assert created == {
            "id": "evt-005",
            "type": "raid.completed",
            "domain": "deniable",
            "payload": {
                "raid_id": "raid-17",
                "outcome": "success",
                "survivors": ["dax", "mira"],
            },
            "created_at": "2026-05-01T04:15:00Z",
        }
        assert store.append_calls == [
            {
                "event_type": "raid.completed",
                "domain": "deniable",
                "payload": {
                    "raid_id": "raid-17",
                    "outcome": "success",
                    "survivors": ["dax", "mira"],
                },
                "created_at": "2026-05-01T04:15:00Z",
            }
        ]

        list_response = client.get(
            "/events",
            params={"since_event_id": "evt-004", "domain": "deniable"},
        )

        assert list_response.status_code == 200
        listed = list_response.json()
        assert [event["id"] for event in listed["events"]] == ["evt-005"]
        assert listed["events"][0]["payload"]["outcome"] == "success"

    def test_post_event_defaults_domain_to_shared(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.post(
            "/events",
            json={
                "type": "world.note",
                "payload": {"note": "new shared omen"},
            },
        )

        assert response.status_code == 201
        created = response.json()
        assert created["domain"] == "shared"
        assert store.append_calls == [
            {
                "event_type": "world.note",
                "domain": "shared",
                "payload": {"note": "new shared omen"},
                "created_at": None,
            }
        ]

    def test_post_event_rejects_blank_type(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.post(
            "/events",
            json={"type": "   ", "payload": {"note": "bad"}},
        )

        assert response.status_code == 422
        assert store.append_calls == []

    def test_post_event_downstream_failure_returns_502(self) -> None:
        client = TestClient(create_app(event_store=ExplodingEventStore()))

        response = client.post(
            "/events",
            json={
                "type": "raid.completed",
                "domain": "deniable",
                "payload": {"raid_id": "raid-17"},
            },
        )

        assert response.status_code == 502
        assert "world db unavailable" in response.json()["detail"]

    def test_tailing_from_checkpoint_returns_only_newer_events(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get("/events", params={"since_event_id": "evt-002"})

        assert response.status_code == 200
        body = response.json()
        assert [event["id"] for event in body["events"]] == ["evt-003", "evt-004"]
        assert body["next_event_id"] == "evt-004"
        assert store.calls == [
            {
                "since_event_id": "evt-002",
                "domain_filter": None,
                "limit": 100,
            }
        ]

    def test_no_checkpoint_returns_full_log(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get("/events")

        assert response.status_code == 200
        body = response.json()
        assert [event["id"] for event in body["events"]] == [
            "evt-001",
            "evt-002",
            "evt-003",
            "evt-004",
        ]
        assert body["next_event_id"] == "evt-004"

    def test_domain_filter_restricts_results(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get("/events", params={"domain": "deniable"})

        assert response.status_code == 200
        body = response.json()
        assert [event["id"] for event in body["events"]] == ["evt-002", "evt-004"]
        assert store.calls[-1]["domain_filter"] == "deniable"

    def test_repeated_domain_param_passes_list(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get(
            "/events",
            params=[("domain", "deniable"), ("domain", "shared")],
        )

        assert response.status_code == 200
        body = response.json()
        assert [event["id"] for event in body["events"]] == [
            "evt-001",
            "evt-002",
            "evt-004",
        ]
        assert store.calls[-1]["domain_filter"] == ["deniable", "shared"]

    def test_empty_tail_preserves_checkpoint_as_next_id(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get("/events", params={"since_event_id": "evt-004"})

        assert response.status_code == 200
        body = response.json()
        assert body["events"] == []
        assert body["next_event_id"] == "evt-004"

    def test_checkpoint_event_is_excluded_even_if_store_returns_it(self) -> None:
        store = RecordingEventStore(events=list(EVENTS))

        def buggy_list(*, since_event_id, domain_filter, limit):
            store.calls.append(
                {
                    "since_event_id": since_event_id,
                    "domain_filter": domain_filter,
                    "limit": limit,
                }
            )
            return list(EVENTS)

        store.list_events = buggy_list  # type: ignore[method-assign]
        client = TestClient(create_app(event_store=store))

        response = client.get("/events", params={"since_event_id": "evt-002"})

        assert response.status_code == 200
        body = response.json()
        assert "evt-002" not in {event["id"] for event in body["events"]}

    def test_limit_is_passed_through_and_clamped_in_response(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response = client.get("/events", params={"limit": 2})

        assert response.status_code == 200
        body = response.json()
        assert len(body["events"]) == 2
        assert store.calls[-1]["limit"] == 2

    def test_downstream_failure_returns_502(self) -> None:
        client = TestClient(create_app(event_store=ExplodingEventStore()))

        response = client.get("/events")

        assert response.status_code == 502
        assert "world db unavailable" in response.json()["detail"]

    def test_invalid_limit_rejected_before_store(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store))

        response_low = client.get("/events", params={"limit": 0})
        response_high = client.get("/events", params={"limit": 9999})

        assert response_low.status_code == 422
        assert response_high.status_code == 422
        assert store.calls == []

    def test_default_store_missing_returns_503(self) -> None:
        client = TestClient(create_app())

        response = client.get("/events")

        assert response.status_code == 503
        assert "NarrativeEventStore" in response.json()["detail"]

    def test_post_default_store_missing_returns_503(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/events",
            json={"type": "world.note", "payload": {}},
        )

        assert response.status_code == 503
        assert "NarrativeEventStore" in response.json()["detail"]

    def test_event_store_factory_exception_returns_503(self) -> None:
        def boom() -> Any:
            raise RuntimeError("sqlite locked")

        client = TestClient(create_app(event_store_factory=boom))

        response = client.get("/events")

        assert response.status_code == 503
        assert "sqlite locked" in response.json()["detail"]

    def test_auth_enabled_missing_header_returns_401(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store, auth_token="secret"))

        response = client.get("/events")

        assert response.status_code == 401
        assert store.calls == []

    def test_auth_enabled_correct_header_succeeds(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store, auth_token="secret"))

        response = client.get(
            "/events",
            headers={"X-Narrative-Auth": "secret"},
        )

        assert response.status_code == 200
        assert len(store.calls) == 1


class TestEventsAppendAuth:
    def test_auth_enabled_missing_header_returns_401(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store, auth_token="secret"))

        response = client.post(
            "/events",
            json={"type": "raid.completed", "payload": {"raid_id": "raid-17"}},
        )

        assert response.status_code == 401
        assert store.append_calls == []

    def test_auth_enabled_correct_header_succeeds(self) -> None:
        store = RecordingEventStore()
        client = TestClient(create_app(event_store=store, auth_token="secret"))

        response = client.post(
            "/events",
            json={
                "type": "raid.completed",
                "domain": "deniable",
                "payload": {"raid_id": "raid-17"},
            },
            headers={"X-Narrative-Auth": "secret"},
        )

        assert response.status_code == 201
        assert len(store.append_calls) == 1


class NoneAppendingStore:
    """Append returns None to exercise the fallback record-synthesis branch."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def list_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return list(self.events)

    def append_event(
        self,
        *,
        event_type: str,
        domain: str,
        payload: dict[str, Any],
        created_at: str | None = None,
    ) -> None:
        self.events.append(
            {
                "id": f"evt-{len(self.events) + 1:03d}",
                "type": event_type,
                "domain": domain,
                "payload": dict(payload),
                "created_at": created_at,
            }
        )
        return None


class TestEventNormalization:
    def test_append_returning_none_synthesizes_response(self) -> None:
        client = TestClient(create_app(event_store=NoneAppendingStore()))

        response = client.post(
            "/events",
            json={
                "type": "world.bootstrap",
                "domain": "shared",
                "payload": {"note": "n"},
                "created_at": "2026-05-01T05:00:00Z",
            },
        )

        assert response.status_code == 201
        body = response.json()
        # Synthesized record carries forward the submitted fields even though
        # the store returned None.
        assert body["type"] == "world.bootstrap"
        assert body["domain"] == "shared"
        assert body["payload"] == {"note": "n"}
        assert body["created_at"] == "2026-05-01T05:00:00Z"
