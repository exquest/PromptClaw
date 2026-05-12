"""Collaborative Canvas — shared visual canvas for CypherClaw art installation.

Multiple sources (art engine, narrative engine, sensor display) contribute
layers to a shared canvas.  Each layer has a priority, opacity, position,
and visibility flag.  The canvas state is serialised to JSON for the
rendering pipeline.

Stdlib only.  Atomic file writes via tmp+rename.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------

_DEFAULT_CANVAS_PATH = "/tmp/canvas_state.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# CanvasLayer dataclass
# ---------------------------------------------------------------------------


@dataclass
class CanvasLayer:
    """A single compositing layer on the shared canvas."""

    name: str
    priority: int
    content: str | None
    image_path: str | None
    opacity: float
    position: tuple[int, int]
    visible: bool


# ---------------------------------------------------------------------------
# Canvas class
# ---------------------------------------------------------------------------


class Canvas:
    """A collection of named layers that can be composited in priority order."""

    def __init__(self) -> None:
        self.layers: dict[str, CanvasLayer] = {}

    def add_layer(self, layer: CanvasLayer) -> None:
        """Add or replace a layer by name."""
        self.layers[layer.name] = layer

    def remove_layer(self, name: str) -> None:
        """Remove a layer by name. No-op if it doesn't exist."""
        self.layers.pop(name, None)

    def set_visibility(self, name: str, visible: bool) -> None:
        """Set a layer's visibility flag.

        Raises KeyError if the layer does not exist.
        """
        self.layers[name].visible = visible

    def set_opacity(self, name: str, opacity: float) -> None:
        """Set a layer's opacity (clamped to 0.0-1.0).

        Raises KeyError if the layer does not exist.
        """
        self.layers[name].opacity = _clamp(opacity, 0.0, 1.0)

    def get_visible_layers(self) -> list[CanvasLayer]:
        """Return visible layers sorted by priority (lowest first = bottom)."""
        return sorted(
            [layer for layer in self.layers.values() if layer.visible],
            key=lambda layer: layer.priority,
        )

    def to_dict(self) -> dict:
        """Serialize the canvas to a JSON-friendly dict."""
        layers_dict: dict[str, dict] = {}
        for name, layer in self.layers.items():
            layers_dict[name] = {
                "name": layer.name,
                "priority": layer.priority,
                "content": layer.content,
                "image_path": layer.image_path,
                "opacity": layer.opacity,
                "position": list(layer.position),
                "visible": layer.visible,
            }
        return {"layers": layers_dict}

    @classmethod
    def from_dict(cls, data: dict) -> Canvas:
        """Deserialize a canvas from a dict."""
        canvas = cls()
        for name, layer_data in data.get("layers", {}).items():
            pos = layer_data.get("position", [0, 0])
            layer = CanvasLayer(
                name=layer_data["name"],
                priority=layer_data["priority"],
                content=layer_data.get("content"),
                image_path=layer_data.get("image_path"),
                opacity=layer_data.get("opacity", 1.0),
                position=tuple(pos),
                visible=layer_data.get("visible", True),
            )
            canvas.layers[name] = layer
        return canvas


# ---------------------------------------------------------------------------
# Diagnostics / simple text rendering
# ---------------------------------------------------------------------------


def canvas_layer_manifest(canvas: Canvas) -> list[dict[str, object]]:
    """Return priority-sorted, JSON-friendly metadata for every layer."""
    manifest: list[dict[str, object]] = []
    for layer in sorted(canvas.layers.values(), key=lambda item: item.priority):
        kind = "empty"
        if layer.image_path:
            kind = "image"
        elif layer.content is not None:
            kind = "text"
        manifest.append(
            {
                "name": layer.name,
                "priority": layer.priority,
                "kind": kind,
                "opacity": layer.opacity,
                "position": layer.position,
                "visible": layer.visible,
            }
        )
    return manifest


