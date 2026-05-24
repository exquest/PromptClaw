"""Render the feature-1 per-voice-reverb-spaces 60-second checkpoint sample.

Thin orchestration around :mod:`live_reference_capture` that:

* asserts every voice in :data:`VOICE_REVERB_PROFILES` required by the
  CypherClaw v2 design statement has a profile populated (so the capture
  actually reflects "per-voice reverb spaces active"), and
* writes the captured Opus file to a local staging path that the T-056b
  upload step (``session_archiver.py``) consumes.

Actual capture still requires a hot HLS stream on the CypherClaw box (see
``ESCALATIONS.md``).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.request import urlopen

_REPO_TOOLS_DIR = Path(__file__).resolve().parent
if str(_REPO_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_TOOLS_DIR))
_REPO_SRC_DIR = _REPO_TOOLS_DIR.parents[1] / "src"
if str(_REPO_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC_DIR))

from cypherclaw.space_reverb import VOICE_REVERB_PROFILES  # noqa: E402
from live_reference_capture import (  # noqa: E402
    DEFAULT_DURATION_SECONDS,
    DEFAULT_PLAYLIST_URL,
    CaptureConfig,
    CaptureResult,
    RunCommand,
    UrlOpenFn,
    capture_reference_sample,
)

CHECKPOINT_PREFIX = "feature-1-reverb-spaces"
DEFAULT_STAGING_DIR = Path(
    "/home/user/cypherclaw/var/reference-renders/checkpoints/feature-1-reverb-spaces"
)
REQUIRED_REVERB_VOICES: tuple[str, ...] = (
    "pluck",
    "breath",
    "choir",
    "kotekan",
    "pad",
    "bowed",
    "tabla_tin",
)


@dataclass(frozen=True)
class ReverbRenderConfig:
    playlist_url: str = DEFAULT_PLAYLIST_URL
    staging_dir: Path = DEFAULT_STAGING_DIR
    duration_seconds: float = float(DEFAULT_DURATION_SECONDS)
    timestamp: str | None = None
    bitrate_kbps: int = 96
    checksum_log: Path | None = None
    ffmpeg_bin: str = "ffmpeg"

    def to_capture_config(self) -> CaptureConfig:
        return CaptureConfig(
            playlist_url=self.playlist_url,
            output_dir=self.staging_dir,
            duration_seconds=self.duration_seconds,
            prefix=CHECKPOINT_PREFIX,
            timestamp=self.timestamp,
            bitrate_kbps=self.bitrate_kbps,
            checksum_log=self.checksum_log,
            ffmpeg_bin=self.ffmpeg_bin,
        )


def assert_per_voice_reverb_active(
    profiles: dict[str, object] | None = None,
) -> None:
    """Raise ``RuntimeError`` if any required voice lacks a reverb profile."""

    available = profiles if profiles is not None else VOICE_REVERB_PROFILES
    missing = [voice for voice in REQUIRED_REVERB_VOICES if voice not in available]
    if missing:
        raise RuntimeError(
            "per-voice reverb spaces are not active for required voices: "
            + ", ".join(missing)
        )


def render_reverb_reference_sample(
    config: ReverbRenderConfig,
    *,
    run_command: RunCommand = subprocess.run,
    urlopen_fn: UrlOpenFn = urlopen,
) -> CaptureResult:
    """Render the feature-1 reverb-spaces sample to the staging path."""

    assert_per_voice_reverb_active()
    return capture_reference_sample(
        config.to_capture_config(),
        run_command=run_command,
        urlopen_fn=urlopen_fn,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render the feature-1 per-voice-reverb-spaces 60-second checkpoint "
            "sample to a local staging path."
        ),
    )
    parser.add_argument("--playlist-url", default=DEFAULT_PLAYLIST_URL)
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR)
    parser.add_argument(
        "--duration-seconds", type=float, default=float(DEFAULT_DURATION_SECONDS)
    )
    parser.add_argument("--timestamp")
    parser.add_argument("--bitrate-kbps", type=int, default=96)
    parser.add_argument("--checksum-log", type=Path)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> ReverbRenderConfig:
    return ReverbRenderConfig(
        playlist_url=args.playlist_url,
        staging_dir=args.staging_dir,
        duration_seconds=args.duration_seconds,
        timestamp=args.timestamp,
        bitrate_kbps=args.bitrate_kbps,
        checksum_log=args.checksum_log,
        ffmpeg_bin=args.ffmpeg_bin,
    )


def _print_json(payload: object, *, file: TextIO | None = None) -> None:
    stream = sys.stdout if file is None else file
    print(json.dumps(payload, indent=2, sort_keys=True), file=stream)


def _dry_run_payload(config: ReverbRenderConfig) -> dict[str, object]:
    from live_reference_capture import build_ffmpeg_command, build_output_path

    capture_config = config.to_capture_config()
    output_path = build_output_path(capture_config)
    checksum_log = capture_config.checksum_log or (
        capture_config.output_dir / "checksums.jsonl"
    )
    return {
        "checkpoint_prefix": CHECKPOINT_PREFIX,
        "checksum_log": str(checksum_log),
        "dry_run": True,
        "ffmpeg_command": build_ffmpeg_command(capture_config, output_path),
        "ok": True,
        "output_path": str(output_path),
        "required_reverb_voices": list(REQUIRED_REVERB_VOICES),
        "staging_dir": str(config.staging_dir),
    }


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = _config_from_args(args)

    try:
        assert_per_voice_reverb_active()
    except RuntimeError as exc:
        _print_json({"error": str(exc), "ok": False}, file=sys.stderr)
        return 1

    if args.dry_run:
        _print_json(_dry_run_payload(config))
        return 0

    try:
        result = render_reverb_reference_sample(config)
    except Exception as exc:  # noqa: BLE001 — surface any capture failure
        _print_json({"error": str(exc), "ok": False}, file=sys.stderr)
        return 1
    _print_json({"capture": result.to_log_record(), "ok": True})
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


__all__ = [
    "CHECKPOINT_PREFIX",
    "DEFAULT_STAGING_DIR",
    "REQUIRED_REVERB_VOICES",
    "ReverbRenderConfig",
    "assert_per_voice_reverb_active",
    "parse_args",
    "render_reverb_reference_sample",
    "run",
]


if __name__ == "__main__":
    main()
