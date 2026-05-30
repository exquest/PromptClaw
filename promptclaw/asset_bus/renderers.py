"""Renderer registry for the Deniable Asset Bus producer.

The :class:`RendererMatrix` in :mod:`promptclaw.asset_bus.capabilities`
maps ``asset_type`` to a renderer *name*. The registry here maps that
name to the concrete callable that does the work. Routing composes the
two: matrix gives the name, registry gives the handler.

Renderers register at startup (or via tests' fixtures) with
:meth:`RendererRegistry.register`. Looking up an unregistered name
raises :class:`UnknownRendererError` so a misconfigured matrix surfaces
as a typed failure rather than a ``KeyError`` deep in dispatch.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

__all__ = [
    "Renderer",
    "RendererRegistry",
    "UnknownRendererError",
]


Renderer = Callable[..., Any]


class UnknownRendererError(KeyError):
    """Raised when a renderer name is looked up but not registered.

    Subclasses :class:`KeyError` so callers that already handle
    ``KeyError`` from mapping-style access keep working, while code that
    wants a typed catch can target this class directly.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"no renderer registered under name {self.name!r}"


class RendererRegistry:
    """In-memory lookup of renderer name → callable handler."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, Renderer] = {}

    def register(
        self, name: str, handler: Renderer, *, replace: bool = False
    ) -> None:
        """Register ``handler`` under ``name``.

        Re-registering an existing name raises :class:`ValueError` unless
        ``replace=True``. Empty or non-string names are rejected so a
        bad config can't insert a never-callable entry.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"renderer name must be a non-empty string, got {name!r}"
            )
        if not callable(handler):
            raise TypeError(
                f"renderer handler for {name!r} must be callable, got {handler!r}"
            )
        if name in self._handlers and not replace:
            raise ValueError(
                f"renderer {name!r} already registered; pass replace=True to override"
            )
        self._handlers[name] = handler

    def get(self, name: str) -> Renderer:
        """Return the callable registered under ``name``.

        Raises :class:`UnknownRendererError` if no handler is registered.
        """
        try:
            return self._handlers[name]
        except KeyError:
            raise UnknownRendererError(name) from None

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)

    def names(self) -> list[str]:
        """Return the list of registered renderer names, insertion-ordered."""
        return list(self._handlers)
