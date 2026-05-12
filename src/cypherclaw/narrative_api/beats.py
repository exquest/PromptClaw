"""NarrativeEngine beat invocation and StoryBeat serialization."""
from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from .schemas import DomainFilter


class NarrativeEngineUnavailableError(RuntimeError):
    """Raised when the deploy-side NarrativeEngine implementation is absent."""


def build_default_narrative_engine() -> Any:
    """Build the deploy-side ``NarrativeEngine`` lazily.

    Uses the ``engine_container`` singleton so the engine shares its db_path
    with the world and memory instances — one SQLite connection across all
    routes.
    """

    try:
        from .engine_container import get_engine

        return get_engine()
    except Exception as exc:  # noqa: BLE001
        raise NarrativeEngineUnavailableError(
            f"cypherclaw NarrativeEngine unavailable: {exc}"
        ) from exc


def generate_next_beat(
    engine: Any,
    *,
    cycle_number: int,
    domain_filter: DomainFilter,
    arc_position_target: float | None,
    force_arc_event: str | None,
) -> dict[str, Any]:
    """Call ``engine.next_beat`` and return a JSON-safe StoryBeat mapping."""

    raw_beat = _call_next_beat(
        engine,
        cycle_number=cycle_number,
        domain_filter=domain_filter,
        arc_position_target=arc_position_target,
        force_arc_event=force_arc_event,
    )
    return serialize_story_beat(raw_beat)


def serialize_story_beat(raw: Any) -> dict[str, Any]:
    """Convert a StoryBeat-like value into JSON-safe dictionaries/lists."""

    data = _story_beat_data(raw)
    jsonable = _to_jsonable(data)
    if isinstance(jsonable, dict):
        return jsonable
    return {"id": str(jsonable)}


def _call_next_beat(
    engine: Any,
    *,
    cycle_number: int,
    domain_filter: DomainFilter,
    arc_position_target: float | None,
    force_arc_event: str | None,
) -> Any:
    method = getattr(engine, "next_beat", None)
    if not callable(method):
        raise AttributeError("NarrativeEngine exposes no next_beat method")
    return _invoke_next_beat_method(
        method,
        cycle_number=cycle_number,
        domain_filter=domain_filter,
        arc_position_target=arc_position_target,
        force_arc_event=force_arc_event,
    )


def _invoke_next_beat_method(
    method: Any,
    *,
    cycle_number: int,
    domain_filter: DomainFilter,
    arc_position_target: float | None,
    force_arc_event: str | None,
) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(
            cycle_number=cycle_number,
            domain_filter=domain_filter,
            arc_position_target=arc_position_target,
            force_arc_event=force_arc_event,
        )

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    kwargs: dict[str, Any] = {}
    if "cycle_number" in params or accepts_kwargs:
        kwargs["cycle_number"] = cycle_number
    elif "cycle" in params:
        kwargs["cycle"] = cycle_number
    elif "cycle_index" in params:
        kwargs["cycle_index"] = cycle_number

    if "domain_filter" in params or accepts_kwargs:
        kwargs["domain_filter"] = domain_filter
    elif "domain" in params:
        kwargs["domain"] = domain_filter

    if arc_position_target is not None:
        if "arc_position_target" in params or accepts_kwargs:
            kwargs["arc_position_target"] = arc_position_target
        elif "target_arc_position" in params:
            kwargs["target_arc_position"] = arc_position_target
        elif "arc_position" in params:
            kwargs["arc_position"] = arc_position_target

    if force_arc_event is not None:
        if "force_arc_event" in params or accepts_kwargs:
            kwargs["force_arc_event"] = force_arc_event
        elif "arc_event" in params:
            kwargs["arc_event"] = force_arc_event
        elif "event_type" in params:
            kwargs["event_type"] = force_arc_event

    return method(**kwargs)


def _story_beat_data(raw: Any) -> Any:
    if isinstance(raw, Mapping):
        return dict(raw)
    if is_dataclass(raw) and not isinstance(raw, type):
        return asdict(raw)

    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except TypeError:
            return model_dump()

    legacy_dict = getattr(raw, "dict", None)
    if callable(legacy_dict):
        return legacy_dict()

    try:
        return dict(vars(raw))
    except TypeError:
        return {"id": str(raw)}


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _to_jsonable(model_dump(mode="json"))
        except TypeError:
            return _to_jsonable(model_dump())

    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_jsonable(item) for item in value]

    try:
        data = vars(value)
    except TypeError:
        return str(value)
    return _to_jsonable(data)
