"""Smoke tests for the asset_render_music box-side CLI (T-022)."""

from __future__ import annotations

import importlib.util
import wave
from pathlib import Path
from types import ModuleType

import pytest


def _load_asset_render_music_module() -> ModuleType:
    module_path = Path(__file__).parent.parent / "tools" / "asset_render_music.py"
    spec = importlib.util.spec_from_file_location(
        "asset_render_music_test_module",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_test_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 16)


def test_parse_documented_argv_resolves_render_parameters(tmp_path: Path) -> None:
    module = _load_asset_render_music_module()
    scene = "tense stakeout; echo $(id) && keep literal"

    params = module.parse_render_params(
        [
            "--scene",
            scene,
            "--mood",
            "tense",
            "--mood",
            "cold",
            "--duration",
            "12.5",
            "--loopable",
            "--output",
            str(tmp_path / "stakeout-loop.wav"),
        ]
    )

    assert params.scene == scene
    assert params.mood == ("tense", "cold")
    assert params.duration_seconds == 12.5
    assert params.loopable is True
    assert params.output == tmp_path / "stakeout-loop.wav"


def test_render_music_writes_wav_with_injected_renderer(tmp_path: Path) -> None:
    module = _load_asset_render_music_module()
    output = tmp_path / "renders" / "stakeout-loop.wav"
    calls: list[object] = []

    def fake_renderer(params: object) -> Path:
        calls.append(params)
        assert params.output.parent.is_dir()
        _write_test_wav(params.output)
        return params.output

    exit_code = module.main(
        [
            "--scene",
            "patient surveillance",
            "--mood",
            "patient",
            "--duration",
            "1.25",
            "--output",
            str(output),
        ],
        renderer=fake_renderer,
    )

    assert exit_code == 0
    assert len(calls) == 1
    with wave.open(str(output), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        assert handle.getnframes() == 16


@pytest.mark.parametrize(
    "argv",
    [
        ["--scene", "x", "--mood", "tense", "--duration", "bad", "--output", "out.wav"],
        ["--scene", "x", "--mood", "tense", "--duration", "0", "--output", "out.wav"],
        ["--scene", "x", "--mood", "tense", "--duration", "-1", "--output", "out.wav"],
        ["--scene", "x", "--mood", "tense", "--duration", "nan", "--output", "out.wav"],
        ["--scene", "x", "--mood", "tense", "--duration", "inf", "--output", "out.wav"],
        ["--scene", "x", "--duration", "1", "--output", "out.wav"],
        ["--scene", "   ", "--mood", "tense", "--duration", "1", "--output", "out.wav"],
    ],
)
def test_parse_rejects_invalid_duration_mood_and_scene(argv: list[str]) -> None:
    module = _load_asset_render_music_module()

    with pytest.raises(SystemExit):
        module.parse_render_params(argv)
