"""Narrative event log invocation and result normalization."""
from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from .schemas import DomainFilter, EventRecord


class EventStoreUnavailableError(RuntimeError):
    """Raised when the deploy-side narrative event store is absent."""


def build_default_event_store() -> Any:
    """Build the deploy-side event store lazily.

    Per PRD §3, events live in the world-state SQLite accessed via
    ``WorldState.append_event`` / ``get_recent_events``. We wrap that with
    ``WorldStateAdapter`` so the duck-typed wrapper code finds the method
    names it expects (``list_events``, ``append_event``).
    """

    try:
        from .engine_container import get_world_adapter

        return get_world_adapter()
    except Exception as exc:  # noqa: BLE001
        raise EventStoreUnavailableError(
            f"cypherclaw narrative WorldState unavailable: {exc}"
        ) from exc


def list_world_events(
    store: Any,
    *,
    since_event_id: str | None,
    domain_filter: DomainFilter,
    limit: int,
) -> list[EventRecord]:
    """List events newer than ``since_event_id``, optionally domain-filtered."""

    raw_events = _call_list(
        store,
        since_event_id=since_event_id,
        domain_filter=domain_filter,
        limit=limit,
    )
    normalized = [
        record
        for record in (_normalize_event(item) for item in raw_events)
        if record.id and _domain_allowed(record.domain, domain_filter)
    ]
    if since_event_id is not None:
        normalized = [
            record for record in normalized if record.id != since_event_id
        ]
    return normalized[:limit]


def append_world_event(
    store: Any,
    *,
    event_type: str,
    domain: str,
    payload: Mapping[str, Any],
    created_at: str | None,
) -> EventRecord:
    """Append a world event through the deploy-side event store."""

    raw_event = _call_append(
        store,
        event_type=event_type,
        domain=domain,
        payload=payload,
        created_at=created_at,
    )
    if raw_event is None:
        record = EventRecord(
            id="",
            type=event_type,
            domain=domain,
            payload=dict(payload),
            created_at=created_at,
        )
    else:
        record = _normalize_event(raw_event)
    return _fill_event_defaults(
        record,
        event_type=event_type,
        domain=domain,
        payload=payload,
        created_at=created_at,
    )


def _call_list(
    store: Any,
    *,
    since_event_id: str | None,
    domain_filter: DomainFilter,
    limit: int,
) -> Iterable[Any]:
    method = _list_method(store)
    return _invoke_list_method(
        method,
        since_event_id=since_event_id,
        domain_filter=domain_filter,
        limit=limit,
    )


def _call_append(
    store: Any,
    *,
    event_type: str,
    domain: str,
    payload: Mapping[str, Any],
    created_at: str | None,
) -> Any:
    method = _append_method(store)
    return _invoke_append_method(
        method,
        event_type=event_type,
        domain=domain,
        payload=payload,
        created_at=created_at,
    )


def _list_method(store: Any) -> Any:
    for name in ("list_events", "events_since", "get_events", "events"):
        method = getattr(store, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "event store exposes no list_events, events_since, get_events, or events method"
    )


def _append_method(store: Any) -> Any:
    for name in ("append_event", "record_event", "add_event", "create_event", "append"):
        method = getattr(store, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "event store exposes no append_event, record_event, add_event, create_event, or append method"
    )


def _invoke_list_method(
    method: Any,
    *,
    since_event_id: str | None,
    domain_filter: DomainFilter,
    limit: int,
) -> Iterable[Any]:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(since_event_id, domain_filter, limit)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    kwargs: dict[str, Any] = {}
    if "since_event_id" in params or accepts_kwargs:
        kwargs["since_event_id"] = since_event_id
    elif "since" in params:
        kwargs["since"] = since_event_id
    elif "after" in params:
        kwargs["after"] = since_event_id

    if "domain_filter" in params or accepts_kwargs:
        kwargs["domain_filter"] = domain_filter
    elif "domain" in params:
        kwargs["domain"] = domain_filter

    for limit_name in ("limit", "k", "top_k", "n", "max_events"):
        if limit_name in params or accepts_kwargs:
            kwargs[limit_name] = limit
            break

    return method(**kwargs)


