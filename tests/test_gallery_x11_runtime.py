"""Runtime checks for the X11 gallery display launcher."""

from __future__ import annotations

import os
import sys
import json


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from gallery import gallery_x11 as mod


def test_gallery_x11_runtime_depth() -> None:
    """Gate to ensure this file maintains depth 2 classification."""
    from sdp.fractal import classify_depth
    assert classify_depth("tests/test_gallery_x11_runtime.py").depth >= 2


def test_gallery_window_position_uses_origin_on_secondary_x_screen(monkeypatch) -> None:
    monkeypatch.delenv("GALLERY_WINDOW_POS", raising=False)

    assert mod.gallery_window_position(":0.1") == "0,0"


def test_gallery_window_position_keeps_combined_desktop_default(monkeypatch) -> None:
    monkeypatch.delenv("GALLERY_WINDOW_POS", raising=False)

    assert mod.gallery_window_position(":0") == "1280,0"


def test_gallery_window_position_honors_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("GALLERY_WINDOW_POS", "12,34")

    assert mod.gallery_window_position(":0.1") == "12,34"


def test_load_playlist_returns_empty_when_dir_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(mod, "ART_DIR", tmp_path / "missing")
    assert mod.load_playlist() == []


def test_load_playlist_reads_json_sidecars(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(mod, "ART_DIR", tmp_path)
    
    # Public
    art1 = tmp_path / "1.png"
    art1.write_bytes(b"")
    meta1 = tmp_path / "1.json"
    meta1.write_text(json.dumps({"visibility": "public"}))
    
    # Private
    art2 = tmp_path / "2.png"
    art2.write_bytes(b"")
    meta2 = tmp_path / "2.json"
    meta2.write_text(json.dumps({"visibility": "private"}))
    
    # No sidecar
    art3 = tmp_path / "3.png"
    art3.write_bytes(b"")
    
    pieces = mod.load_playlist()
    assert pieces == [art1]


def test_init_pygame_display_safe_to_call_multiple_times() -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    mod.init_pygame_display()
    mod.init_pygame_display()
    assert mod.pygame.display.get_init()


def test_render_overlay_handles_missing_state_files() -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    mod.init_pygame_display()
    surface = mod.pygame.Surface((mod.WIDTH, mod.HEIGHT))
    # This should not raise an exception, as state file loading uses try-except
    mod.render_overlay(surface)
    assert surface.get_width() == mod.WIDTH
    assert surface.get_height() == mod.HEIGHT


def test_render_overlay_with_mocked_state(tmp_path, monkeypatch) -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    
    # Create mock state files
    composer_state = tmp_path / "composer_state.json"
    composer_state.write_text(json.dumps({"key": "C", "movement": "Allegro"}))
    
    active_chars = tmp_path / "active_characters.json"
    active_chars.write_text(json.dumps({"active_characters": ["sense_window"]}))
    
    garden_state = tmp_path / "garden_state.json"
    garden_state.write_text(json.dumps({"season": "Spring", "light": "Dusk"}))
    
    def mock_open(path, *args, **kwargs):
        if path == "/tmp/composer_state.json":
            return original_open(str(composer_state))
        elif path == "/tmp/active_characters.json":
            return original_open(str(active_chars))
        elif path == "/tmp/garden_state.json":
            return original_open(str(garden_state))
        return original_open(path, *args, **kwargs)
        
    import builtins
    original_open = builtins.open
    monkeypatch.setattr("builtins.open", mock_open)
    
    mod.init_pygame_display()
    surface = mod.pygame.Surface((mod.WIDTH, mod.HEIGHT))
    mod.render_overlay(surface)
    assert surface.get_width() == mod.WIDTH


def test_render_art_fallback(tmp_path) -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    mod.init_pygame_display()
    
    # Try to render a missing image; it should return a fallback surface
    missing_image = tmp_path / "missing.png"
    surface = mod.render_art(missing_image, (100, 100))
    
    assert surface.get_width() == 100
    assert surface.get_height() == 100
