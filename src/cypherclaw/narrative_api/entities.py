"""Narrative entity retrieval and normalization."""
from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from .schemas import DomainFilter, EntityRecord, StateMutation


_CONTROL_FIELDS = {
    "id",
    "entity_id",
    "type",
    "entity_type",
    "kind",
    "name",
    "domain",
}


def get_world_entity(store: Any, entity_id: str) -> EntityRecord | None:
    """Fetch a single entity by ID; return ``None`` when the store has no match."""

    method = _get_entity_method(store)
    if method is None:
        for record in (
            _normalize_entity(item) for item in _call_list_entities(
                store,
                domain_filter=None,
                entity_type=None,
                limit=10_000,
                offset=0,
            )
        ):
            if record.id == entity_id:
                return record
        return None

    raw = _invoke_get_entity_method(method, entity_id)
    if raw is None:
        return None
    record = _normalize_entity(raw)
    return record if record.id else None


def _get_entity_method(store: Any) -> Any:
    for name in ("get_entity", "fetch_entity", "find_entity", "entity"):
        method = getattr(store, name, None)
        if callable(method):
            return method
    return None


def _invoke_get_entity_method(method: Any, entity_id: str) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(entity_id)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    for name in ("entity_id", "id", "identifier", "key"):
        if name in params or accepts_kwargs:
            return method(**{name: entity_id})

    return method(entity_id)


def create_world_entity(
    store: Any,
    *,
    entity_type: str,
    name: str,
    domain: str,
    properties: Mapping[str, Any],
) -> EntityRecord:
    """Create a world entity through the deploy-side store and return it normalized."""

    raw = _call_create_entity(
        store,
        entity_type=entity_type,
        name=name,
        domain=domain,
        properties=properties,
    )
    if raw is None:
        record = EntityRecord(
            id="",
            type=entity_type,
            name=name,
            domain=domain,
            properties=dict(properties),
        )
    else:
        record = _normalize_entity(raw)
    return EntityRecord(
        id=record.id,
        type=record.type or entity_type,
        name=record.name or name,
        domain=record.domain or domain,
        properties=record.properties or dict(properties),
    )


def apply_world_entity_mutations(
    store: Any,
    *,
    entity_id: str,
    mutations: Iterable[StateMutation],
) -> EntityRecord | None:
    """Apply state mutations to an entity and persist the updated record."""

    current = get_world_entity(store, entity_id)
    if current is None:
        return None

    properties = deepcopy(current.properties)
    for mutation in mutations:
        _apply_state_mutation(properties, entity_id=entity_id, mutation=mutation)

    updated = EntityRecord(
        id=current.id,
        type=current.type,
        name=current.name,
        domain=current.domain,
        properties=properties,
    )
    raw = _call_update_entity(store, updated)
    if raw is None:
        return updated

    persisted = _normalize_entity(raw)
    return EntityRecord(
        id=persisted.id or updated.id,
        type=persisted.type or updated.type,
        name=persisted.name or updated.name,
        domain=persisted.domain or updated.domain,
        properties=persisted.properties or updated.properties,
    )


def _apply_state_mutation(
    properties: dict[str, Any],
    *,
    entity_id: str,
    mutation: StateMutation,
) -> None:
    if mutation.target_entity is not None and mutation.target_entity != entity_id:
        raise ValueError(
            f"mutation target_entity {mutation.target_entity!r} does not match "
            f"path entity_id {entity_id!r}"
        )

    path = _property_path(mutation.field)
    if mutation.operation == "set":
        _set_path(properties, path, mutation.value)
    elif mutation.operation == "increment":
        _increment_path(properties, path, mutation.value)
    elif mutation.operation == "decrement":
        _decrement_path(properties, path, mutation.value)
    elif mutation.operation == "append":
        _append_path(properties, path, mutation.value)
    elif mutation.operation == "remove":
        _remove_path(properties, path, mutation.value)
    else:
        raise ValueError(f"unsupported mutation operation: {mutation.operation}")


def _property_path(field: str) -> tuple[str, ...]:
    parts = tuple(field.split("."))
    if any(part == "" for part in parts):
        raise ValueError(f"invalid entity property path: {field!r}")
    if parts[0] == "properties":
        parts = parts[1:]
    elif parts[0] in _CONTROL_FIELDS:
        raise ValueError(f"cannot mutate top-level entity field: {parts[0]}")
    if not parts:
        raise ValueError("mutation field must address a property")
    return parts


