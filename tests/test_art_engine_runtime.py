"""Tests for the art engine runtime helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import art_engine


def test_cycle_state_round_trip_creates_gallery_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(art_engine, "GALLERY_DIR", tmp_path / "gallery")

    initial = art_engine._get_cycle_state()
    art_engine._save_cycle_state({"cycle": 4, "model_index": 2, "theme_index": 1})
    restored = art_engine._get_cycle_state()

    assert initial == {"cycle": 0, "model_index": 0, "theme_index": 0}
    assert restored == {"cycle": 4, "model_index": 2, "theme_index": 1}
    assert (art_engine.GALLERY_DIR / ".art_engine_state.json").exists()


def test_extract_python_strips_fences_and_glyphweave_imports() -> None:
    source = """```python
from glyphweave.dsl import Canvas
import glyphweave
canvas = Canvas(4, 1)
canvas.place_text(0, 0, "hi")
print(canvas.render())
```"""

    extracted = art_engine.extract_python(source)

    assert "from glyphweave" not in extracted
    assert "import glyphweave" not in extracted
    assert 'print(canvas.render())' in extracted


def test_execute_art_code_returns_rendered_canvas() -> None:
    rendered = art_engine.execute_art_code(
        'canvas = Canvas(6, 2)\n'
        'canvas.place_text(0, 0, "hi")\n'
        'canvas.place_emoji(0, 1, "✨")\n'
        'print(canvas.render())\n'
    )

    assert rendered is not None
    assert "hi" in rendered
    assert "✨" in rendered


def test_generate_art_persists_sidecars_and_advances_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(art_engine, "GALLERY_DIR", tmp_path / "gallery")
    monkeypatch.setattr(art_engine, "MODELS", ["test-model"])
    monkeypatch.setattr(
        art_engine,
        "THEMES",
        [("test theme", "water", "A calm test scene")],
    )

    def fake_call(prompt: str, model: str = "unused") -> str:
        assert "test theme" in prompt
        assert model == "test-model"
        return (
            "```python\n"
            'canvas = Canvas(8, 3)\n'
            'canvas.place_text(0, 0, "art")\n'
            'canvas.place_emoji(0, 1, "🌊")\n'
            'print(canvas.render())\n'
            "```"
        )

    def fake_render_to_image(text_art: str, output_path: Path) -> bool:
        output_path.write_bytes(b"png")
        return True

    framebuffer_calls: list[Path] = []

    monkeypatch.setattr(art_engine, "call_ollama", fake_call)
    monkeypatch.setattr(art_engine, "render_to_image", fake_render_to_image)
    monkeypatch.setattr(
        art_engine,
        "render_to_framebuffer",
        lambda image_path: framebuffer_calls.append(Path(image_path)) or True,
    )

    result = art_engine.generate_art()

    assert result["success"] is True
    assert result["model"] == "test-model"
    assert result["theme"] == "test theme"
    assert "art" in result["text_art"]
    assert result["image_path"] is not None
    assert Path(result["image_path"]).exists()
    assert framebuffer_calls == [Path(result["image_path"])]

    txt_files = list(art_engine.GALLERY_DIR.glob("*.txt"))
    json_files = [
        path
        for path in art_engine.GALLERY_DIR.glob("*.json")
        if path.name != ".art_engine_state.json"
    ]
    state = json.loads((art_engine.GALLERY_DIR / ".art_engine_state.json").read_text())

    assert len(txt_files) == 1
    assert len(json_files) == 1
    assert state["cycle"] == 1
    assert state["model_index"] == 1
    assert state["theme_index"] == 1