def _invoke_append_method(
    method: Any,
    *,
    event_type: str,
    domain: str,
    payload: Mapping[str, Any],
    created_at: str | None,
) -> Any:
    event_payload = dict(payload)
    event_record: dict[str, Any] = {
        "type": event_type,
        "domain": domain,
        "payload": event_payload,
    }
    if created_at is not None:
        event_record["created_at"] = created_at

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(event_type, domain, event_payload, created_at)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    for event_arg_name in ("event", "record", "entry"):
        if event_arg_name in params and not accepts_kwargs:
            return method(event_record)

    kwargs: dict[str, Any] = {}
    for type_name in ("event_type", "type", "kind"):
        if type_name in params or accepts_kwargs:
            kwargs[type_name] = event_type
            break

    if "domain" in params or accepts_kwargs:
        kwargs["domain"] = domain

    for payload_name in ("payload", "data", "body"):
        if payload_name in params or accepts_kwargs:
            kwargs[payload_name] = event_payload
            break

    if "created_at" in params or accepts_kwargs:
        kwargs["created_at"] = created_at
    elif "timestamp" in params:
        kwargs["timestamp"] = created_at

    if kwargs:
        return method(**kwargs)
    return method(event_type, domain, event_payload, created_at)


def _normalize_event(raw: Any) -> EventRecord:
    if isinstance(raw, Mapping):
        return _normalize_mapping(raw)

    data = _object_data(raw)
    if data:
        return _normalize_mapping(data)

    return EventRecord(id=str(raw))


def _fill_event_defaults(
    record: EventRecord,
    *,
    event_type: str,
    domain: str,
    payload: Mapping[str, Any],
    created_at: str | None,
) -> EventRecord:
    return EventRecord(
        id=record.id,
        type=record.type or event_type,
        domain=record.domain or domain,
        payload=record.payload or dict(payload),
        created_at=record.created_at or created_at,
    )


def _normalize_mapping(raw: Mapping[str, Any]) -> EventRecord:
    data = dict(raw)
    payload = _payload_from(data.get("payload"))
    consumed = {
        "id",
        "event_id",
        "type",
        "event_type",
        "kind",
        "domain",
        "payload",
        "data",
        "body",
        "created_at",
        "timestamp",
        "ts",
    }
    for key, value in data.items():
        if key in consumed:
            continue
        payload.setdefault(key, value)

    raw_payload = data.get("payload")
    if not isinstance(raw_payload, Mapping):
        for source_key in ("data", "body"):
            source = data.get(source_key)
            if isinstance(source, Mapping):
                for key, value in source.items():
                    payload.setdefault(key, value)

    event_id = _first_present(data, ("id", "event_id"))
    return EventRecord(
        id=str(event_id) if event_id is not None else "",
        type=_coerce_optional_str(_first_present(data, ("type", "event_type", "kind"))),
        domain=_coerce_optional_str(data.get("domain")),
        payload=payload,
        created_at=_coerce_optional_str(
            _first_present(data, ("created_at", "timestamp", "ts"))
        ),
    )


def _payload_from(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _object_data(raw: Any) -> dict[str, Any]:
    if is_dataclass(raw) and not isinstance(raw, type):
        return asdict(raw)
    try:
        return dict(vars(raw))
    except TypeError:
        return {}


def _first_present(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _domain_allowed(domain: str | None, domain_filter: DomainFilter) -> bool:
    if domain_filter is None:
        return True
    if domain is None:
        return True
    if isinstance(domain_filter, str):
        allowed = {domain_filter}
    else:
        allowed = set(domain_filter)
    return domain in allowed
