#!/usr/bin/env python3
"""Box-side image renderer for the Deniable Asset Bus.

The producer sends this command as argv data, never as a shell string. This
wrapper keeps the public contract small: prompt + size + optional seed/count
in, PNG files out under the requested output directory. The default renderer
loads the existing DreamShaper helper lazily so tests can parse and exercise
the CLI without CUDA, model weights, or Diffusers installed.
"""

import argparse
import random
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageRenderParams:
    """Resolved arguments for one image render request."""

    prompt: str
    width: int
    height: int
    seed: int | None
    count: int
    output_dir: Path


Renderer = Callable[[ImageRenderParams, int, Path], object]


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected integer, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parse_size(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must contain integer dimensions") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    return width, height


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render PNG image assets with the CypherClaw DreamShaper pipeline.",
    )
    parser.add_argument("--prompt", required=True, help="Text prompt for the generated image.")
    parser.add_argument(
        "--size",
        required=True,
        type=_parse_size,
        metavar="WIDTHxHEIGHT",
        help="Output image size, for example 768x512.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional deterministic seed. Multiple images use seed + index.",
    )
    parser.add_argument(
        "--count",
        type=_positive_int,
        default=1,
        help="Number of PNG files to generate.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where image-<n>.png files are written.",
    )
    return parser


def parse_render_params(argv: Sequence[str] | None = None) -> ImageRenderParams:
    """Parse CLI argv into resolved render parameters."""
    args = _build_parser().parse_args(argv)
    width, height = args.size
    return ImageRenderParams(
        prompt=args.prompt,
        width=width,
        height=height,
        seed=args.seed,
        count=args.count,
        output_dir=args.output_dir,
    )


def _seed_render(seed: int | None, index: int) -> int | None:
    if seed is None:
        return None
    actual_seed = seed + index
    random.seed(actual_seed)
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return actual_seed
    torch.manual_seed(actual_seed)
    cuda = getattr(torch, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "manual_seed_all", None)):
        cuda.manual_seed_all(actual_seed)
    return actual_seed


def _load_diffusion_generate() -> Callable[..., Any]:
    repo_root = Path(__file__).resolve().parent.parent
    tools_dir = repo_root / "my-claw" / "tools"
    tools_dir_text = str(tools_dir)
    if tools_dir_text not in sys.path:
        sys.path.insert(0, tools_dir_text)

    from diffusion_art import generate as diffusion_generate

    return diffusion_generate


def default_renderer(
    params: ImageRenderParams,
    index: int,
    target_path: Path,
) -> object:
    """Render one image through the existing DreamShaper helper."""
    del target_path
    _seed_render(params.seed, index)
    generate = _load_diffusion_generate()
    return generate(
        params.prompt,
        init_image=None,
        width=params.width,
        height=params.height,
    )


def _persist_rendered_output(rendered: object, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rendered, (str, Path)):
        source = Path(rendered)
        if source.resolve() != target_path.resolve():
            shutil.copyfile(source, target_path)
        return target_path

    save = getattr(rendered, "save", None)
    if callable(save):
        save(target_path)
        return target_path

    raise TypeError(
        "image renderer must return a path or an image-like object with save(...)"
    )


def render_images(
    params: ImageRenderParams,
    *,
    renderer: Renderer = default_renderer,
) -> list[Path]:
    """Render all requested images and return their output paths."""
    params.output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index in range(params.count):
        target_path = params.output_dir / f"image-{index}.png"
        rendered = renderer(params, index, target_path)
        outputs.append(_persist_rendered_output(rendered, target_path))
    return outputs


def main(
    argv: Sequence[str] | None = None,
    *,
    renderer: Renderer = default_renderer,
) -> int:
    """CLI entry point."""
    params = parse_render_params(argv)
    for output_path in render_images(params, renderer=renderer):
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
