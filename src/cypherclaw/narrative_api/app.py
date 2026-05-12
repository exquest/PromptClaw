"""FastAPI app exposing the CypherClaw narrative API."""
from __future__ import annotations

import importlib
import logging
import time
import urllib.request
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from .beats import (
    NarrativeEngineUnavailableError,
    build_default_narrative_engine,
    generate_next_beat,
)
from .entities import (
    apply_world_entity_mutations,
    create_world_entity,
    get_world_entity,
    list_world_entities,
)
from .events import (
    EventStoreUnavailableError,
    append_world_event,
    build_default_event_store,
    list_world_events,
)
from .log_config import StructlogRequestMiddleware, setup_logging
from .memory import (
    MemoryUnavailableError,
    build_default_memory,
    search_narrative_memory,
)
from .schemas import (
    EntityCreateRequest,
    EntityListResponse,
    EntityMutationRequest,
    EntityRecord,
    EventCreateRequest,
    EventListResponse,
    EventRecord,
    MemorySearchRequest,
    MemorySearchResponse,
    NextBeatRequest,
    StateMutation,
)

logger = logging.getLogger(__name__)

MemoryFactory = Callable[[], Any]
EventStoreFactory = Callable[[], Any]
NarrativeEngineFactory = Callable[[], Any]
HealthChecker = Callable[[], bool]


