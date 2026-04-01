"""Tests for the GlyphWeave runtime package."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import glyphweave
from glyphweave import dsl, pet_animations, pet_sprites, player, scenes
import tamagotchi


def test_package_lazy_exports_expose_canvas_and_pet_helpers() -> None:
    canvas = glyphweave.Canvas(4, 2)
    canvas.place_text(0, 0, "hi")

    frames = glyphweave.get_frames("claude", 1, "idle")
    portrait = glyphweave.get_portrait("codex", 2)

    assert "hi" in canvas.to_string()
    assert isinstance(frames, list) and frames
    assert isinstance(portrait, str) and portrait


def test_canvas_animation_and_json_helpers_round_trip() -> None:
    canvas = dsl.Canvas(6, 2)
    canvas.place_text(0, 0, "A🙂")
    overlay = dsl.Canvas(2, 1).place_text(0, 0, "OK")
    canvas.composite(overlay, offset_x=0, offset_y=1)

    rendered = canvas.to_string()
    errors = canvas.validate()

    animation = dsl.Animation(6, 2, frame_ms=150, loop=False).add_frame(canvas)
    aeaf = animation.to_aeaf()

    assert "A🙂" in rendered
    assert "OK" in rendered
    assert errors == []
    assert "AEAF:1" in aeaf
    assert "frame_ms=150" in aeaf
    assert dsl.to_json({"ok": True}) == '{"ok": true}'


def test_pet_sprites_and_contextual_animations_cover_expected_states() -> None:
    frames = pet_sprites.get_frames("gemini", 3, "thinking")
    evolution = pet_sprites.get_evolution_frames("claude", 1, 2)
    portrait = pet_sprites.get_portrait("cypherclaw", 4)
    contextual = pet_animations.build_contextual_frames("codex", "implement and test feature", pet_frames=frames[:2], num_frames=3)
    thinking = pet_animations.build_thinking_frames(pet_portrait=portrait, num_frames=2)

    assert len(frames) >= 4
    assert len(evolution) == 4
    assert "✨" in "\n".join(evolution)
    assert "cypherclaw" not in portrait.lower()  # portrait is art, not text label
    assert len(contextual) == 3
    assert "⌨️" in contextual[0] or "⚡" in contextual[0]
    assert len(thinking) == 2
    assert "🧠" in thinking[0]


def test_player_and_scenes_render_daemon_facing_outputs() -> None:
    art = scenes.CypherClawArt()
    pets = tamagotchi.PetManager().pets

    status = art.status_display(memory=5, tasks=2, schedules=1, artifacts=3, pets=pets)
    pet_status = art.pet_status_display(pets)
    preview = art.plan_preview([{"type": "agent", "label": "Research topic"}, {"type": "shell", "label": "Run tests"}])
    spinner_frames, spinner_ms = player.build_spinner_frames("gemini", "research docs", ["research"], pet_frames=pet_sprites.get_frames("gemini", 1, "thinking")[:2])
    processing_frames, processing_ms = player.build_processing_frames(pet_portrait=pets["cypherclaw"].get_portrait())

    edits: list[tuple[int, str]] = []
    aeaf = player.AEAFPlayer(
        frames=["frame one", "frame two"],
        frame_ms=1,
        loop=False,
        message_id=123,
        edit_fn=lambda msg_id, frame: edits.append((msg_id, frame)),
    )
    aeaf.start()
    aeaf.stop()

    assert "🧠 5 msgs" in status
    assert "🐾 PET STATUS" in pet_status
    assert "📜 Plan Preview" in preview
    assert spinner_frames and spinner_ms >= player.MIN_FRAME_MS
    assert processing_frames and processing_ms >= player.MIN_FRAME_MS
    assert all(frame.startswith("```") for frame in spinner_frames[:2])
