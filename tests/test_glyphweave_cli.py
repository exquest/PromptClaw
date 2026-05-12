from __future__ import annotations

from pathlib import Path

import pytest

from promptclaw import glyphweave_cli


def test_preview_builtin_scene_renders_terminal_and_png(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "starfield.png"

    exit_code = glyphweave_cli.main(
        [
            "preview",
            "--scene",
            "starfield",
            "--palette",
            "space",
            "--width",
            "20",
            "--height",
            "8",
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "starfield" in captured.out
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_preview_dsl_file_renders_canvas_and_png(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dsl_file = tmp_path / "scene.py"
    dsl_file.write_text(
        "\n".join(
            [
                "def build(width, height, palette):",
                "    canvas = Canvas(width, height)",
                "    canvas.place_text(0, 0, 'DSL')",
                "    canvas.place_emoji(3, 0, palette[0])",
                "    return canvas",
            ]
        )
    )
    output = tmp_path / "dsl.png"

    exit_code = glyphweave_cli.main(
        [
            "preview",
            "--dsl",
            str(dsl_file),
            "--palette",
            "water",
            "--width",
            "12",
            "--height",
            "4",
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DSL" in captured.out
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_preview_requires_exactly_one_source(tmp_path: Path) -> None:
    dsl_file = tmp_path / "scene.py"
    dsl_file.write_text("canvas = Canvas(width, height)")

    with pytest.raises(SystemExit, match="choose exactly one"):
        glyphweave_cli.main(["preview", "--scene", "starfield", "--dsl", str(dsl_file)])


def test_preview_rejects_unknown_scene() -> None:
    with pytest.raises(SystemExit, match="unknown scene"):
        glyphweave_cli.main(["preview", "--scene", "unknown-scene"])
