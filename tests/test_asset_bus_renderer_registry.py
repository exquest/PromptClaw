"""Tests for the renderer registry (T-012b).

The registry maps a renderer *name* (the value the matrix returns) to
the concrete callable that fulfills a request. Routing composes the
matrix and the registry; if the matrix names a renderer that nobody
registered, lookup must surface a typed error rather than a bare
``KeyError`` so the failure is unambiguous in dispatch.
"""

from __future__ import annotations

import pytest

from promptclaw.asset_bus import (
    RendererRegistry,
    UnknownRendererError,
)


def _image_renderer(*args: object, **kwargs: object) -> str:
    return "image-bytes"


def _music_renderer(*args: object, **kwargs: object) -> str:
    return "music-bytes"


def test_register_and_lookup_hit() -> None:
    registry = RendererRegistry()
    registry.register("sd-image-renderer", _image_renderer)
    assert registry.get("sd-image-renderer") is _image_renderer
    assert registry.get("sd-image-renderer")() == "image-bytes"


def test_lookup_miss_raises_typed_error() -> None:
    registry = RendererRegistry()
    with pytest.raises(UnknownRendererError) as excinfo:
        registry.get("no-such-renderer")
    assert excinfo.value.name == "no-such-renderer"
    assert "no-such-renderer" in str(excinfo.value)


def test_unknown_renderer_error_is_a_key_error() -> None:
    # Subclassing KeyError lets generic mapping-style handlers keep working.
    registry = RendererRegistry()
    with pytest.raises(KeyError):
        registry.get("missing")


def test_register_multiple_renderers_then_iterate() -> None:
    registry = RendererRegistry()
    registry.register("sd-image-renderer", _image_renderer)
    registry.register("music-renderer", _music_renderer)
    assert "sd-image-renderer" in registry
    assert "music-renderer" in registry
    assert "voiceover-renderer" not in registry
    assert len(registry) == 2
    assert set(iter(registry)) == {"sd-image-renderer", "music-renderer"}
    assert registry.names() == ["sd-image-renderer", "music-renderer"]


def test_register_duplicate_rejected_by_default() -> None:
    registry = RendererRegistry()
    registry.register("r", _image_renderer)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("r", _music_renderer)
    # Original handler still wins.
    assert registry.get("r") is _image_renderer


def test_register_replace_overrides_existing() -> None:
    registry = RendererRegistry()
    registry.register("r", _image_renderer)
    registry.register("r", _music_renderer, replace=True)
    assert registry.get("r") is _music_renderer


def test_register_empty_name_rejected() -> None:
    registry = RendererRegistry()
    with pytest.raises(ValueError, match="non-empty"):
        registry.register("", _image_renderer)


def test_register_whitespace_name_rejected() -> None:
    registry = RendererRegistry()
    with pytest.raises(ValueError, match="non-empty"):
        registry.register("   ", _image_renderer)


def test_register_non_callable_rejected() -> None:
    registry = RendererRegistry()
    with pytest.raises(TypeError, match="callable"):
        registry.register("r", "not a function")  # type: ignore[arg-type]


def test_registries_are_independent() -> None:
    a = RendererRegistry()
    b = RendererRegistry()
    a.register("r", _image_renderer)
    assert "r" in a
    assert "r" not in b
