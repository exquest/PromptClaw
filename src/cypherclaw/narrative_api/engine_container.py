"""Wire the narrative_api routes to the live cypherclaw narrative engine.

The wrappers in ``events.py``, ``entities.py``, ``memory.py`` call into a
"store" object using duck-typed method names (``list_events``, ``create_entity``,
``semantic_search``, ...). The real engine — ``cypherclaw.narrative.world.WorldState``,
``cypherclaw.narrative.engine.NarrativeEngine``, ``cypherclaw.narrative.memory.NarrativeMemory``
— exposes a different but equivalent API. This module provides:

- A process-global ``WorldState`` singleton so every route shares the same
  database connection (sqlite is happiest with one connection per process).
- ``WorldStateAdapter`` translating the duck-typed names the wrappers look for
  to the actual ``WorldState`` methods, plus tacking on the ``domain`` field
  that the wrappers expect (stored inside the existing ``data`` JSON blob —
  the migration adds a top-level column too, but the JSON copy keeps things
  resilient if the migration hasn't run yet).
- Lazy builders the existing ``build_default_*`` functions can delegate to.

The PRD's design intent (line 111): each endpoint is *parse → call existing
engine method → serialize → return*. This module is the "call existing engine
method" layer.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


_world: Any | None = None
_engine: Any | None = None
_memory: Any | None = None


def _resolve_db_path() -> str | None:
    """Honor ``CYPHERCLAW_NARRATIVE_DB_PATH`` if set; else use engine default."""
    return os.environ.get("CYPHERCLAW_NARRATIVE_DB_PATH") or None


def get_world():
    """Return the process-singleton ``WorldState``, building + initializing on first call."""
    global _world
    if _world is not None:
        return _world
    from cypherclaw.narrative.world import WorldState

    ws = WorldState(db_path=_resolve_db_path())
    ws.initialize()
    _world = ws
    return _world


def get_engine():
    """Return the process-singleton ``NarrativeEngine``, sharing the world's db_path."""
    global _engine
    if _engine is not None:
        return _engine
    from cypherclaw.narrative.engine import NarrativeEngine

    eng = NarrativeEngine(db_path=_resolve_db_path())
    try:
        eng.initialize()
    except Exception:
        # Some deployments do lazy initialization inside next_beat() — don't
        # block service start if initialize() throws (e.g. no ollama).
        logger.warning("NarrativeEngine.initialize() failed", exc_info=True)
    _engine = eng
    return _engine


def get_memory():
    """Return the process-singleton ``NarrativeMemoryAdapter``.

    The underlying ``NarrativeMemory`` instance shares the world singleton
    (one SQLite connection across all routes). The adapter wraps it so the
    duck-typed wrapper code finds ``search``/``semantic_search`` — the engine
    exposes ``retrieve_similar_beats`` instead.
    """
    global _memory
    if _memory is not None:
        return _memory
    from cypherclaw.narrative.memory import NarrativeMemory

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    embed_model = os.environ.get("NARRATIVE_EMBED_MODEL", "nomic-embed-text:latest")
    raw = NarrativeMemory(
        world=get_world(),
        ollama_url=ollama_url,
        embed_model=embed_model,
    )
    _memory = NarrativeMemoryAdapter(raw)
    return _memory


