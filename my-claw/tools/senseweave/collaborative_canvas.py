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
