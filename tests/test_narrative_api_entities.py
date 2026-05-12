import json
from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cypherclaw.narrative_api.app import create_app

class MockStore:
    def __init__(self, entities):
        self._entities = entities

    def list_entities(self, domain_filter=None, type=None, limit=100, offset=0):
        # A naive store that ignores domain_filter and type, but natively paginates
        return self._entities[offset : offset + limit]

@pytest.fixture
def auth_headers():
    return {"X-Narrative-Auth": "test-token"}

@pytest.fixture
def mock_store():
    # 5 entities with varying domains and types
    return MockStore([
        {"id": "e1", "domain": "shared", "type": "character", "name": "Alice"},
        {"id": "e2", "domain": "deniable", "type": "location", "name": "Secret Base"},
        {"id": "e3", "domain": "private", "type": "character", "name": "Bob"},
        {"id": "e4", "domain": "shared", "type": "item", "name": "Sword"},
        {"id": "e5", "domain": "deniable", "type": "character", "name": "Charlie"},
    ])

@pytest.fixture
def client(mock_store):
    app = create_app(event_store=mock_store, auth_token="test-token")
    return TestClient(app)

def test_entities_domain_deniable(client, auth_headers):
    # Should return deniable + shared entities
    resp = client.get("/world/entities?domain=deniable", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 4
    ids = {e["id"] for e in data["entities"]}
    assert ids == {"e1", "e2", "e4", "e5"}

def test_entities_no_domain(client, auth_headers):
    # Should default to shared
    resp = client.get("/world/entities", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 2
    ids = {e["id"] for e in data["entities"]}
    assert ids == {"e1", "e4"}

def test_entities_type_filter(client, auth_headers):
    # filter by type=character
    resp = client.get("/world/entities?type=character", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 1
    ids = {e["id"] for e in data["entities"]}
    assert ids == {"e1"} # only shared character

def test_entities_pagination(client, auth_headers):
    # Native store paginates before filtering! 
    # With limit=2, offset=0, store returns e1, e2. Filter domain=shared -> returns e1 (len=1)
    # If we fetch with multiplier, it would fetch more and return up to `limit` items.
    resp1 = client.get("/world/entities?limit=2&offset=0", headers=auth_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()["entities"]
    
    resp2 = client.get("/world/entities?limit=2&offset=2", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()["entities"]
    
    # Actually, we want correct pagination for the client.
    # The client asks for limit=2, offset=0. It should get 2 shared items: e1, e4.
    # The client asks for limit=2, offset=2. It should get 0 shared items.
    
    assert len(data1) == 2
    assert {e["id"] for e in data1} == {"e1", "e4"}
    assert len(data2) == 0

def test_entities_unknown_domain(client, auth_headers):
    resp = client.get("/world/entities?domain=unknown_domain", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["entities"]
    assert len(data) == 0

def test_entities_unauth(client):
    resp = client.get("/world/entities")
    assert resp.status_code == 401


class MockStoreWithGet:
    def __init__(self, entities):
        self._by_id = {e["id"]: e for e in entities}

    def list_entities(self, domain_filter=None, type=None, limit=100, offset=0):
        return list(self._by_id.values())[offset : offset + limit]

    def get_entity(self, entity_id):
        return self._by_id.get(entity_id)


@pytest.fixture
def get_client():
    store = MockStoreWithGet([
        {
            "id": "e1",
            "domain": "shared",
            "type": "character",
            "name": "Alice",
            "properties": {"hp": 10, "tags": ["protagonist"]},
        },
        {
            "id": "e2",
            "domain": "deniable",
            "type": "location",
            "name": "Secret Base",
            "properties": {"coords": [1, 2, 3]},
        },
    ])
    app = create_app(event_store=store, auth_token="test-token")
    return TestClient(app)


def test_get_entity_known(get_client, auth_headers):
    resp = get_client.get("/world/entities/e1", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "e1"
    assert data["type"] == "character"
    assert data["name"] == "Alice"
    assert data["domain"] == "shared"
    assert data["properties"] == {"hp": 10, "tags": ["protagonist"]}


def test_get_entity_unknown(get_client, auth_headers):
    resp = get_client.get("/world/entities/missing", headers=auth_headers)
    assert resp.status_code == 404
    assert "missing" in resp.json()["detail"]


def test_get_entity_unauth(get_client):
    resp = get_client.get("/world/entities/e1")
    assert resp.status_code == 401


def test_get_entity_fallback_via_list(auth_headers):
    """When store has no get_entity method, fall back to scanning list_entities."""

    class ListOnlyStore:
        def __init__(self, entities):
            self._entities = entities

        def list_entities(self, domain_filter=None, type=None, limit=100, offset=0):
            return self._entities[offset : offset + limit]

    store = ListOnlyStore([
        {"id": "x1", "domain": "shared", "type": "item", "name": "Lantern"},
        {"id": "x2", "domain": "shared", "type": "item", "name": "Map"},
    ])
    app = create_app(event_store=store, auth_token="test-token")
    client = TestClient(app)

    resp = client.get("/world/entities/x2", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Map"

    resp = client.get("/world/entities/nope", headers=auth_headers)
    assert resp.status_code == 404


class CreatingStore:
    """Mock store that supports list/get/create with auto-assigned IDs."""

    def __init__(self):
        self._by_id: dict[str, dict] = {}
        self._counter = 0
        self.create_calls: list[dict] = []

    def list_entities(self, domain_filter=None, type=None, limit=100, offset=0):
        return list(self._by_id.values())[offset : offset + limit]

    def get_entity(self, entity_id):
        return self._by_id.get(entity_id)

    def create_entity(self, *, type, name, domain, properties):
        self.create_calls.append(
            {
                "type": type,
                "name": name,
                "domain": domain,
                "properties": dict(properties),
            }
        )
        self._counter += 1
        entity_id = f"ent-{self._counter:03d}"
        record = {
            "id": entity_id,
            "type": type,
            "name": name,
            "domain": domain,
            "properties": dict(properties),
        }
        self._by_id[entity_id] = record
        return record


class ExplodingCreateStore:
    def list_entities(self, **kwargs):
        return []

    def get_entity(self, entity_id):
        return None

    def create_entity(self, **kwargs):
        raise RuntimeError("world db unavailable")


class TestCreateEntityEndpoint:
    def test_create_squad_member_round_trips_via_get(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        payload = {
            "type": "character",
            "name": "Dax",
            "domain": "deniable",
            "properties": {
                "role": "squad-member",
                "current_state": "healthy",
                "tags": ["fighter", "wolfpack"],
            },
        }
        resp = client.post("/world/entities", json=payload, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"]
        assert body["type"] == "character"
        assert body["name"] == "Dax"
        assert body["domain"] == "deniable"
        assert body["properties"] == {
            "role": "squad-member",
            "current_state": "healthy",
            "tags": ["fighter", "wolfpack"],
        }
        assert store.create_calls == [
            {
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {
                    "role": "squad-member",
                    "current_state": "healthy",
                    "tags": ["fighter", "wolfpack"],
                },
            }
        ]

        get_resp = client.get(f"/world/entities/{body['id']}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json() == body

    def test_rejects_unknown_domain_before_store(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Mira",
                "domain": "private",
                "properties": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert store.create_calls == []

    def test_rejects_blank_type_or_name_before_store(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        blank_type = client.post(
            "/world/entities",
            json={"type": "   ", "name": "Mira", "domain": "shared"},
            headers=headers,
        )
        assert blank_type.status_code == 422

        blank_name = client.post(
            "/world/entities",
            json={"type": "character", "name": "", "domain": "shared"},
            headers=headers,
        )
        assert blank_name.status_code == 422

        missing_type = client.post(
            "/world/entities",
            json={"name": "Mira", "domain": "shared"},
            headers=headers,
        )
        assert missing_type.status_code == 422

        missing_name = client.post(
            "/world/entities",
            json={"type": "character", "domain": "shared"},
            headers=headers,
        )
        assert missing_name.status_code == 422

        assert store.create_calls == []

    def test_accepts_each_whitelisted_domain(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        for domain in ("shared", "cypherclaw", "deniable"):
            resp = client.post(
                "/world/entities",
                json={
                    "type": "character",
                    "name": f"Char-{domain}",
                    "domain": domain,
                    "properties": {},
                },
                headers=headers,
            )
            assert resp.status_code == 201, f"domain={domain} failed: {resp.text}"
            assert resp.json()["domain"] == domain

    def test_downstream_store_failure_returns_502(self):
        client = TestClient(
            create_app(event_store=ExplodingCreateStore(), auth_token="test-token")
        )
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {},
            },
            headers=headers,
        )
        assert resp.status_code == 502
        assert "world db unavailable" in resp.json()["detail"]

    def test_default_store_missing_returns_503(self):
        client = TestClient(create_app(auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {},
            },
            headers=headers,
        )
        assert resp.status_code == 503

    def test_partial_store_response_falls_back_to_request_input(self):
        class PartialReturnStore:
            def create_entity(self, **kwargs):
                return {"id": "ent-xyz"}

        client = TestClient(
            create_app(event_store=PartialReturnStore(), auth_token="test-token")
        )
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {"role": "squad-member"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body == {
            "id": "ent-xyz",
            "type": "character",
            "name": "Dax",
            "domain": "deniable",
            "properties": {"role": "squad-member"},
        }

    def test_store_without_id_surfaces_502(self):
        class NoIdStore:
            def create_entity(self, **kwargs):
                return None

        client = TestClient(
            create_app(event_store=NoIdStore(), auth_token="test-token")
        )
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {},
            },
            headers=headers,
        )
        assert resp.status_code == 502

    def test_record_dict_store_signature_supported(self):
        """Stores that take a single 'entity' mapping arg are supported."""

        class RecordDictStore:
            def __init__(self):
                self.received: list[dict] = []

            def create_entity(self, entity):
                self.received.append(entity)
                return {**entity, "id": "ent-rd-1"}

        store = RecordDictStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Mira",
                "domain": "deniable",
                "properties": {"role": "scout"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "ent-rd-1"
        assert body["name"] == "Mira"
        assert store.received == [
            {
                "type": "character",
                "name": "Mira",
                "domain": "deniable",
                "properties": {"role": "scout"},
            }
        ]

    def test_auth_enabled_missing_header_returns_401(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {},
            },
        )
        assert resp.status_code == 401
        assert store.create_calls == []

    def test_auth_enabled_correct_header_succeeds(self):
        store = CreatingStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))

        resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {},
            },
            headers={"X-Narrative-Auth": "test-token"},
        )
        assert resp.status_code == 201


class MutableEntityStore:
    """Entity store with explicit update persistence for PATCH tests."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {
            "fighter-1": {
                "id": "fighter-1",
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {
                    "archetype": "marksman",
                    "stats": {"combat": 4, "tech": 2, "resolve": 3},
                    "current_state": "healthy",
                    "campaign_xp": 12,
                    "skills": ["marksman"],
                    "permanent_injuries": ["bruise", "scar"],
                },
            }
        }
        self.update_calls: list[dict[str, Any]] = []

    def list_entities(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [deepcopy(entity) for entity in self._by_id.values()]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        entity = self._by_id.get(entity_id)
        return deepcopy(entity) if entity is not None else None

    def update_entity(
        self,
        *,
        entity_id: str,
        entity: dict[str, Any],
    ) -> dict[str, Any]:
        self.update_calls.append(
            {"entity_id": entity_id, "entity": deepcopy(entity)}
        )
        self._by_id[entity_id] = deepcopy(entity)
        return deepcopy(entity)


class ExplodingUpdateStore(MutableEntityStore):
    def update_entity(
        self,
        *,
        entity_id: str,
        entity: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("sqlite locked")


class TestPatchEntityEndpoint:
    def test_set_current_state_persists_and_round_trips(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "target_entity": "fighter-1",
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            headers=headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "fighter-1"
        assert body["properties"]["current_state"] == "wounded"
        assert store.update_calls == [
            {
                "entity_id": "fighter-1",
                "entity": {
                    "id": "fighter-1",
                    "type": "character",
                    "name": "Dax",
                    "domain": "deniable",
                    "properties": {
                        "archetype": "marksman",
                        "stats": {"combat": 4, "tech": 2, "resolve": 3},
                        "current_state": "wounded",
                        "campaign_xp": 12,
                        "skills": ["marksman"],
                        "permanent_injuries": ["bruise", "scar"],
                    },
                },
            }
        ]

        get_resp = client.get("/world/entities/fighter-1", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["properties"]["current_state"] == "wounded"

    def test_applies_numeric_list_and_nested_mutations_in_order(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "operation": "increment",
                        "field": "stats.combat",
                        "value": 2,
                    },
                    {
                        "operation": "decrement",
                        "field": "campaign_xp",
                        "value": 3,
                    },
                    {
                        "operation": "append",
                        "field": "skills",
                        "value": "field_medic",
                    },
                    {
                        "operation": "remove",
                        "field": "permanent_injuries",
                        "value": "bruise",
                    },
                    {
                        "operation": "set",
                        "field": "recovery.until_raid",
                        "value": 2,
                    },
                ]
            },
            headers=headers,
        )

        assert resp.status_code == 200
        properties = resp.json()["properties"]
        assert properties["stats"]["combat"] == 6
        assert properties["campaign_xp"] == 9
        assert properties["skills"] == ["marksman", "field_medic"]
        assert properties["permanent_injuries"] == ["scar"]
        assert properties["recovery"] == {"until_raid": 2}
        assert len(store.update_calls) == 1

    def test_accepts_single_state_mutation_payload(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "target_entity": "fighter-1",
                "operation": "set",
                "field": "properties.current_state",
                "value": "exhausted",
            },
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["properties"]["current_state"] == "exhausted"
        assert store.get_entity("fighter-1")["properties"]["current_state"] == (
            "exhausted"
        )

    def test_rejects_invalid_mutations_without_persisting(self):
        cases = [
            {
                "mutations": [
                    {
                        "target_entity": "other",
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            {"mutations": []},
            {
                "mutations": [
                    {
                        "operation": "set",
                        "field": "id",
                        "value": "other-id",
                    }
                ]
            },
            {
                "mutations": [
                    {
                        "operation": "set",
                        "field": "stats..combat",
                        "value": 7,
                    }
                ]
            },
            {
                "mutations": [
                    {
                        "operation": "increment",
                        "field": "stats.combat",
                        "value": "two",
                    }
                ]
            },
            {
                "mutations": [
                    {
                        "operation": "increment",
                        "field": "current_state",
                        "value": 1,
                    }
                ]
            },
        ]

        for payload in cases:
            store = MutableEntityStore()
            client = TestClient(
                create_app(event_store=store, auth_token="test-token")
            )

            resp = client.patch(
                "/world/entities/fighter-1",
                json=payload,
                headers={"X-Narrative-Auth": "test-token"},
            )

            assert resp.status_code == 422, payload
            assert store.update_calls == []
            assert (
                store.get_entity("fighter-1")["properties"]["current_state"]
                == "healthy"
            )

    def test_missing_entity_returns_404(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))

        resp = client.patch(
            "/world/entities/missing",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            headers={"X-Narrative-Auth": "test-token"},
        )

        assert resp.status_code == 404
        assert store.update_calls == []

    def test_downstream_update_failure_returns_502(self):
        client = TestClient(
            create_app(event_store=ExplodingUpdateStore(), auth_token="test-token")
        )

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            headers={"X-Narrative-Auth": "test-token"},
        )

        assert resp.status_code == 502
        assert "sqlite locked" in resp.json()["detail"]

    def test_default_store_missing_returns_503(self):
        client = TestClient(create_app(auth_token="test-token"))

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            headers={"X-Narrative-Auth": "test-token"},
        )

        assert resp.status_code == 503

    def test_auth_enabled_missing_header_returns_401(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
        )

        assert resp.status_code == 401
        assert store.update_calls == []

    def test_auth_enabled_correct_header_succeeds(self):
        store = MutableEntityStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))

        resp = client.patch(
            "/world/entities/fighter-1",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    }
                ]
            },
            headers={"X-Narrative-Auth": "test-token"},
        )

        assert resp.status_code == 200


class NarrativeEntityLifecycleStore:
    """In-memory world store covering list/get/create/update for one workflow."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {
            "guide-shared": {
                "id": "guide-shared",
                "type": "character",
                "name": "Mira",
                "domain": "shared",
                "properties": {"role": "handler", "skills": ["logistics"]},
            },
            "hideout-1": {
                "id": "hideout-1",
                "type": "location",
                "name": "Old Relay",
                "domain": "deniable",
                "properties": {"security": 2},
            },
            "studio-voice": {
                "id": "studio-voice",
                "type": "character",
                "name": "Cypher Muse",
                "domain": "cypherclaw",
                "properties": {"role": "artist"},
            },
        }
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def list_entities(self, **kwargs: Any) -> list[dict[str, Any]]:
        limit = int(kwargs.get("limit", 100))
        offset = int(kwargs.get("offset", 0))
        records = [deepcopy(entity) for entity in self._by_id.values()]
        return records[offset : offset + limit]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        entity = self._by_id.get(entity_id)
        return deepcopy(entity) if entity is not None else None

    def create_entity(
        self,
        *,
        type: str,
        name: str,
        domain: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                "type": type,
                "name": name,
                "domain": domain,
                "properties": deepcopy(properties),
            }
        )
        entity_id = f"entity-{len(self._by_id) + 1:03d}"
        entity = {
            "id": entity_id,
            "type": type,
            "name": name,
            "domain": domain,
            "properties": deepcopy(properties),
        }
        self._by_id[entity_id] = deepcopy(entity)
        return entity

    def update_entity(
        self,
        *,
        entity_id: str,
        entity: dict[str, Any],
    ) -> dict[str, Any]:
        self.update_calls.append(
            {
                "entity_id": entity_id,
                "entity": deepcopy(entity),
            }
        )
        self._by_id[entity_id] = deepcopy(entity)
        return deepcopy(entity)


class NarrativeApiEntitiesEndToEndTests:
    __test__ = True

    def test_deniable_entity_lifecycle_is_json_safe(self) -> None:
        store = NarrativeEntityLifecycleStore()
        client = TestClient(create_app(event_store=store, auth_token="test-token"))
        headers = {"X-Narrative-Auth": "test-token"}

        create_resp = client.post(
            "/world/entities",
            json={
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {
                    "role": "squad-member",
                    "current_state": "healthy",
                    "stats": {"combat": 4, "tech": 2},
                    "skills": ["marksman"],
                },
            },
            headers=headers,
        )

        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created == {
            "id": "entity-004",
            "type": "character",
            "name": "Dax",
            "domain": "deniable",
            "properties": {
                "role": "squad-member",
                "current_state": "healthy",
                "stats": {"combat": 4, "tech": 2},
                "skills": ["marksman"],
            },
        }
        assert store.create_calls == [
            {
                "type": "character",
                "name": "Dax",
                "domain": "deniable",
                "properties": {
                    "role": "squad-member",
                    "current_state": "healthy",
                    "stats": {"combat": 4, "tech": 2},
                    "skills": ["marksman"],
                },
            }
        ]

        patch_resp = client.patch(
            f"/world/entities/{created['id']}",
            json={
                "mutations": [
                    {
                        "operation": "set",
                        "field": "current_state",
                        "value": "wounded",
                    },
                    {
                        "operation": "increment",
                        "field": "stats.combat",
                        "value": 1,
                    },
                    {
                        "operation": "append",
                        "field": "skills",
                        "value": "field_medic",
                    },
                    {
                        "operation": "set",
                        "field": "recovery.until_raid",
                        "value": 2,
                    },
                ]
            },
            headers=headers,
        )

        assert patch_resp.status_code == 200
        updated = patch_resp.json()
        assert updated["id"] == created["id"]
        assert updated["properties"]["current_state"] == "wounded"
        assert updated["properties"]["stats"] == {"combat": 5, "tech": 2}
        assert updated["properties"]["skills"] == ["marksman", "field_medic"]
        assert updated["properties"]["recovery"] == {"until_raid": 2}
        assert store.update_calls == [
            {
                "entity_id": "entity-004",
                "entity": updated,
            }
        ]

        get_resp = client.get(f"/world/entities/{created['id']}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json() == updated

        list_resp = client.get(
            "/world/entities",
            params={"domain": "deniable", "type": "character", "limit": 10},
            headers=headers,
        )
        assert list_resp.status_code == 200
        visible_entities = list_resp.json()["entities"]
        assert [entity["id"] for entity in visible_entities] == [
            "guide-shared",
            "entity-004",
        ]
        assert {entity["domain"] for entity in visible_entities} == {
            "shared",
            "deniable",
        }

        diagnostic = {
            "created": created,
            "updated": updated,
            "visible_entities": visible_entities,
            "store_calls": {
                "created": store.create_calls,
                "updated": store.update_calls,
            },
        }
        decoded = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert decoded["updated"]["properties"]["current_state"] == "wounded"
        assert decoded["updated"]["properties"]["stats"]["combat"] == 5
        assert [entity["id"] for entity in decoded["visible_entities"]] == [
            "guide-shared",
            "entity-004",
        ]