def _set_path(
    properties: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    parent = _created_path_parent(properties, path)
    parent[path[-1]] = deepcopy(value)


def _increment_path(
    properties: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    amount = _numeric_value(value, "increment value")
    parent = _created_path_parent(properties, path)
    current = parent.get(path[-1], 0)
    parent[path[-1]] = _numeric_value(current, "existing value") + amount


def _decrement_path(
    properties: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    amount = _numeric_value(value, "decrement value")
    parent = _created_path_parent(properties, path)
    current = parent.get(path[-1], 0)
    parent[path[-1]] = _numeric_value(current, "existing value") - amount


def _append_path(
    properties: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    parent = _created_path_parent(properties, path)
    existing = parent.setdefault(path[-1], [])
    if not isinstance(existing, list):
        raise ValueError(f"cannot append to non-list property: {'.'.join(path)}")
    existing.append(deepcopy(value))


def _remove_path(
    properties: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    parent = _path_parent(properties, path, create=False)
    if parent is None or path[-1] not in parent:
        return
    existing = parent[path[-1]]
    if isinstance(existing, list):
        parent[path[-1]] = [item for item in existing if item != value]
        return
    del parent[path[-1]]


def _created_path_parent(
    properties: dict[str, Any],
    path: tuple[str, ...],
) -> dict[str, Any]:
    parent = _path_parent(properties, path, create=True)
    if parent is None:
        raise AssertionError("create=True path parent unexpectedly returned None")
    return parent


def _path_parent(
    properties: dict[str, Any],
    path: tuple[str, ...],
    *,
    create: bool,
) -> dict[str, Any] | None:
    current = properties
    for part in path[:-1]:
        child = current.get(part)
        if child is None:
            if not create:
                return None
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError(
                f"cannot traverse non-object property path segment: {part}"
            )
        current = child
    return current


def _numeric_value(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    return value


def _call_update_entity(store: Any, entity: EntityRecord) -> Any:
    method = _update_entity_method(store)
    return _invoke_update_entity_method(method, entity)


def _update_entity_method(store: Any) -> Any:
    for name in (
        "update_entity",
        "patch_entity",
        "save_entity",
        "upsert_entity",
        "record_entity",
    ):
        method = getattr(store, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "world store exposes no update_entity, patch_entity, save_entity, "
        "upsert_entity, or record_entity method"
    )


def _invoke_update_entity_method(method: Any, entity: EntityRecord) -> Any:
    record = _entity_record_mapping(entity)

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(entity.id, record)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    kwargs: dict[str, Any] = {}
    for id_name in ("entity_id", "id", "identifier", "key"):
        if id_name in params or accepts_kwargs:
            kwargs[id_name] = entity.id
            break

    for record_arg_name in ("entity", "record", "entry"):
        if record_arg_name in params or accepts_kwargs:
            kwargs[record_arg_name] = record
            break

    if "name" in params or accepts_kwargs:
        kwargs["name"] = entity.name

    if "domain" in params or accepts_kwargs:
        kwargs["domain"] = entity.domain

    for type_name in ("type", "entity_type", "kind"):
        if type_name in params or accepts_kwargs:
            kwargs[type_name] = entity.type
            break

    for props_name in ("properties", "attributes", "data"):
        if props_name in params or accepts_kwargs:
            kwargs[props_name] = dict(entity.properties)
            break

    if kwargs:
        return method(**kwargs)

    positional = [
        param
        for param in params.values()
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return method(entity.id, record)
    return method(record)


def _entity_record_mapping(entity: EntityRecord) -> dict[str, Any]:
    return {
        "id": entity.id,
        "type": entity.type,
        "name": entity.name,
        "domain": entity.domain,
        "properties": dict(entity.properties),
    }


def _call_create_entity(
    store: Any,
    *,
    entity_type: str,
    name: str,
    domain: str,
    properties: Mapping[str, Any],
) -> Any:
    method = _create_entity_method(store)
    return _invoke_create_entity_method(
        method,
        entity_type=entity_type,
        name=name,
        domain=domain,
        properties=properties,
    )


def _create_entity_method(store: Any) -> Any:
    for name in (
        "create_entity",
        "add_entity",
        "record_entity",
        "upsert_entity",
        "save_entity",
    ):
        method = getattr(store, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "world store exposes no create_entity, add_entity, record_entity, "
        "upsert_entity, or save_entity method"
    )


def _invoke_create_entity_method(
    method: Any,
    *,
    entity_type: str,
    name: str,
    domain: str,
    properties: Mapping[str, Any],
) -> Any:
    record_props = dict(properties)
    record: dict[str, Any] = {
        "type": entity_type,
        "name": name,
        "domain": domain,
        "properties": record_props,
    }

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(record)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    for record_arg_name in ("entity", "record", "entry"):
        if record_arg_name in params and not accepts_kwargs:
            return method(record)

    kwargs: dict[str, Any] = {}
    for type_name in ("type", "entity_type", "kind"):
        if type_name in params or accepts_kwargs:
            kwargs[type_name] = entity_type
            break

    if "name" in params or accepts_kwargs:
        kwargs["name"] = name

    if "domain" in params or accepts_kwargs:
        kwargs["domain"] = domain

    for props_name in ("properties", "attributes", "data"):
        if props_name in params or accepts_kwargs:
            kwargs[props_name] = record_props
            break

    if kwargs:
        return method(**kwargs)
    return method(record)


def list_world_entities(
    store: Any,
    *,
    domain_filter: DomainFilter,
    entity_type: str | None,
    limit: int,
    offset: int,
) -> list[EntityRecord]:
    """List world entities, optionally domain and type filtered."""

    raw_entities = _call_list_entities(
        store,
        domain_filter=domain_filter,
        entity_type=entity_type,
        limit=offset + (limit * 5),
        offset=0,
    )
    
    normalized = [
        record
        for record in (_normalize_entity(item) for item in raw_entities)
        if record.id and _domain_allowed(record.domain, domain_filter)
    ]
    
    if entity_type is not None:
        normalized = [r for r in normalized if r.type == entity_type]
        
    return normalized[offset : offset + limit]


def _call_list_entities(
    store: Any,
    *,
    domain_filter: DomainFilter,
    entity_type: str | None,
    limit: int,
    offset: int,
) -> Iterable[Any]:
    method = _list_entities_method(store)
    return _invoke_list_entities_method(
        method,
        domain_filter=domain_filter,
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )


def _list_entities_method(store: Any) -> Any:
    for name in ("list_entities", "get_entities", "entities"):
        method = getattr(store, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "event store exposes no list_entities, get_entities, or entities method"
    )


def _invoke_list_entities_method(
    method: Any,
    *,
    domain_filter: DomainFilter,
    entity_type: str | None,
    limit: int,
    offset: int,
) -> Iterable[Any]:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(domain_filter, entity_type, limit, offset)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    kwargs: dict[str, Any] = {}
    
    if "domain_filter" in params or accepts_kwargs:
        kwargs["domain_filter"] = domain_filter
    elif "domain" in params:
        kwargs["domain"] = domain_filter

    if "entity_type" in params or accepts_kwargs:
        kwargs["entity_type"] = entity_type
    elif "type" in params:
        kwargs["type"] = entity_type

    if "limit" in params or accepts_kwargs:
        kwargs["limit"] = limit

    if "offset" in params or accepts_kwargs:
        kwargs["offset"] = offset

    return method(**kwargs)


def _normalize_entity(raw: Any) -> EntityRecord:
    if isinstance(raw, Mapping):
        return _normalize_mapping(raw)

    data = _object_data(raw)
    if data:
        return _normalize_mapping(data)

    return EntityRecord(id=str(raw))


def _normalize_mapping(raw: Mapping[str, Any]) -> EntityRecord:
    data = dict(raw)
    properties = _payload_from(data.get("properties"))
    consumed = {
        "id",
        "entity_id",
        "type",
        "entity_type",
        "kind",
        "name",
        "domain",
        "properties",
        "data",
        "attributes",
    }
    for key, value in data.items():
        if key in consumed:
            continue
        properties.setdefault(key, value)

    raw_props = data.get("properties")
    if not isinstance(raw_props, Mapping):
        for source_key in ("data", "attributes"):
            source = data.get(source_key)
            if isinstance(source, Mapping):
                for key, value in source.items():
                    properties.setdefault(key, value)

    entity_id = _first_present(data, ("id", "entity_id"))
    return EntityRecord(
        id=str(entity_id) if entity_id is not None else "",
        type=_coerce_optional_str(_first_present(data, ("type", "entity_type", "kind"))),
        name=_coerce_optional_str(data.get("name")),
        domain=_coerce_optional_str(data.get("domain")),
        properties=properties,
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
