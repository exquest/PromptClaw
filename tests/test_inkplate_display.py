"""Tests for the inkplate sampler-status renderer."""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.portfolio_report import SurfaceSnapshot

import inkplate_display


def test_inkplate_renderer_uses_combined_sample_status_helper(monkeypatch) -> None:
    calls: dict[str, tuple[object, object, object]] = {}

    def fake_helper(
        activity: object,
        playback_state: object,
        monitor_state: object,
    ) -> str:
        calls["args"] = (activity, playback_state, monitor_state)
        return "combined sampler line"

    monkeypatch.setattr(inkplate_display, "face_display_sample_status_text", fake_helper)

    renderer = inkplate_display.InkplateRenderer(width=800, height=600)
    snapshot = SurfaceSnapshot(
        song_title="Quiet Rooms",
        section_caption="Theme",
        practice_block="Harmony Lab",
        artistic_intent="CypherClaw leans toward bloom forms.",
    )
    activity = {"requested_sample_source": "theramini_in"}
    playback_state = {"playing": True, "mode": "freeze_bed"}
    monitor_state = {"error": ""}

    lines = renderer.build_lines(
        snapshot=snapshot,
        activity=activity,
        playback_state=playback_state,
        monitor_state=monitor_state,
    )

    assert calls["args"] == (activity, playback_state, monitor_state)
    assert lines[-1] == "combined sampler line"


def test_inkplate_renderer_truncates_long_sample_status_to_fit_width(
    monkeypatch,
) -> None:
    long_text = (
        "currently sampling theramini in via room mic"
        " · playing sample freeze bed from source self bus"
    )
    monkeypatch.setattr(
        inkplate_display,
        "face_display_sample_status_text",
        lambda *_args, **_kwargs: long_text,
    )

    renderer = inkplate_display.InkplateRenderer(width=220, height=160)
    line = renderer.build_lines(
        activity={"capture_ready": True},
        playback_state={"playing": True},
        monitor_state={},
    )[0]

    draw = ImageDraw.Draw(Image.new("1", (renderer.width, renderer.height), 1))
    bbox = draw.textbbox((0, 0), line, font=renderer.status_font)

    assert line.endswith("...")
    assert bbox[2] - bbox[0] <= renderer.content_width


def test_inkplate_renderer_keeps_sample_status_when_it_fits(monkeypatch) -> None:
    monkeypatch.setattr(
        inkplate_display,
        "face_display_sample_status_text",
        lambda *_args, **_kwargs: "playing sample freeze bed",
    )

    renderer = inkplate_display.InkplateRenderer(width=800, height=600)
    line = renderer.build_lines(
        activity={"capture_ready": True},
        playback_state={"playing": True},
        monitor_state={},
    )[0]

    assert line == "playing sample freeze bed"


def test_inkplate_renderer_omits_empty_sample_status(monkeypatch) -> None:
    monkeypatch.setattr(
        inkplate_display,
        "face_display_sample_status_text",
        lambda *_args, **_kwargs: "",
    )

    renderer = inkplate_display.InkplateRenderer(width=800, height=600)
    image = renderer.render(
        snapshot=SurfaceSnapshot(
            song_title="",
            section_caption="",
            practice_block="",
            artistic_intent="",
        ),
        activity=None,
        playback_state=None,
        monitor_state=None,
    )

    assert renderer.build_lines(activity=None, playback_state=None, monitor_state=None) == ()
    assert image.size == (800, 600)
