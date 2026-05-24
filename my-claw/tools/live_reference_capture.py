"""Capture a CypherClaw live HLS reference sample to an Opus file."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TextIO
from urllib.request import Request, urlopen

try:
    from cypherclaw.first_boot import bootstrap_identity as _bootstrap_identity
except ImportError:  # pragma: no cover
    try:
        from first_boot import bootstrap_identity as _bootstrap_identity
    except ImportError:  # pragma: no cover

        def _bootstrap_identity(**_kwargs: object) -> object:
            return None


DEFAULT_PLAYLIST_URL = "https://cypherclaw.holdenu.com/api/cypherclaw/live.m3u8"
DEFAULT_OUTPUT_DIR = Path("/home/user/cypherclaw/var/reference-renders")
DEFAULT_PREFIX = "feature-3-stream"
DEFAULT_DURATION_SECONDS = 60
DEFAULT_BITRATE_KBPS = 96
DEFAULT_CHECKSUM_LOG_NAME = "checksums.jsonl"
DEFAULT_PLAYLIST_TIMEOUT_SECONDS = 10.0
DEFAULT_FFMPEG_TIMEOUT_MARGIN_SECONDS = 30.0


class HttpResponse(Protocol):
    def __enter__(self) -> HttpResponse:
        ...

    def __exit__(self, *args: object) -> None:
        ...

    def read(self) -> bytes:
        ...


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
UrlOpenFn = Callable[..., HttpResponse]


@dataclass(frozen=True)
class CaptureConfig:
    playlist_url: str = DEFAULT_PLAYLIST_URL
    output_dir: Path = DEFAULT_OUTPUT_DIR
    duration_seconds: float = float(DEFAULT_DURATION_SECONDS)
    prefix: str = DEFAULT_PREFIX
    timestamp: str | None = None
    bitrate_kbps: int = DEFAULT_BITRATE_KBPS
    checksum_log: Path | None = None
    ffmpeg_bin: str = "ffmpeg"
    playlist_timeout_seconds: float = DEFAULT_PLAYLIST_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CaptureResult:
    output_path: Path
    checksum_log: Path
    sha256: str
    size_bytes: int
    duration_seconds: float
    playlist_url: str
    captured_at: str
    ffmpeg_command: tuple[str, ...]

    def to_log_record(self) -> dict[str, object]:
        return {
            "captured_at": self.captured_at,
            "checksum_log": str(self.checksum_log),
            "duration_seconds": self.duration_seconds,
            "ffmpeg_command": list(self.ffmpeg_command),
            "output_path": str(self.output_path),
            "playlist_url": self.playlist_url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _duration_arg(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}"


def _checksum_log_path(config: CaptureConfig) -> Path:
    return config.checksum_log or (config.output_dir / DEFAULT_CHECKSUM_LOG_NAME)


def build_output_path(config: CaptureConfig) -> Path:
    """Return the destination Opus path for this capture."""

    if not config.prefix.strip():
        raise ValueError("prefix is required")
    timestamp = config.timestamp or _utc_timestamp()
    return config.output_dir / f"{config.prefix}-{timestamp}.opus"


def build_ffmpeg_command(config: CaptureConfig, output_path: Path) -> list[str]:
    """Build the ffmpeg command for HLS to single-file Ogg Opus capture."""

    return [
        config.ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-t",
        _duration_arg(config.duration_seconds),
        "-i",
        config.playlist_url,
        "-vn",
        "-map",
        "0:a:0",
        "-c:a",
        "libopus",
        "-b:a",
        f"{config.bitrate_kbps}k",
        "-vbr",
        "constrained",
        "-application",
        "audio",
        "-frame_duration",
        "20",
        "-compression_level",
        "5",
        "-threads",
        "1",
        "-f",
        "ogg",
        str(output_path),
    ]


def playlist_has_media_segments(body: str) -> bool:
    """Return whether an HLS playlist body has media segment entries."""

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            return True
        if not line.startswith("#"):
            return True
    return False


def fetch_playlist(
    playlist_url: str,
    *,
    urlopen_fn: UrlOpenFn = urlopen,
    timeout_seconds: float = DEFAULT_PLAYLIST_TIMEOUT_SECONDS,
) -> str:
    """Fetch an HLS playlist body."""

    request = Request(
        playlist_url,
        headers={"User-Agent": "PromptClaw live-reference-capture"},
    )
    with urlopen_fn(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode(errors="replace")


def ensure_playlist_has_media_segments(
    config: CaptureConfig,
    *,
    urlopen_fn: UrlOpenFn = urlopen,
) -> str:
    """Fetch and validate that the configured playlist is not cold."""

    body = fetch_playlist(
        config.playlist_url,
        urlopen_fn=urlopen_fn,
        timeout_seconds=config.playlist_timeout_seconds,
    )
    if not playlist_has_media_segments(body):
        raise RuntimeError(
            f"playlist {config.playlist_url} has no media segments; "
            "start the CypherClaw audio producer before capture"
        )
    return body


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_checksum_log(path: Path, result: CaptureResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_log_record(), sort_keys=True) + "\n")


def _ffmpeg_detail(completed: subprocess.CompletedProcess[str]) -> str:
    detail = (completed.stderr or completed.stdout or "").strip()
    return detail or f"exit code {completed.returncode}"


def capture_reference_sample(
    config: CaptureConfig,
    *,
    run_command: RunCommand = subprocess.run,
    urlopen_fn: UrlOpenFn = urlopen,
) -> CaptureResult:
    """Capture one live reference sample and append its checksum log record."""

    output_path = build_output_path(config)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_log = _checksum_log_path(config)
    ensure_playlist_has_media_segments(config, urlopen_fn=urlopen_fn)

    command = build_ffmpeg_command(config, output_path)
    completed = run_command(
        command,
        capture_output=True,
        text=True,
        timeout=config.duration_seconds + DEFAULT_FFMPEG_TIMEOUT_MARGIN_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg capture failed: {_ffmpeg_detail(completed)}")
    if not output_path.exists():
        raise RuntimeError(f"ffmpeg did not create output file: {output_path}")

    size_bytes = output_path.stat().st_size
    if size_bytes <= 0:
        raise RuntimeError(f"ffmpeg created an empty output file: {output_path}")

    result = CaptureResult(
        output_path=output_path,
        checksum_log=checksum_log,
        sha256=_sha256_file(output_path),
        size_bytes=size_bytes,
        duration_seconds=config.duration_seconds,
        playlist_url=config.playlist_url,
        captured_at=_iso_now(),
        ffmpeg_command=tuple(command),
    )
    _append_checksum_log(checksum_log, result)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a CypherClaw live HLS reference sample to Opus",
    )
    parser.add_argument("--playlist-url", default=DEFAULT_PLAYLIST_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--duration-seconds", type=float, default=float(DEFAULT_DURATION_SECONDS))
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--timestamp")
    parser.add_argument("--bitrate-kbps", type=int, default=DEFAULT_BITRATE_KBPS)
    parser.add_argument("--checksum-log", type=Path)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument(
        "--playlist-timeout-seconds",
        type=float,
        default=DEFAULT_PLAYLIST_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--identity-mode",
        choices=("standalone", "federated"),
        default="standalone",
    )
    parser.add_argument("--identity-release", default="")
    parser.add_argument("--identity-parent-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> CaptureConfig:
    return CaptureConfig(
        playlist_url=args.playlist_url,
        output_dir=args.output_dir,
        duration_seconds=args.duration_seconds,
        prefix=args.prefix,
        timestamp=args.timestamp,
        bitrate_kbps=args.bitrate_kbps,
        checksum_log=args.checksum_log,
        ffmpeg_bin=args.ffmpeg_bin,
        playlist_timeout_seconds=args.playlist_timeout_seconds,
    )


def _print_json(payload: object, *, file: TextIO | None = None) -> None:
    stream = sys.stdout if file is None else file
    print(json.dumps(payload, indent=2, sort_keys=True), file=stream)


def _dry_run_payload(config: CaptureConfig) -> dict[str, object]:
    output_path = build_output_path(config)
    return {
        "checksum_log": str(_checksum_log_path(config)),
        "dry_run": True,
        "ffmpeg_command": build_ffmpeg_command(config, output_path),
        "ok": True,
        "output_path": str(output_path),
    }


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    # Ensure identity is bootstrapped on startup (before work or dry-run)
    _bootstrap_identity(
        mode=args.identity_mode,
        release=args.identity_release,
        parent_id=args.identity_parent_id,
    )

    config = _config_from_args(args)

    if args.dry_run:
        _print_json(_dry_run_payload(config))
        return 0

    try:
        result = capture_reference_sample(config)
    except Exception as exc:
        _print_json({"error": str(exc), "ok": False}, file=sys.stderr)
        return 1
    _print_json({"capture": result.to_log_record(), "ok": True})
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
