"""Tests for the renderer-matrix loader (T-012).

The renderer matrix maps ``asset_type`` to the *name* of the renderer
that handles it, loaded from a JSON config file. Routing uses it to
dispatch each request to the right renderer. Validation must reject
duplicate asset_types and empty renderer names so a malformed config
never silently routes to nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    RendererMatrix,
    RendererMatrixError,
    load_renderer_matrix,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_valid_object_matrix(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "renderers.json",
        {
            "image": "sd-image-renderer",
            "music": "music-renderer",
            "sfx": "sfx-renderer",
        },
    )
    matrix = load_renderer_matrix(config)
    assert isinstance(matrix, RendererMatrix)
    assert matrix["image"] == "sd-image-renderer"
    assert matrix["music"] == "music-renderer"
    assert matrix["sfx"] == "sfx-renderer"
    assert set(matrix) == {"image", "music", "sfx"}
    assert len(matrix) == 3


def test_load_valid_list_matrix(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "renderers.json",
        [
            {"asset_type": "image", "renderer": "sd-image-renderer"},
            {"asset_type": "music", "renderer": "music-renderer"},
        ],
    )
    matrix = load_renderer_matrix(config)
    assert matrix["image"] == "sd-image-renderer"
    assert matrix["music"] == "music-renderer"


def test_renderer_matrix_is_immutable(tmp_path: Path) -> None:
    config = _write(tmp_path / "r.json", {"image": "r1"})
    matrix = load_renderer_matrix(config)
    with pytest.raises(TypeError):
        matrix["image"] = "r2"  # type: ignore[index]


def test_missing_config_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(RendererMatrixError, match="not found"):
        load_renderer_matrix(missing)


def test_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RendererMatrixError, match="not valid JSON"):
        load_renderer_matrix(bad)


def test_empty_matrix_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "empty.json", {})
    with pytest.raises(RendererMatrixError, match="empty"):
        load_renderer_matrix(config)


def test_empty_renderer_name_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "r.json", {"image": ""})
    with pytest.raises(RendererMatrixError, match="non-empty"):
        load_renderer_matrix(config)


def test_whitespace_only_renderer_name_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "r.json", {"image": "   "})
    with pytest.raises(RendererMatrixError, match="non-empty"):
        load_renderer_matrix(config)


def test_non_string_renderer_name_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "r.json", {"image": 42})
    with pytest.raises(RendererMatrixError, match="non-empty"):
        load_renderer_matrix(config)


def test_duplicate_asset_type_rejected(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "dup.json",
        [
            {"asset_type": "image", "renderer": "r1"},
            {"asset_type": "image", "renderer": "r2"},
        ],
    )
    with pytest.raises(RendererMatrixError, match="duplicate"):
        load_renderer_matrix(config)


def test_list_entry_missing_keys_rejected(tmp_path: Path) -> None:
    config = _write(
        tmp_path / "bad.json",
        [{"asset_type": "image"}],
    )
    with pytest.raises(RendererMatrixError, match="missing"):
        load_renderer_matrix(config)


def test_top_level_wrong_shape_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "bad.json", "image=renderer")
    with pytest.raises(RendererMatrixError, match="must be a JSON object or list"):
        load_renderer_matrix(config)


def test_empty_asset_type_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / "bad.json", {"": "r1"})
    with pytest.raises(RendererMatrixError, match="asset_type"):
        load_renderer_matrix(config)
