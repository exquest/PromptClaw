#!/usr/bin/env python3
"""Compatibility wrapper for the X11 gallery display entrypoint."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from gallery.gallery_x11 import (
    ART_DIR,
    DURATION,
    HEIGHT,
    WIDTH,
    gallery_window_position,
)
from gallery.gallery_x11 import main as _delegate_main


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI flags for the wrapper entrypoint."""
    parser = argparse.ArgumentParser(prog="gallery_x11", description=__doc__)
    parser.add_argument("--display", default=None, help="Override DISPLAY for this launch.")
    parser.add_argument("--window-pos", default=None, help="Override SDL window origin.")
    parser.add_argument("--check", action="store_true", help="Validate environment and exit.")
    return parser.parse_args(list(argv) if argv is not None else None)


def runtime_summary(env: dict[str, str] | None = None) -> dict[str, object]:
    """Summarize the effective gallery runtime configuration."""
    source = env if env is not None else os.environ
    display = source.get("DISPLAY", "")
    return {
        "display": display,
        "window_pos": gallery_window_position(display),
        "art_dir": str(ART_DIR),
        "art_dir_exists": ART_DIR.exists(),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "duration_seconds": DURATION,
    }


def validate_runtime(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Return human-readable problems with the gallery runtime, empty when healthy."""
    summary = runtime_summary(env)
    problems: list[str] = []
    if not summary["display"]:
        problems.append("DISPLAY is not set")
    if not summary["art_dir_exists"]:
        problems.append(f"art directory missing: {summary['art_dir']}")
    return tuple(problems)


def apply_overrides(
    args: argparse.Namespace, env: dict[str, str] | None = None
) -> None:
    """Apply parsed CLI overrides to the target environment."""
    target = env if env is not None else os.environ
    if args.display is not None:
        target["DISPLAY"] = args.display
    if args.window_pos is not None:
        target["GALLERY_WINDOW_POS"] = args.window_pos


def main(argv: Sequence[str] | None = None) -> int:
    """Validate runtime, then delegate to the underlying display loop."""
    args = parse_args(argv)
    apply_overrides(args)
    problems = validate_runtime()
    for problem in problems:
        print(problem, file=sys.stderr)
    if args.check:
        return 1 if problems else 0
    if problems:
        return 1
    _delegate_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
