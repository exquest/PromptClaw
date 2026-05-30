"""Smoke tests for the asset_render_image box-side CLI (T-021)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


PNG_BYTES = b"\x89PNG\r\n\x1a\nfake image bytes"


def _load_asset_render_image_module() -> ModuleType:
    module_path = Path(__file__).parent.parent / "tools" / "asset_render_image.py"
    spec = importlib.util.spec_from_file_location(
        "asset_render_image_test_module",
        module_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_documented_argv_resolves_render_parameters(tmp_path: Path) -> None:
    module = _load_asset_render_image_module()
    prompt = "weathered dossier; echo $(id) && keep this literal"

    params = module.parse_render_params(
        [
            "--prompt",
            prompt,
            "--size",
            "768x512",
            "--seed",
            "12345",
            "--count",
            "3",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert params.prompt == prompt
    assert params.width == 768
    assert params.height == 512
    assert params.seed == 12345
    assert params.count == 3
    assert params.output_dir == tmp_path


def test_render_images_writes_counted_pngs_with_injected_renderer(
    tmp_path: Path,
) -> None:
    module = _load_asset_render_image_module()
    calls: list[tuple[int, Path, int | None]] = []

    def fake_renderer(params: object, index: int, target_path: Path) -> Path:
        calls.append((index, target_path, params.seed))
        target_path.write_bytes(PNG_BYTES + str(index).encode("ascii"))
        return target_path

    exit_code = module.main(
        [
            "--prompt",
            "main menu background",
            "--size",
            "320x240",
            "--seed",
            "77",
            "--count",
            "2",
            "--output-dir",
            str(tmp_path / "renders"),
        ],
        renderer=fake_renderer,
    )

    assert exit_code == 0
    output_dir = tmp_path / "renders"
    assert calls == [
        (0, output_dir / "image-0.png", 77),
        (1, output_dir / "image-1.png", 77),
    ]
    assert (output_dir / "image-0.png").read_bytes() == PNG_BYTES + b"0"
    assert (output_dir / "image-1.png").read_bytes() == PNG_BYTES + b"1"


@pytest.mark.parametrize(
    "argv",
    [
        ["--prompt", "x", "--size", "bad", "--output-dir", "out"],
        ["--prompt", "x", "--size", "0x512", "--output-dir", "out"],
        ["--prompt", "x", "--size", "512x0", "--output-dir", "out"],
        ["--prompt", "x", "--size", "512x512", "--count", "0", "--output-dir", "out"],
        ["--prompt", "x", "--size", "512x512", "--count", "-1", "--output-dir", "out"],
    ],
)
def test_parse_rejects_invalid_size_and_count(argv: list[str]) -> None:
    module = _load_asset_render_image_module()

    with pytest.raises(SystemExit):
        module.parse_render_params(argv)
