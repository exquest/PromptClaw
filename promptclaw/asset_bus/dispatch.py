"""Routing dispatch for the Deniable Asset Bus producer.

Composes the renderer matrix (``asset_type`` → renderer name) and the
renderer registry (renderer name → callable) to invoke the right handler
for a request. The two indirections are intentional: the matrix is
declarative config the operator edits; the registry is wired at startup
by code that imports the concrete handlers. Dispatch keeps them honest
by surfacing typed failures when either lookup misses.
"""

from __future__ import annotations

from typing import Any, Mapping

from .capabilities import RendererMatrix
from .renderers import RendererRegistry, UnknownRendererError

__all__ = [
    "UnknownAssetTypeError",
    "UnknownRendererError",
    "dispatch_request",
]


class UnknownAssetTypeError(KeyError):
    """Raised when a request's ``asset_type`` has no entry in the matrix.

    Subclasses :class:`KeyError` so generic mapping-style handlers keep
    working, while callers that want a typed catch can target this
    class directly.
    """

    def __init__(self, asset_type: object) -> None:
        super().__init__(asset_type)
        self.asset_type = asset_type

    def __str__(self) -> str:
        return f"no renderer mapping for asset_type {self.asset_type!r}"


def dispatch_request(
    request: Mapping[str, Any],
    matrix: RendererMatrix,
    registry: RendererRegistry,
) -> Any:
    """Resolve the renderer for ``request`` and invoke it.

    Reads ``asset_type`` from ``request``, consults ``matrix`` for the
    renderer name, resolves the callable via ``registry``, and calls it
    with the request. Raises :class:`UnknownAssetTypeError` if the
    matrix has no entry, or :class:`UnknownRendererError` if the matrix
    names a renderer that nobody registered.
    """
    asset_type = request.get("asset_type")
    try:
        renderer_name = matrix[asset_type]  # type: ignore[index]
    except KeyError:
        raise UnknownAssetTypeError(asset_type) from None
    handler = registry.get(renderer_name)
    return handler(request)