def create_app(
    *,
    memory: Any | None = None,
    memory_factory: MemoryFactory | None = None,
    event_store: Any | None = None,
    event_store_factory: EventStoreFactory | None = None,
    narrative_engine: Any | None = None,
    narrative_engine_factory: NarrativeEngineFactory | None = None,
    narrative_engine_checker: HealthChecker | None = None,
    ollama_checker: HealthChecker | None = None,
    auth_token: str | None = None,
) -> FastAPI:
    """Create the narrative API app.

    Tests inject ``memory``, ``event_store``, and ``narrative_engine`` directly.
    Production leaves them unset so request paths lazily import the deploy-side
    implementations.

    When ``auth_token`` is a non-empty string, every endpoint requires the
    request to carry a matching ``X-Narrative-Auth`` header. When unset or
    empty, auth is disabled. T-010 owns the env-var pull and startup warning.
    """

    app = FastAPI(title="cypherclaw-narrative-api", version="0.1.0")
    setup_logging()
    app.add_middleware(StructlogRequestMiddleware)
    started_at = time.monotonic()

    if not auth_token:
        logger.warning(
            "NARRATIVE_AUTH_TOKEN is unset or empty; shared-secret auth is disabled."
        )

    def require_auth(
        x_narrative_auth: str | None = Header(default=None),
    ) -> None:
        if not auth_token:
            return
        if x_narrative_auth != auth_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing narrative auth token",
            )

    def get_memory() -> Any:
        if memory is not None:
            return memory
        if memory_factory is not None:
            return memory_factory()
        return build_default_memory()

    def get_event_store() -> Any:
        if event_store is not None:
            return event_store
        if event_store_factory is not None:
            return event_store_factory()
        return build_default_event_store()

    def get_narrative_engine() -> Any:
        if narrative_engine is not None:
            return narrative_engine
        if narrative_engine_factory is not None:
            return narrative_engine_factory()
        return build_default_narrative_engine()

    def check_world_db() -> bool:
        store = get_event_store()
        list_world_events(
            store,
            since_event_id=None,
            domain_filter=None,
            limit=1,
        )
        return True

    @app.get("/health")
    def health() -> dict[str, object]:
        narrative_engine_importable = _run_health_check(
            narrative_engine_checker or _default_narrative_engine_importable
        )
        world_db_reachable = _run_health_check(check_world_db)
        ollama_reachable = _run_health_check(
            ollama_checker or _default_ollama_reachable
        )
        healthy = (
            narrative_engine_importable
            and world_db_reachable
            and ollama_reachable
        )
        return {
            "status": "ok" if healthy else "degraded",
            "narrative_engine_importable": narrative_engine_importable,
            "world_db_reachable": world_db_reachable,
            "ollama_reachable": ollama_reachable,
            "version": app.version,
            "uptime_seconds": time.monotonic() - started_at,
        }

    @app.post(
        "/memory/search",
        response_model=MemorySearchResponse,
        dependencies=[Depends(require_auth)],
    )
    def memory_search(payload: MemorySearchRequest) -> MemorySearchResponse:
        try:
            searcher = get_memory()
        except MemoryUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"memory searcher unavailable: {exc}",
            ) from exc

        try:
            results = search_narrative_memory(
                searcher,
                query=payload.query,
                k=payload.k,
                domain_filter=payload.domain_filter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("NarrativeMemory search failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"memory search failed: {exc}",
            ) from exc

        return MemorySearchResponse(results=results)

    @app.post(
        "/beats/next",
        dependencies=[Depends(require_auth)],
    )
    def beats_next(payload: NextBeatRequest) -> dict[str, Any]:
        try:
            engine = get_narrative_engine()
        except NarrativeEngineUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"narrative engine unavailable: {exc}",
            ) from exc

        try:
            return generate_next_beat(
                engine,
                cycle_number=payload.cycle_number,
                domain_filter=payload.domain_filter,
                arc_position_target=payload.arc_position_target,
                force_arc_event=payload.force_arc_event,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("NarrativeEngine next_beat failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"beat generation failed: {exc}",
            ) from exc

    @app.get(
        "/world/entities",
        response_model=EntityListResponse,
        dependencies=[Depends(require_auth)],
    )
    def world_entities_list(
        domain: list[str] | None = Query(default=None),
        type: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> EntityListResponse:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"world store unavailable: {exc}",
            ) from exc

        # If domain isn't provided, default to "shared" per acceptance criteria.
        # Acceptance criteria: "Query with domain=deniable returns only Deniable + shared entities"
        if not domain:
            domain_filter: list[str] | str = "shared"
        else:
            domain_filter = domain + ["shared"] if "deniable" in domain and "shared" not in domain else domain

        try:
            entities = list_world_entities(
                store,
                domain_filter=domain_filter,
                entity_type=type,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("world store list_entities failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"entity listing failed: {exc}",
            ) from exc

        return EntityListResponse(entities=entities)

    @app.post(
        "/world/entities",
        response_model=EntityRecord,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_auth)],
    )
    def world_entity_create(payload: EntityCreateRequest) -> EntityRecord:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"world store unavailable: {exc}",
            ) from exc

        try:
            record = create_world_entity(
                store,
                entity_type=payload.type,
                name=payload.name,
                domain=payload.domain,
                properties=payload.properties,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("world store create_entity failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"entity creation failed: {exc}",
            ) from exc

        if not record.id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="world store returned no entity id",
            )
        return record

    @app.patch(
        "/world/entities/{entity_id}",
        response_model=EntityRecord,
        dependencies=[Depends(require_auth)],
    )
    def world_entity_patch(
        entity_id: str,
        payload: EntityMutationRequest | StateMutation,
    ) -> EntityRecord:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"world store unavailable: {exc}",
            ) from exc

        mutations = (
            payload.mutations
            if isinstance(payload, EntityMutationRequest)
            else [payload]
        )
        try:
            entity = apply_world_entity_mutations(
                store,
                entity_id=entity_id,
                mutations=mutations,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("world store update_entity failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"entity update failed: {exc}",
            ) from exc

        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"entity not found: {entity_id}",
            )
        return entity

    @app.get(
        "/world/entities/{entity_id}",
        response_model=EntityRecord,
        dependencies=[Depends(require_auth)],
    )
    def world_entity_get(entity_id: str) -> EntityRecord:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"world store unavailable: {exc}",
            ) from exc

        try:
            entity = get_world_entity(store, entity_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("world store get_entity failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"entity lookup failed: {exc}",
            ) from exc

        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"entity not found: {entity_id}",
            )
        return entity

    @app.get(
        "/events",
        response_model=EventListResponse,
        dependencies=[Depends(require_auth)],
    )
    def events_list(
        since_event_id: str | None = Query(default=None),
        domain: list[str] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> EventListResponse:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"event store unavailable: {exc}",
            ) from exc

        domain_filter = _normalize_domain_param(domain)

        try:
            events = list_world_events(
                store,
                since_event_id=since_event_id,
                domain_filter=domain_filter,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("event store list_events failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"event listing failed: {exc}",
            ) from exc

        next_event_id = events[-1].id if events else since_event_id
        return EventListResponse(events=events, next_event_id=next_event_id)

    @app.post(
        "/events",
        response_model=EventRecord,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_auth)],
    )
    def events_append(payload: EventCreateRequest) -> EventRecord:
        try:
            store = get_event_store()
        except EventStoreUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"event store unavailable: {exc}",
            ) from exc

        try:
            return append_world_event(
                store,
                event_type=payload.type,
                domain=payload.domain,
                payload=payload.payload,
                created_at=payload.created_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("event store append_event failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"event append failed: {exc}",
            ) from exc

    return app


def _normalize_domain_param(domain: list[str] | None) -> str | list[str] | None:
    if not domain:
        return None
    if len(domain) == 1:
        return domain[0]
    return domain


def _run_health_check(check: HealthChecker) -> bool:
    try:
        return bool(check())
    except Exception:  # noqa: BLE001
        return False


def _default_narrative_engine_importable() -> bool:
    try:
        module = importlib.import_module("cypherclaw.narrative.engine")
        getattr(module, "NarrativeEngine")
    except Exception:  # noqa: BLE001
        return False
    return True


def _default_ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(  # noqa: S310
            "http://localhost:11434/api/ps",
            timeout=1,
        ) as response:
            response.read(1)
    except OSError:
        return False
    return True
