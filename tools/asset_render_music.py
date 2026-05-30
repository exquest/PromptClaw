#!/usr/bin/env python3
"""Box-side music renderer for the Deniable Asset Bus.

The producer sends this command as argv data, never as a shell string. This
wrapper keeps the public contract small: scene + mood + duration + loopability
in, one WAV file out at the requested output path. The default renderer writes
a deterministic silent WAV with the standard library so tests can exercise the
CLI without SuperCollider, JACK, a live CypherClaw box, or provider credentials.
Deployed boxes can replace the renderer callback with the existing CypherClaw
synthesis stack without changing this argv contract.
"""

import argparse
import math
import shutil
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MusicRenderParams:
    """Resolved arguments for one music render request."""

    scene: str
    mood: tuple[str, ...]
    duration_seconds: float
    loopable: bool
    output: Path


Renderer = Callable[[MusicRenderParams], object]

_DEFAULT_SAMPLE_RATE: int = 8000
_DEFAULT_SAMPLE_WIDTH: int = 2
_DEFAULT_CHANNELS: int = 1
_SILENCE_CHUNK_FRAMES: int = 4096


def _non_empty_text(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("value must not be blank")
    return value


def _positive_duration(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected float, got {value!r}") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("duration must be a positive finite number")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render one WAV music asset with the CypherClaw synthesis pipeline.",
    )
    parser.add_argument(
        "--scene",
        required=True,
        type=_non_empty_text,
        help="Free-text scene description for the generated music.",
    )
    parser.add_argument(
        "--mood",
        required=True,
        action="append",
        type=_non_empty_text,
        help="Mood tag for the generated music. Repeat for multiple moods.",
    )
    parser.add_argument(
        "--duration",
        required=True,
        type=_positive_duration,
        help="Requested output duration in seconds.",
    )
    parser.add_argument(
        "--loopable",
        action="store_true",
        help="Request a loopable bed. The flag is advisory for the renderer.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="WAV file path to write.",
    )
    return parser


def parse_render_params(argv: Sequence[str] | None = None) -> MusicRenderParams:
    """Parse CLI argv into resolved render parameters."""
    args = _build_parser().parse_args(argv)
    return MusicRenderParams(
        scene=args.scene,
        mood=tuple(args.mood),
        duration_seconds=args.duration,
        loopable=args.loopable,
        output=args.output,
    )


def _write_silent_wav(
    output: Path,
    *,
    duration_seconds: float,
    sample_rate: int = _DEFAULT_SAMPLE_RATE,
) -> Path:
    frame_count = max(1, int(round(duration_seconds * sample_rate)))
    output.parent.mkdir(parents=True, exist_ok=True)
    silence = b"\x00" * (_DEFAULT_SAMPLE_WIDTH * _DEFAULT_CHANNELS)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(_DEFAULT_CHANNELS)
        handle.setsampwidth(_DEFAULT_SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        remaining = frame_count
        while remaining > 0:
            chunk_frames = min(remaining, _SILENCE_CHUNK_FRAMES)
            handle.writeframes(silence * chunk_frames)
            remaining -= chunk_frames
    return output


def default_renderer(params: MusicRenderParams) -> Path:
    """Render one deterministic WAV through the default offline fallback."""
    return _write_silent_wav(
        params.output,
        duration_seconds=params.duration_seconds,
    )


def _persist_rendered_output(rendered: object, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if rendered is None:
        if target_path.exists():
            return target_path
        raise TypeError("music renderer returned None without writing output")

    if isinstance(rendered, (str, Path)):
        source = Path(rendered)
        if source.resolve() != target_path.resolve():
            shutil.copyfile(source, target_path)
        return target_path

    raise TypeError("music renderer must return a path or write params.output")


def render_music(
    params: MusicRenderParams,
    *,
    renderer: Renderer = default_renderer,
) -> Path:
    """Render the requested music asset and return its WAV path."""
    params.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = renderer(params)
    return _persist_rendered_output(rendered, params.output)


def main(
    argv: Sequence[str] | None = None,
    *,
    renderer: Renderer = default_renderer,
) -> int:
    """CLI entry point."""
    params = parse_render_params(argv)
    print(render_music(params, renderer=renderer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
