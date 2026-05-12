"""Depth-2 collaborative_canvas helpers - locked test surface for frac-0007."""
from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from collaborative_canvas import (  # noqa: E402
    Canvas,
    CanvasLayer,
    canvas_layer_manifest,
    canvas_summary,
    read_canvas_state,
    render_text_canvas,
    write_canvas_state,
)


def test_canvas_layer_manifest_reports_ordered_layer_metadata() -> None:
    canvas = Canvas()
    canvas.add_layer(CanvasLayer("text", 20, "hello", None, 0.75, (4, 2), True))
    canvas.add_layer(CanvasLayer("image", 5, None, "/tmp/image.png", 1.0, (0, 0), True))
    canvas.add_layer(CanvasLayer("hidden", 10, "secret", None, 0.5, (1, 1), False))
    canvas.add_layer(CanvasLayer("empty", 30, None, None, 1.0, (9, 9), True))

    manifest = canvas_layer_manifest(canvas)

    assert manifest == [
        {
            "name": "image",
            "priority": 5,
            "kind": "image",
            "opacity": 1.0,
            "position": (0, 0),
            "visible": True,
        },
        {
            "name": "hidden",
            "priority": 10,
            "kind": "text",
            "opacity": 0.5,
            "position": (1, 1),
            "visible": False,
        },
        {
            "name": "text",
            "priority": 20,
            "kind": "text",
            "opacity": 0.75,
            "position": (4, 2),
            "visible": True,
        },
        {
            "name": "empty",
            "priority": 30,
            "kind": "empty",
            "opacity": 1.0,
            "position": (9, 9),
            "visible": True,
        },
    ]


def test_canvas_summary_reports_counts_top_layer_and_bounds() -> None:
    canvas = Canvas()
    canvas.add_layer(CanvasLayer("background", 0, "abc\nde", None, 1.0, (1, 2), True))
    canvas.add_layer(CanvasLayer("photo", 5, None, "/tmp/photo.png", 1.0, (0, 0), True))
    canvas.add_layer(CanvasLayer("label", 10, "XY", None, 0.8, (3, 1), True))
    canvas.add_layer(CanvasLayer("hidden-empty", 20, None, None, 1.0, (99, 99), False))

    summary = canvas_summary(canvas)

    assert summary == {
        "layer_count": 4,
        "visible_count": 3,
        "hidden_count": 1,
        "text_layers": 2,
        "image_layers": 1,
        "empty_layers": 1,
        "top_visible_layer": "label",
        "bounds": {"min_x": 0, "min_y": 0, "max_x": 5, "max_y": 4},
    }


def test_render_text_canvas_composes_visible_text_layers_by_priority() -> None:
    canvas = Canvas()
    canvas.add_layer(CanvasLayer("background", 0, "abcd\nefgh", None, 1.0, (0, 0), True))
    canvas.add_layer(CanvasLayer("top", 10, " Z\n  Q", None, 1.0, (1, 0), True))
    canvas.add_layer(CanvasLayer("hidden", 99, "X", None, 1.0, (0, 1), False))
    canvas.add_layer(CanvasLayer("image", 50, None, "/tmp/photo.png", 1.0, (0, 0), True))

    rendered = render_text_canvas(canvas, width=5, height=3, fill=".")

    assert rendered == "abZd.\nefQh.\n....."


def test_canvas_state_roundtrip_can_render_text_output(tmp_path: Path) -> None:
    path = str(tmp_path / "canvas.json")
    canvas = Canvas()
    canvas.add_layer(CanvasLayer("word", 0, "hi", None, 1.0, (1, 1), True))
    canvas.add_layer(CanvasLayer("punctuation", 5, "!", None, 1.0, (3, 1), True))

    write_canvas_state(canvas, path=path)
    loaded = read_canvas_state(path=path)

    assert loaded is not None
    assert render_text_canvas(loaded, width=5, height=3, fill=".") == ".....\n.hi!.\n....."
