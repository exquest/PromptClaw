"""Tests for collaborative_canvas.py — shared visual canvas for CypherClaw art installation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from collaborative_canvas import (
    CanvasLayer,
    Canvas,
    write_canvas_state,
    read_canvas_state,
)


# === CanvasLayer ===


class TestCanvasLayer:
    def test_dataclass_fields(self):
        layer = CanvasLayer(
            name="background",
            priority=0,
            content="solid blue",
            image_path=None,
            opacity=1.0,
            position=(0, 0),
            visible=True,
        )
        assert layer.name == "background"
        assert layer.priority == 0
        assert layer.content == "solid blue"
        assert layer.image_path is None
        assert layer.opacity == 1.0
        assert layer.position == (0, 0)
        assert layer.visible is True

    def test_image_path_layer(self):
        layer = CanvasLayer(
            name="art",
            priority=10,
            content=None,
            image_path="/tmp/art.png",
            opacity=0.8,
            position=(100, 200),
            visible=True,
        )
        assert layer.image_path == "/tmp/art.png"
        assert layer.content is None


# === Canvas ===


class TestCanvas:
    def test_add_layer(self):
        c = Canvas()
        layer = CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True)
        c.add_layer(layer)
        assert "bg" in c.layers

    def test_remove_layer(self):
        c = Canvas()
        layer = CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True)
        c.add_layer(layer)
        c.remove_layer("bg")
        assert "bg" not in c.layers

    def test_remove_nonexistent_layer_no_error(self):
        c = Canvas()
        c.remove_layer("nonexistent")  # Should not raise

    def test_set_visibility(self):
        c = Canvas()
        layer = CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True)
        c.add_layer(layer)
        c.set_visibility("bg", False)
        assert c.layers["bg"].visible is False
        c.set_visibility("bg", True)
        assert c.layers["bg"].visible is True

    def test_set_opacity(self):
        c = Canvas()
        layer = CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True)
        c.add_layer(layer)
        c.set_opacity("bg", 0.5)
        assert c.layers["bg"].opacity == 0.5

    def test_set_opacity_clamps(self):
        c = Canvas()
        layer = CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True)
        c.add_layer(layer)
        c.set_opacity("bg", -0.5)
        assert c.layers["bg"].opacity == 0.0
        c.set_opacity("bg", 1.5)
        assert c.layers["bg"].opacity == 1.0

    def test_get_visible_layers_sorted_by_priority(self):
        c = Canvas()
        c.add_layer(CanvasLayer("top", 100, "overlay", None, 1.0, (0, 0), True))
        c.add_layer(CanvasLayer("mid", 50, "art", None, 0.8, (0, 0), True))
        c.add_layer(CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True))
        visible = c.get_visible_layers()
        assert len(visible) == 3
        assert visible[0].name == "bg"
        assert visible[1].name == "mid"
        assert visible[2].name == "top"

    def test_get_visible_layers_excludes_hidden(self):
        c = Canvas()
        c.add_layer(CanvasLayer("visible", 0, "yes", None, 1.0, (0, 0), True))
        c.add_layer(CanvasLayer("hidden", 10, "no", None, 1.0, (0, 0), False))
        visible = c.get_visible_layers()
        assert len(visible) == 1
        assert visible[0].name == "visible"

    def test_get_visible_layers_empty_canvas(self):
        c = Canvas()
        assert c.get_visible_layers() == []

    def test_to_dict(self):
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True))
        d = c.to_dict()
        assert "layers" in d
        assert "bg" in d["layers"]
        layer_data = d["layers"]["bg"]
        assert layer_data["name"] == "bg"
        assert layer_data["priority"] == 0
        assert layer_data["opacity"] == 1.0
        assert layer_data["position"] == [0, 0]
        assert layer_data["visible"] is True

    def test_from_dict_roundtrip(self):
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True))
        c.add_layer(CanvasLayer("art", 10, None, "/tmp/art.png", 0.7, (50, 100), True))
        c.add_layer(CanvasLayer("overlay", 99, "text", None, 0.5, (10, 10), False))

        d = c.to_dict()
        c2 = Canvas.from_dict(d)

        assert set(c2.layers.keys()) == {"bg", "art", "overlay"}
        assert c2.layers["bg"].content == "blue"
        assert c2.layers["art"].image_path == "/tmp/art.png"
        assert c2.layers["art"].opacity == 0.7
        assert c2.layers["art"].position == (50, 100)
        assert c2.layers["overlay"].visible is False

    def test_from_dict_empty(self):
        c = Canvas.from_dict({"layers": {}})
        assert len(c.layers) == 0

    def test_add_layer_replaces_existing(self):
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True))
        c.add_layer(CanvasLayer("bg", 0, "red", None, 0.5, (0, 0), True))
        assert c.layers["bg"].content == "red"
        assert c.layers["bg"].opacity == 0.5


# === write_canvas_state / read_canvas_state ===


class TestCanvasIO:
    def test_write_and_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "canvas.json")
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "blue", None, 1.0, (0, 0), True))
        c.add_layer(CanvasLayer("art", 10, None, "/tmp/art.png", 0.8, (50, 50), True))

        write_canvas_state(c, path=path)
        loaded = read_canvas_state(path=path)

        assert loaded is not None
        assert set(loaded.layers.keys()) == {"bg", "art"}
        assert loaded.layers["bg"].content == "blue"
        assert loaded.layers["art"].opacity == 0.8

    def test_read_missing_returns_none(self, tmp_path):
        path = str(tmp_path / "missing.json")
        assert read_canvas_state(path=path) is None

    def test_read_corrupt_returns_none(self, tmp_path):
        path = str(tmp_path / "corrupt.json")
        Path(path).write_text("not json at all {{{{")
        assert read_canvas_state(path=path) is None

    def test_write_creates_file(self, tmp_path):
        path = str(tmp_path / "canvas.json")
        c = Canvas()
        write_canvas_state(c, path=path)
        assert Path(path).exists()

    def test_write_is_valid_json(self, tmp_path):
        path = str(tmp_path / "canvas.json")
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "x", None, 1.0, (0, 0), True))
        write_canvas_state(c, path=path)
        data = json.loads(Path(path).read_text())
        assert "layers" in data

    def test_atomic_write_no_partial(self, tmp_path):
        """File should not be left in a partial state after write."""
        path = str(tmp_path / "canvas.json")
        c = Canvas()
        c.add_layer(CanvasLayer("bg", 0, "test", None, 1.0, (0, 0), True))
        write_canvas_state(c, path=path)
        # File should be valid JSON
        data = json.loads(Path(path).read_text())
        assert data is not None

    def test_write_creates_parent_directories(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "canvas.json")
        c = Canvas()
        write_canvas_state(c, path=path)
        assert Path(path).exists()