def canvas_summary(canvas: Canvas) -> dict[str, object]:
    """Return a stable operator summary of layer counts and visible bounds."""
    manifest = canvas_layer_manifest(canvas)
    summary: dict[str, object] = {
        "layer_count": len(manifest),
        "visible_count": 0,
        "hidden_count": 0,
        "text_layers": 0,
        "image_layers": 0,
        "empty_layers": 0,
        "top_visible_layer": None,
        "bounds": None,
    }
    for item in manifest:
        if item["visible"]:
            summary["visible_count"] = int(summary["visible_count"]) + 1
        else:
            summary["hidden_count"] = int(summary["hidden_count"]) + 1
        kind = item["kind"]
        if kind == "text":
            summary["text_layers"] = int(summary["text_layers"]) + 1
        elif kind == "image":
            summary["image_layers"] = int(summary["image_layers"]) + 1
        else:
            summary["empty_layers"] = int(summary["empty_layers"]) + 1

    min_x: int | None = None
    min_y: int | None = None
    max_x: int | None = None
    max_y: int | None = None
    visible_layers = canvas.get_visible_layers()
    for layer in visible_layers:
        x, y = layer.position
        width = 0
        height = 0
        if layer.image_path:
            width = 1
            height = 1
        elif layer.content:
            lines = layer.content.splitlines()
            width = max((len(line) for line in lines), default=0)
            height = len(lines)
        if width <= 0 or height <= 0:
            continue
        min_x = x if min_x is None else min(min_x, x)
        min_y = y if min_y is None else min(min_y, y)
        max_x = x + width if max_x is None else max(max_x, x + width)
        max_y = y + height if max_y is None else max(max_y, y + height)

    if visible_layers:
        summary["top_visible_layer"] = visible_layers[-1].name
    if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
        summary["bounds"] = {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
        }
    return summary


def render_text_canvas(
    canvas: Canvas,
    width: int,
    height: int,
    fill: str = " ",
) -> str:
    """Composite visible text layers into a fixed-size text grid."""
    if width <= 0 or height <= 0:
        return ""
    fill_char = fill[:1] if fill else " "
    rows = [[fill_char for _ in range(width)] for _ in range(height)]
    for layer in canvas.get_visible_layers():
        if not layer.content or layer.opacity <= 0:
            continue
        origin_x, origin_y = layer.position
        for dy, line in enumerate(layer.content.splitlines()):
            y = origin_y + dy
            if y < 0 or y >= height:
                continue
            x = origin_x
            leading_indent_open = True
            leading_indent_used = False
            for char in line:
                if char == " ":
                    if leading_indent_open:
                        if not leading_indent_used:
                            x += 1
                            leading_indent_used = True
                        continue
                    x += 1
                    continue
                leading_indent_open = False
                if x < 0 or x >= width:
                    x += 1
                    continue
                rows[y][x] = char
                x += 1
    return "\n".join("".join(row) for row in rows)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_canvas_state(canvas: Canvas, path: str = _DEFAULT_CANVAS_PATH) -> None:
    """Atomically write canvas state to a JSON file.

    Uses write-to-temp-then-rename to avoid partial writes.

    Parameters
    ----------
    canvas : Canvas
        The canvas to serialize.
    path : str
        Destination file path.
    """
    data = canvas.to_dict()
    content = json.dumps(data, indent=2)

    # Ensure parent directory exists
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, path)
    except BaseException:
        os.close(fd) if not _fd_closed(fd) else None
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _fd_closed(fd: int) -> bool:
    """Check if a file descriptor is already closed."""
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True


def read_canvas_state(path: str = _DEFAULT_CANVAS_PATH) -> Canvas | None:
    """Read canvas state from a JSON file.

    Parameters
    ----------
    path : str
        Path to the canvas state file.

    Returns
    -------
    Canvas | None
        The deserialized canvas, or None if the file is missing or corrupt.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Canvas.from_dict(data)
    except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
