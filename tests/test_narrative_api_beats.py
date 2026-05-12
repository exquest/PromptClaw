"""Tests for the CypherClaw narrative beat HTTP endpoint."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from cypherclaw.narrative_api.app import create_app
from cypherclaw.narrative_api.beats import serialize_story_beat


class RecordingNarrativeEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def next_beat(
        self,
        *,
        cycle_number: int,
        domain_filter: str | list[str] | None,
        arc_position_target: float | None = None,
        force_arc_event: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "cycle_number": cycle_number,
                "domain_filter": domain_filter,
                "arc_position_target": arc_position_target,
                "force_arc_event": force_arc_event,
            }
        )
        return {
            "id": "beat-007",
            "cycle_number": cycle_number,
            "arc_position": 0.5,
            "active_characters": ["fighter-dax"],
            "tone_vector": {"tension": 0.8, "hope": 0.2},
            "prose_description": "Dax hears the old commander on a jammed channel.",
        }


class MinimalShapeEngine:
    def next_beat(
        self,
        *,
        cycle_number: int,
        domain_filter: str | list[str] | None,
    ) -> dict[str, Any]:
        return {
            "id": "beat-min",
            "cycle_number": cycle_number,
            "arc_position": 0.25,
            "custom_payload": {"domain_filter": domain_filter},
        }


class ExplodingNarrativeEngine:
    def next_beat(self, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("ollama refused beat generation")


class ShouldNotBeCalledEngine:
    def __init__(self) -> None:
        self.calls = 0

    def next_beat(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"id": "should-not-return"}


class TestBeatsNextEndpoint:
    def test_returns_story_beat_from_injected_engine(self) -> None:
        engine = RecordingNarrativeEngine()
        client = TestClient(create_app(narrative_engine=engine))

        response = client.post(
            "/beats/next",
            json={
                "cycle_number": 7,
                "domain_filter": "deniable",
                "arc_position_target": 0.5,
                "force_arc_event": "act_i_loss",
            },
        )

        assert response.status_code == 200
        assert engine.calls == [
            {
                "cycle_number": 7,
                "domain_filter": "deniable",
                "arc_position_target": 0.5,
                "force_arc_event": "act_i_loss",
            }
        ]
        assert response.json() == {
            "id": "beat-007",
            "cycle_number": 7,
            "arc_position": 0.5,
            "active_characters": ["fighter-dax"],
            "tone_vector": {"tension": 0.8, "hope": 0.2},
            "prose_description": "Dax hears the old commander on a jammed channel.",
        }

    def test_preserves_mapping_story_beat_shape(self) -> None:
        client = TestClient(create_app(narrative_engine=MinimalShapeEngine()))

        response = client.post(
            "/beats/next",
            json={"cycle_number": 3, "domain_filter": ["deniable", "shared"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "id": "beat-min",
            "cycle_number": 3,
            "arc_position": 0.25,
            "custom_payload": {"domain_filter": ["deniable", "shared"]},
        }
        assert "session_id" not in body
        assert "active_themes" not in body
        assert "passed_evaluation" not in body

    def test_rejects_invalid_arc_position_before_engine(self) -> None:
        engine = ShouldNotBeCalledEngine()
        client = TestClient(create_app(narrative_engine=engine))

        response = client.post(
            "/beats/next",
            json={
                "cycle_number": 1,
                "domain_filter": "deniable",
                "arc_position_target": 1.5,
            },
        )

        assert response.status_code == 422
        assert engine.calls == 0

    def test_rejects_blank_force_arc_event_before_engine(self) -> None:
        engine = ShouldNotBeCalledEngine()
        client = TestClient(create_app(narrative_engine=engine))

        response = client.post(
            "/beats/next",
            json={
                "cycle_number": 1,
                "domain_filter": "deniable",
                "force_arc_event": "   ",
            },
        )

        assert response.status_code == 422
        assert engine.calls == 0

    def test_downstream_engine_failure_returns_502(self) -> None:
        client = TestClient(create_app(narrative_engine=ExplodingNarrativeEngine()))

        response = client.post(
            "/beats/next",
            json={"cycle_number": 4, "domain_filter": "deniable"},
        )

        assert response.status_code == 502
        assert "ollama refused beat generation" in response.json()["detail"]

    def test_default_engine_missing_returns_503(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/beats/next",
            json={"cycle_number": 4, "domain_filter": "deniable"},
        )

        assert response.status_code == 503
        assert "NarrativeEngine" in response.json()["detail"]

    def test_auth_enabled_missing_header_returns_401(self) -> None:
        engine = RecordingNarrativeEngine()
        client = TestClient(
            create_app(narrative_engine=engine, auth_token="secret")
        )

        response = client.post(
            "/beats/next",
            json={"cycle_number": 7, "domain_filter": "deniable"},
        )

        assert response.status_code == 401
        assert engine.calls == []

    def test_auth_enabled_correct_header_succeeds(self) -> None:
        engine = RecordingNarrativeEngine()
        client = TestClient(
            create_app(narrative_engine=engine, auth_token="secret")
        )

        response = client.post(
            "/beats/next",
            json={"cycle_number": 7, "domain_filter": "deniable"},
            headers={"X-Narrative-Auth": "secret"},
        )

        assert response.status_code == 200
        assert len(engine.calls) == 1


@dataclass(frozen=True)
class NestedGlyphPrompt:
    scene_type: str
    palette_name: str


@dataclass(frozen=True)
class DataclassStoryBeat:
    id: str
    cycle_number: int
    arc_position: float
    active_characters: tuple[str, ...]
    glyph_prompt: NestedGlyphPrompt


class TestBeatSerialization:
    def test_serializes_dataclass_story_beat_with_nested_values(self) -> None:
        result = serialize_story_beat(
            DataclassStoryBeat(
                id="beat-dc",
                cycle_number=9,
                arc_position=0.75,
                active_characters=("fighter-dax", "handler-mira"),
                glyph_prompt=NestedGlyphPrompt(
                    scene_type="status_display",
                    palette_name="PALETTE_NIGHT",
                ),
            )
        )

        assert result == {
            "id": "beat-dc",
            "cycle_number": 9,
            "arc_position": 0.75,
            "active_characters": ["fighter-dax", "handler-mira"],
            "glyph_prompt": {
                "scene_type": "status_display",
                "palette_name": "PALETTE_NIGHT",
            },
        }
