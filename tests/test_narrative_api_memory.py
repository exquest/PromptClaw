"""Tests for the CypherClaw narrative memory HTTP endpoint."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from cypherclaw.narrative_api.app import create_app


class RecordingMemory:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def semantic_search(
        self,
        query: str,
        k: int,
        domain_filter: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {"query": query, "k": k, "domain_filter": domain_filter}
        )
        return [
            {
                "id": "shared-low",
                "text": "Dax remembered a quiet promise after extraction.",
                "similarity": 0.31,
                "domain": "shared",
                "metadata": {"source": "event-log"},
            },
            {
                "id": "cypherclaw-high",
                "text": "A CypherClaw-only studio memory.",
                "similarity": 0.99,
                "domain": "cypherclaw",
            },
            {
                "id": "deniable-best",
                "content": "Dax was betrayed by an old commander.",
                "score": 0.93,
                "metadata": {"domain": "deniable", "source": "memory"},
            },
            {
                "id": "deniable-mid",
                "text": "The squad debated whether Dax could still be trusted.",
                "similarity": 0.72,
                "domain": "deniable",
            },
        ]


class SingleDomainMemory:
    def semantic_search(
        self,
        query: str,
        k: int,
        domain_filter: str | list[str] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        return [
            ("shared signal", 0.51, {"id": "shared-hit", "domain": "shared"}),
            (
                "deniable signal",
                0.86,
                {"id": "deniable-hit", "domain": "deniable"},
            ),
        ]


class ExplodingMemory:
    def semantic_search(
        self,
        query: str,
        k: int,
        domain_filter: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("ollama unavailable")


class TestMemorySearchEndpoint:
    def test_returns_ranked_results_and_honors_domain_filter(self) -> None:
        memory = RecordingMemory()
        client = TestClient(create_app(memory=memory))

        response = client.post(
            "/memory/search",
            json={
                "query": "Dax betrayal",
                "k": 3,
                "domain_filter": ["deniable", "shared"],
            },
        )

        assert response.status_code == 200
        assert memory.calls == [
            {
                "query": "Dax betrayal",
                "k": 3,
                "domain_filter": ["deniable", "shared"],
            }
        ]
        body = response.json()
        assert [result["id"] for result in body["results"]] == [
            "deniable-best",
            "deniable-mid",
            "shared-low",
        ]
        assert [result["similarity"] for result in body["results"]] == [
            0.93,
            0.72,
            0.31,
        ]
        assert {result["domain"] for result in body["results"]} == {
            "deniable",
            "shared",
        }
        assert "cypherclaw-high" not in {
            result["id"] for result in body["results"]
        }

    def test_accepts_single_domain_filter_string(self) -> None:
        client = TestClient(create_app(memory=SingleDomainMemory()))

        response = client.post(
            "/memory/search",
            json={"query": "shared signal", "k": 5, "domain_filter": "shared"},
        )

        assert response.status_code == 200
        body = response.json()
        assert [result["id"] for result in body["results"]] == ["shared-hit"]
        assert body["results"][0]["text"] == "shared signal"
        assert body["results"][0]["domain"] == "shared"

    def test_rejects_empty_query(self) -> None:
        memory = RecordingMemory()
        client = TestClient(create_app(memory=memory))

        response = client.post(
            "/memory/search",
            json={"query": "   ", "k": 3, "domain_filter": "shared"},
        )

        assert response.status_code == 422
        assert memory.calls == []

    def test_downstream_memory_failure_returns_502(self) -> None:
        client = TestClient(create_app(memory=ExplodingMemory()))

        response = client.post(
            "/memory/search",
            json={"query": "Dax betrayal", "k": 3, "domain_filter": "shared"},
        )

        assert response.status_code == 502
        assert "ollama unavailable" in response.json()["detail"]

    def test_default_searcher_missing_returns_503(self) -> None:
        # No memory injected and the deploy-side cypherclaw.narrative.memory
        # package is not present in this checkout, so the lazy import fails.
        client = TestClient(create_app())

        response = client.post(
            "/memory/search",
            json={"query": "Dax betrayal", "k": 3},
        )

        assert response.status_code == 503
        assert "NarrativeMemory" in response.json()["detail"]

    def test_memory_factory_exception_returns_503(self) -> None:
        def boom() -> Any:
            raise RuntimeError("torch not installed")

        client = TestClient(create_app(memory_factory=boom))

        response = client.post(
            "/memory/search",
            json={"query": "Dax betrayal", "k": 3},
        )

        assert response.status_code == 503
        assert "torch not installed" in response.json()["detail"]

    def test_auth_enabled_missing_header_returns_401(self) -> None:
        client = TestClient(
            create_app(memory=RecordingMemory(), auth_token="secret")
        )

        response = client.post(
            "/memory/search",
            json={"query": "Dax", "k": 3, "domain_filter": "shared"},
        )

        assert response.status_code == 401
        assert "auth" in response.json()["detail"].lower()

    def test_auth_enabled_wrong_token_returns_401(self) -> None:
        client = TestClient(
            create_app(memory=RecordingMemory(), auth_token="secret")
        )

        response = client.post(
            "/memory/search",
            json={"query": "Dax", "k": 3, "domain_filter": "shared"},
            headers={"X-Narrative-Auth": "wrong"},
        )

        assert response.status_code == 401

    def test_auth_enabled_correct_header_succeeds(self) -> None:
        memory = RecordingMemory()
        client = TestClient(create_app(memory=memory, auth_token="secret"))

        response = client.post(
            "/memory/search",
            json={"query": "Dax betrayal", "k": 3, "domain_filter": "deniable"},
            headers={"X-Narrative-Auth": "secret"},
        )

        assert response.status_code == 200
        assert len(memory.calls) == 1

    def test_empty_auth_token_disables_auth(self) -> None:
        memory = RecordingMemory()
        # Empty string mirrors "unset" semantics of T-010 — auth disabled.
        client = TestClient(create_app(memory=memory, auth_token=""))

        response = client.post(
            "/memory/search",
            json={"query": "Dax", "k": 3, "domain_filter": "shared"},
        )

        assert response.status_code == 200


class TupleMemoryWithDistance:
    def semantic_search(
        self,
        query: str,
        k: int,
        domain_filter: str | list[str] | None = None,
    ) -> list[Any]:
        return [
            {"id": "a", "content": "raw distance hit", "distance": 0.2, "domain": "shared"},
            {"id": "b", "text": "no score hit", "domain": "shared"},
            ("plain string only",),
        ]


class TestMemoryNormalization:
    def test_distance_and_missing_score_branches_render(self) -> None:
        client = TestClient(create_app(memory=TupleMemoryWithDistance()))

        response = client.post(
            "/memory/search",
            json={"query": "raw", "k": 5, "domain_filter": "shared"},
        )

        assert response.status_code == 200
        body = response.json()
        ids = [r["id"] for r in body["results"]]
        assert "a" in ids
        # The distance-based hit's similarity is 1.0 - 0.2 = 0.8, leading
        a_hit = next(r for r in body["results"] if r["id"] == "a")
        assert a_hit["similarity"] == 0.8
        b_hit = next(r for r in body["results"] if r["id"] == "b")
        assert b_hit["similarity"] == 0.0
