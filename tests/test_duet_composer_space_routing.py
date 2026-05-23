"""Static coverage for live composer mood-space playback routing (T-045c)."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DUET_COMPOSER_PATH = REPO_ROOT / "my-claw" / "tools" / "duet_composer.py"


def _duet_composer_source() -> str:
    return DUET_COMPOSER_PATH.read_text(encoding="utf-8")


def _function_block(source: str, name: str, next_name: str) -> str:
    match = re.search(
        rf"^def {name}\([\s\S]*?^def {next_name}\(",
        source,
        flags=re.MULTILINE,
    )
    assert match, f"could not locate {name} block"
    return match.group(0)


def test_play_voice_routes_profiled_voices_to_resolved_scene_space() -> None:
    source = _duet_composer_source()
    block = _function_block(source, "play_voice", "release_sustained")

    assert "resolve_voice_space_profile" in source
    assert "mood_mode:" in block
    assert "active_house:" in block
    assert re.search(
        r"resolve_voice_space_profile\(\s*resolved_voice,"
        r"[\s\S]*mood_mode=mood_mode,"
        r"[\s\S]*active_house=active_house,"
        r"[\s\S]*\)",
        block,
    )
    assert re.search(r'args\.extend\(\[\s*"fx_bus_id",', block)


def test_tracker_playback_passes_scene_space_context_to_play_voice() -> None:
    source = _duet_composer_source()
    match = re.search(
        r"def _play_tracker_event\(event: ScheduledTrackerEvent\) -> None:"
        r"[\s\S]*?def _on_scene_start",
        source,
    )
    assert match, "could not locate _play_tracker_event block"
    block = match.group(0)

    assert 'mood_mode=event.scene_metadata.get("mood_mode"' in block
    assert "active_house=_active_house_from_scene_metadata(event.scene_metadata)" in block