class NarrativeMemoryAdapter:
    """Expose ``retrieve_similar_beats`` under the names the wrapper looks for.

    Wrapper duck-types over (``semantic_search``, ``search``, ``query``); the
    real engine method is ``retrieve_similar_beats(query, top_k)``. We also
    surface ``retrieve_relevant_context`` as an alternate path callers can opt
    into via a ``mode`` kwarg.
    """

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def semantic_search(
        self,
        query: str,
        k: int = 5,
        domain_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.search(query=query, k=k, domain_filter=domain_filter)

    def search(
        self,
        query: str,
        k: int = 5,
        domain_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        results = self.memory.retrieve_similar_beats(query=query, top_k=k)
        if domain_filter:
            results = [
                r
                for r in results
                if _result_domain(r) == domain_filter or _result_domain(r) == "shared"
            ]
        return results

    # Forward any other attribute access in case a caller needs the raw engine method.
    def __getattr__(self, name: str) -> Any:
        return getattr(self.memory, name)


def _result_domain(result: dict[str, Any]) -> str:
    """Best-effort domain extraction from a memory hit."""
    if isinstance(result, dict):
        if result.get("domain"):
            return result["domain"]
        meta = result.get("metadata") or result.get("data") or {}
        if isinstance(meta, dict) and meta.get("domain"):
            return meta["domain"]
    return "shared"


# ---------------------------------------------------------------------------
# WorldState adapter — duck-typed names the wrapper looks for.
# ---------------------------------------------------------------------------


class WorldStateAdapter:
    """Expose ``WorldState`` methods under the names the wrapper duck-types.

    Mapping:
        list_events     -> WorldState.get_recent_events (+ python-side filtering for since_event_id / domain)
        append_event    -> WorldState.append_event (+ stash domain in data["domain"])
        get_entity      -> WorldState.get_entity
        list_entities   -> WorldState.get_entities_by_type (or all-types fallback)
        create_entity   -> WorldState.upsert_entity (with generated id)
        update_entity   -> WorldState.upsert_entity (existing id)
    """

    def __init__(self, world: Any) -> None:
        self.world = world

    # ----- Events -----

    def list_events(
        self,
        since_event_id: str | None = None,
        domain_filter: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        # Over-fetch so that since_event_id + domain filtering still has limit candidates.
        fetch = max(limit * 4, limit + 50)
        events = self.world.get_recent_events(limit=fetch)
        # WorldState returns DESC by created_at; keep that order.
        if since_event_id:
            # Trim everything older than (and including) since_event_id.
            cutoff_idx = next(
                (i for i, e in enumerate(events) if e.get("id") == since_event_id),
                None,
            )
            if cutoff_idx is not None:
                events = events[:cutoff_idx]
        if domain_filter:
            events = [
                e
                for e in events
                if _event_domain(e) == domain_filter or _event_domain(e) == "shared"
            ]
        return events[:limit]

    def append_event(
        self,
        event_type: str,
        description: str = "",
        character_ids: list[str] | None = None,
        data: dict | None = None,
        domain: str = "shared",
        **_: Any,
    ) -> dict[str, Any]:
        # The HTTP wrapper sends ``payload`` (mapped to ``data`` here) and
        # ``domain`` but no top-level ``description`` field. Look inside the
        # payload for one — Deniable raids stash narrative copy there — and
        # fall back to the event_type slug as a last resort.
        payload = dict(data or {})
        payload.setdefault("domain", domain)
        if not description:
            description = (
                payload.get("description")
                or payload.get("text")
                or payload.get("summary")
                or event_type
            )
        new_id = self.world.append_event(
            event_type=event_type,
            description=description,
            character_ids=character_ids,
            data=payload,
        )
        return {
            "id": new_id,
            "event_type": event_type,
            "type": event_type,  # wrapper expects "type"
            "description": description,
            "character_ids": character_ids or [],
            "data": payload,
            "payload": payload,  # wrapper expects "payload"
            "domain": payload["domain"],
        }

    # ----- Entities -----

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        record = self.world.get_entity(entity_id)
        if record is None:
            return None
        return _entity_with_domain(record)

    def list_entities(
        self,
        entity_type: str | None = None,
        domain_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if entity_type:
            records = self.world.get_entities_by_type(entity_type)
        else:
            # No "list all entities" method on WorldState. Fall back to a
            # union over the canonical entity types we know about.
            records = []
            for t in ("character", "location", "item", "faction", "concept", "squad", "fighter"):
                try:
                    records.extend(self.world.get_entities_by_type(t))
                except Exception:
                    continue
        records = [_entity_with_domain(r) for r in records]
        if domain_filter:
            records = [
                r
                for r in records
                if r.get("domain") == domain_filter or r.get("domain") == "shared"
            ]
        return records[offset : offset + limit]

    def create_entity(
        self,
        entity_id: str | None = None,
        entity_type: str = "concept",
        name: str = "",
        domain: str = "shared",
        properties: dict | None = None,
    ) -> dict[str, Any]:
        import uuid

        new_id = entity_id or str(uuid.uuid4())
        payload = dict(properties or {})
        payload["domain"] = domain
        self.world.upsert_entity(
            entity_id=new_id,
            entity_type=entity_type,
            name=name,
            data=payload,
        )
        return {
            "id": new_id,
            "entity_type": entity_type,
            "name": name,
            "domain": domain,
            "data": payload,
        }

    def update_entity(
        self,
        entity_id: str,
        properties: dict | None = None,
    ) -> dict[str, Any] | None:
        existing = self.world.get_entity(entity_id)
        if existing is None:
            return None
        merged_data = dict(existing.get("data") or {})
        merged_data.update(properties or {})
        self.world.upsert_entity(
            entity_id=entity_id,
            entity_type=existing["entity_type"],
            name=existing["name"],
            data=merged_data,
        )
        existing["data"] = merged_data
        return _entity_with_domain(existing)


def _event_domain(event: dict[str, Any]) -> str:
    """Pull domain from an event row. Prefer top-level column (post-migration);
    fall back to ``data["domain"]`` (pre-migration); default to ``shared``."""
    if "domain" in event and event["domain"]:
        return event["domain"]
    data = event.get("data")
    if isinstance(data, dict):
        d = data.get("domain")
        if d:
            return d
    return "shared"


def _entity_with_domain(entity: dict[str, Any]) -> dict[str, Any]:
    """Surface ``data["domain"]`` (or top-level column) onto the returned dict."""
    out = dict(entity)
    if "domain" not in out or not out["domain"]:
        data = out.get("data")
        if isinstance(data, dict) and data.get("domain"):
            out["domain"] = data["domain"]
        else:
            out["domain"] = "shared"
    return out


def get_world_adapter() -> WorldStateAdapter:
    """Return a fresh ``WorldStateAdapter`` over the singleton world."""
    return WorldStateAdapter(get_world())
