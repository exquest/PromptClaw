"""Pydantic schemas for the CypherClaw narrative API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DomainFilter = str | list[str] | None


class MemorySearchRequest(BaseModel):
    """POST /memory/search body."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    domain_filter: DomainFilter = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class MemorySearchResult(BaseModel):
    """Single ranked memory hit returned to HTTP clients."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    text: str
    similarity: float
    domain: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResponse(BaseModel):
    """POST /memory/search response."""

    model_config = ConfigDict(extra="ignore")

    results: list[MemorySearchResult] = Field(default_factory=list)


class NextBeatRequest(BaseModel):
    """POST /beats/next body."""

    model_config = ConfigDict(extra="forbid")

    cycle_number: int = Field(ge=0)
    domain_filter: DomainFilter = Field(...)
    arc_position_target: float | None = Field(default=None, ge=0.0, le=1.0)
    force_arc_event: str | None = None

    @field_validator("force_arc_event")
    @classmethod
    def strip_optional_force_arc_event(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("force_arc_event must not be empty")
        return stripped


class EventRecord(BaseModel):
    """Single narrative event entry returned to HTTP clients."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str | None = None
    domain: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class EventCreateRequest(BaseModel):
    """POST /events body."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    domain: str = Field(default="shared", min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None

    @field_validator("type", "domain")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class EventListResponse(BaseModel):
    """GET /events response."""

    model_config = ConfigDict(extra="ignore")

    events: list[EventRecord] = Field(default_factory=list)
    next_event_id: str | None = None

class EntityRecord(BaseModel):
    """Single world entity returned to HTTP clients."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str | None = None
    name: str | None = None
    domain: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class EntityListResponse(BaseModel):
    """GET /world/entities response."""

    model_config = ConfigDict(extra="ignore")

    entities: list[EntityRecord] = Field(default_factory=list)


class StateMutation(BaseModel):
    """StateMutation payload from the Deniable integration spec."""

    model_config = ConfigDict(extra="forbid")

    target_entity: str | None = None
    operation: Literal["set", "increment", "decrement", "append", "remove"]
    field: str = Field(min_length=1)
    value: Any = None

    @field_validator("target_entity")
    @classmethod
    def strip_optional_target_entity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("target_entity must not be empty")
        return stripped

    @field_validator("field")
    @classmethod
    def strip_field(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be empty")
        return stripped


class EntityMutationRequest(BaseModel):
    """PATCH /world/entities/{entity_id} body."""

    model_config = ConfigDict(extra="forbid")

    mutations: list[StateMutation] = Field(min_length=1)


ENTITY_DOMAIN_WHITELIST: frozenset[str] = frozenset({"shared", "cypherclaw", "deniable"})


class EntityCreateRequest(BaseModel):
    """POST /world/entities body."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    domain: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", "name")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        stripped = value.strip()
        if stripped not in ENTITY_DOMAIN_WHITELIST:
            raise ValueError(
                f"domain must be one of {sorted(ENTITY_DOMAIN_WHITELIST)}"
            )
        return stripped
