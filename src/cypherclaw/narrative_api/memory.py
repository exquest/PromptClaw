"""NarrativeMemory invocation and result normalization."""
from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from .schemas import DomainFilter, MemorySearchResult


class MemoryUnavailableError(RuntimeError):
    """Raised when the deploy-side NarrativeMemory implementation is absent."""


def build_default_memory() -> Any:
    """Build the deploy-side ``NarrativeMemory`` instance lazily.

    The engine's ``NarrativeMemory.__init__`` requires a ``world`` arg (the
    ``WorldState`` it queries through). The container module owns the
    process-singleton world; we hand the same instance to memory so they
    share one SQLite connection.
    """

    try:
        from .engine_container import get_memory

        return get_memory()
    except Exception as exc:  # noqa: BLE001
        raise MemoryUnavailableError(
            f"cypherclaw NarrativeMemory unavailable: {exc}"
        ) from exc


def search_narrative_memory(
    memory: Any,
    *,
    query: str,
    k: int,
    domain_filter: DomainFilter = None,
) -> list[MemorySearchResult]:
    """Search ``memory`` and return ranked, domain-filtered results."""

    raw_results = _call_search(memory, query=query, k=k, domain_filter=domain_filter)
    normalized = [
        result
        for result in (_normalize_result(item) for item in raw_results)
        if _domain_allowed(result.domain, domain_filter)
    ]
    normalized.sort(key=lambda result: result.similarity, reverse=True)
    return normalized[:k]


def _call_search(
    memory: Any,
    *,
    query: str,
    k: int,
    domain_filter: DomainFilter,
) -> Iterable[Any]:
    method = _search_method(memory)
    return _invoke_search_method(
        method,
        query=query,
        k=k,
        domain_filter=domain_filter,
    )


def _search_method(memory: Any) -> Any:
    for name in ("semantic_search", "search", "query"):
        method = getattr(memory, name, None)
        if callable(method):
            return method
    raise AttributeError(
        "NarrativeMemory exposes no semantic_search, search, or query method"
    )


def _invoke_search_method(
    method: Any,
    *,
    query: str,
    k: int,
    domain_filter: DomainFilter,
) -> Iterable[Any]:
    kwargs: dict[str, Any] = {}
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(query, k, domain_filter=domain_filter)

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )

    if "domain_filter" in params or accepts_kwargs:
        kwargs["domain_filter"] = domain_filter
    elif "domain" in params:
        kwargs["domain"] = domain_filter

    for limit_name in ("k", "top_k", "limit", "n"):
        if limit_name in params or accepts_kwargs:
            kwargs[limit_name] = k
            return method(query, **kwargs)

    return method(query, k, **kwargs)


def _normalize_result(raw: Any) -> MemorySearchResult:
    if isinstance(raw, tuple):
        return _normalize_tuple(raw)
    if isinstance(raw, Mapping):
        return _normalize_mapping(raw)
    if isinstance(raw, str):
        return MemorySearchResult(text=raw, similarity=0.0)

    data = _object_data(raw)
    if data:
        return _normalize_mapping(data)

    return MemorySearchResult(text=str(raw), similarity=0.0)


def _normalize_tuple(raw: tuple[Any, ...]) -> MemorySearchResult:
    text = str(raw[0]) if raw else ""
    similarity = _coerce_float(raw[1]) if len(raw) > 1 else 0.0
    metadata = _metadata_from(raw[2]) if len(raw) > 2 else {}
    return MemorySearchResult(
        id=_coerce_optional_str(metadata.get("id")),
        text=text,
        similarity=similarity,
        domain=_coerce_optional_str(metadata.get("domain")),
        metadata=metadata,
    )


def _normalize_mapping(raw: Mapping[str, Any]) -> MemorySearchResult:
    data = dict(raw)
    metadata = _metadata_from(data.get("metadata"))
    metadata.update(
        {
            key: value
            for key, value in data.items()
            if key
            not in {
                "id",
                "memory_id",
                "event_id",
                "source_id",
                "text",
                "content",
                "summary",
                "body",
                "memory",
                "document",
                "similarity",
                "score",
                "relevance",
                "distance",
                "domain",
                "metadata",
            }
        }
    )

    return MemorySearchResult(
        id=_coerce_optional_str(
            _first_present(data, metadata, ("id", "memory_id", "event_id", "source_id"))
        ),
        text=_coerce_text(
            _first_present(
                data,
                metadata,
                ("text", "content", "summary", "body", "memory", "document"),
            )
        ),
        similarity=_similarity_from(data, metadata),
        domain=_coerce_optional_str(_first_present(data, metadata, ("domain",))),
        metadata=metadata,
    )


def _object_data(raw: Any) -> dict[str, Any]:
    if is_dataclass(raw) and not isinstance(raw, type):
        return asdict(raw)
    try:
        return dict(vars(raw))
    except TypeError:
        return {}


def _metadata_from(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _first_present(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
    keys: tuple[str, ...],
) -> Any:
    for key in keys:
        if key in primary and primary[key] is not None:
            return primary[key]
        if key in secondary and secondary[key] is not None:
            return secondary[key]
    return None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _similarity_from(
    data: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> float:
    value = _first_present(data, metadata, ("similarity", "score", "relevance"))
    if value is not None:
        return _coerce_float(value)
    distance = _first_present(data, metadata, ("distance",))
    if distance is not None:
        return 1.0 - _coerce_float(distance)
    return 0.0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
