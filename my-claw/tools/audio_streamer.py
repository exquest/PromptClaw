"""Stream the live JACK output bus into short Opus segment files."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.request import Request, urlopen

try:
    from cypherclaw.first_boot import bootstrap_identity as _bootstrap_identity
except ImportError:  # pragma: no cover - runtime fallback for copied tool trees
    try:
        from first_boot import bootstrap_identity as _bootstrap_identity
    except ImportError:  # pragma: no cover - defensive fallback

        def _bootstrap_identity(
            *,
            mode: str = "standalone",
            release: str = "",
            parent_id: str | None = None,
        ) -> object:
            return None


IdentityMode = Literal["standalone", "federated"]

DEFAULT_CLIENT_NAME = "cypherclaw-opus-stream"
DEFAULT_OUTPUT_DIR = Path("/home/user/cypherclaw-data/streams")
DEFAULT_PID_FILE = Path("/tmp/cypherclaw-audio-streamer.pid")
DEFAULT_SOURCE_PORTS = ("SuperCollider:out_1", "SuperCollider:out_2")
DEFAULT_SEGMENT_SECONDS = 6
DEFAULT_BITRATE_KBPS = 96
DEFAULT_CONNECT_TIMEOUT_SECONDS = 8.0
DEFAULT_DURATION_TOLERANCE_SECONDS = 0.75
DEFAULT_BITRATE_TOLERANCE_RATIO = 0.25
DEFAULT_MAX_CPU_PERCENT = 10.0
DEFAULT_WORKER_SEGMENT_URL = "https://cypherclaw.holdenu.com/api/cypherclaw/segment"
DEFAULT_SEGMENT_CONTENT_TYPE = "audio/ogg; codecs=opus"


class StreamProcess(Protocol):
    pid: int

    def poll(self) -> int | None:
        ...

    def terminate(self) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., StreamProcess]
BootstrapIdentityFn = Callable[..., object]


class HttpResponse(Protocol):
    def __enter__(self) -> HttpResponse:
        ...

    def __exit__(self, *args: object) -> None:
        ...

    def read(self) -> bytes:
        ...


UrlOpenFn = Callable[..., HttpResponse]


@dataclass(frozen=True)
class StreamerConfig:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    client_name: str = DEFAULT_CLIENT_NAME
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS
    bitrate_kbps: int = DEFAULT_BITRATE_KBPS
    source_ports: tuple[str, ...] = DEFAULT_SOURCE_PORTS
    jack_wrapper: tuple[str, ...] = ()
    pid_file: Path | None = DEFAULT_PID_FILE
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    identity_mode: IdentityMode = "standalone"
    identity_release: str = ""
    identity_parent_id: str | None = None


@dataclass(frozen=True)
class SegmentUploadConfig:
    endpoint_url: str = DEFAULT_WORKER_SEGMENT_URL
    admin_token: str = ""
    sequence: int = 0
    captured_at: str = ""
    duration_seconds: float = float(DEFAULT_SEGMENT_SECONDS)
    scene: str = ""
    tuning: str = ""
    source: str = "jack-streamer"
    content_type: str = DEFAULT_SEGMENT_CONTENT_TYPE


@dataclass(frozen=True)
class SegmentUploadResult:
    ok: bool
    key: str
    sequence: int
    size: int
    latency_ms: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "key": self.key,
            "sequence": self.sequence,
            "size": self.size,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class SegmentProbe:
    path: Path
    duration_seconds: float
    bitrate_bps: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "duration_seconds": self.duration_seconds,
            "bitrate_bps": self.bitrate_bps,
        }


@dataclass(frozen=True)
class SegmentValidation:
    path: Path
    ok: bool
    duration_ok: bool
    bitrate_ok: bool
    duration_delta_seconds: float
    bitrate_delta_ratio: float
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "ok": self.ok,
            "duration_ok": self.duration_ok,
            "bitrate_ok": self.bitrate_ok,
            "duration_delta_seconds": self.duration_delta_seconds,
            "bitrate_delta_ratio": self.bitrate_delta_ratio,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class CpuCheck:
    pid: int
    ok: bool
    cpu_percent: float | None
    max_cpu_percent: float
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "ok": self.ok,
            "cpu_percent": self.cpu_percent,
            "max_cpu_percent": self.max_cpu_percent,
            "errors": list(self.errors),
        }


def _wrapped(config: StreamerConfig, command: Sequence[str]) -> list[str]:
    return [*config.jack_wrapper, *command]


def _segment_pattern(config: StreamerConfig) -> str:
    return str(config.output_dir / f"{config.client_name}-%Y%m%dT%H%M%S.opus")


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def build_segment_upload_request(path: Path, config: SegmentUploadConfig) -> Request:
    """Build the Worker POST request for one completed Opus segment."""

    if config.sequence < 0:
        raise ValueError("sequence must be non-negative")
    if not config.admin_token:
        raise ValueError("admin_token is required")
    captured_at = config.captured_at or _utc_now_iso()
    headers = {
        "Authorization": f"Bearer {config.admin_token}",
        "Content-Type": config.content_type,
        "X-CypherClaw-Sequence": str(config.sequence),
        "X-CypherClaw-Captured-At": captured_at,
        "X-CypherClaw-Duration": f"{config.duration_seconds:.3f}",
    }
    if config.scene:
        headers["X-CypherClaw-Scene"] = config.scene
    if config.tuning:
        headers["X-CypherClaw-Tuning"] = config.tuning
    if config.source:
        headers["X-CypherClaw-Source"] = config.source
    return Request(
        config.endpoint_url,
        data=path.read_bytes(),
        headers=headers,
        method="POST",
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_int(payload: dict[str, object], name: str) -> int:
    value = _optional_int(payload.get(name))
    if value is None:
        raise RuntimeError(f"Worker response missing integer field {name!r}")
    return value


def post_segment_to_worker(
    path: Path,
    config: SegmentUploadConfig,
    *,
    urlopen_fn: UrlOpenFn = urlopen,
    timeout_seconds: float = 15.0,
) -> SegmentUploadResult:
    """Post one segment to the Worker and return its ingest result."""

    request = build_segment_upload_request(path, config)
    with urlopen_fn(request, timeout=timeout_seconds) as response:  # noqa: S310
        payload = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise RuntimeError("Worker response must be a JSON object")
    return SegmentUploadResult(
        ok=bool(payload.get("ok")),
        key=str(payload.get("key", "")),
        sequence=_required_int(payload, "sequence"),
        size=_required_int(payload, "size"),
        latency_ms=_optional_int(payload.get("latency_ms")),
    )


def build_ffmpeg_command(config: StreamerConfig) -> list[str]:
    """Build the ffmpeg command that captures JACK and writes Opus segments."""

    return _wrapped(
        config,
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "warning",
            "-f",
            "jack",
            "-ac",
            str(len(config.source_ports)),
            "-i",
            config.client_name,
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
            "segment",
            "-segment_time",
            str(config.segment_seconds),
            "-segment_format",
            "ogg",
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            _segment_pattern(config),
        ],
    )


def jack_input_ports(config: StreamerConfig) -> tuple[str, ...]:
    return tuple(
        f"{config.client_name}:input_{channel}"
        for channel in range(1, len(config.source_ports) + 1)
    )


def build_jack_connect_commands(config: StreamerConfig) -> tuple[list[str], ...]:
    return tuple(
        _wrapped(config, ["jack_connect", source, destination])
        for source, destination in zip(config.source_ports, jack_input_ports(config), strict=True)
    )


def wait_for_jack_inputs(
    config: StreamerConfig,
    *,
    process: StreamProcess | None = None,
    run_command: RunCommand = subprocess.run,
    poll_interval_seconds: float = 0.1,
) -> None:
    """Wait until ffmpeg's JACK input ports appear in `jack_lsp`."""

    expected = set(jack_input_ports(config))
    deadline = time.monotonic() + config.connect_timeout_seconds
    command = _wrapped(config, ["jack_lsp"])
    last_listing = ""
    while time.monotonic() <= deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("ffmpeg exited before JACK input ports appeared")
        completed = run_command(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        last_listing = completed.stdout or ""
        if expected.issubset(set(last_listing.splitlines())):
            return
        time.sleep(poll_interval_seconds)
    missing = ", ".join(sorted(expected.difference(set(last_listing.splitlines()))))
    raise RuntimeError(f"timed out waiting for JACK input ports: {missing}")


def connect_jack_ports(
    config: StreamerConfig,
    *,
    run_command: RunCommand = subprocess.run,
) -> None:
    """Connect configured source ports into the ffmpeg JACK client."""

    for command in build_jack_connect_commands(config):
        completed = run_command(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"jack_connect failed for {' '.join(command)}: {detail}")


def _terminate_process(process: StreamProcess) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def start_streamer(
    config: StreamerConfig,
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    run_command: RunCommand = subprocess.run,
    bootstrap_identity_fn: BootstrapIdentityFn = _bootstrap_identity,
) -> StreamProcess:
    """Start ffmpeg, connect JACK ports, and return the running process."""

    bootstrap_identity_fn(
        mode=config.identity_mode,
        release=config.identity_release,
        parent_id=config.identity_parent_id,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if config.pid_file is not None:
        config.pid_file.parent.mkdir(parents=True, exist_ok=True)

    process = popen_factory(
        build_ffmpeg_command(config),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_jack_inputs(config, process=process, run_command=run_command)
        connect_jack_ports(config, run_command=run_command)
    except Exception:
        _terminate_process(process)
        raise

    if config.pid_file is not None:
        config.pid_file.write_text(f"{process.pid}\n")
    return process


def probe_segment(
    path: Path,
    *,
    run_command: RunCommand = subprocess.run,
) -> SegmentProbe:
    """Read duration and bitrate for one media segment via ffprobe."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,bit_rate",
        "-of",
        "json",
        str(path),
    ]
    completed = run_command(
        command,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"ffprobe failed for {path}: {detail}")

    payload = json.loads(completed.stdout or "{}")
    media_format = payload.get("format")
    if not isinstance(media_format, dict):
        raise RuntimeError(f"ffprobe returned no format payload for {path}")
    try:
        duration_seconds = float(media_format["duration"])
        bitrate_bps = int(float(media_format["bit_rate"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"ffprobe returned invalid duration/bitrate for {path}") from exc
    return SegmentProbe(path=path, duration_seconds=duration_seconds, bitrate_bps=bitrate_bps)


def validate_segment_probe(
    probe: SegmentProbe,
    *,
    expected_duration_seconds: float = float(DEFAULT_SEGMENT_SECONDS),
    duration_tolerance_seconds: float = DEFAULT_DURATION_TOLERANCE_SECONDS,
    expected_bitrate_bps: int = DEFAULT_BITRATE_KBPS * 1000,
    bitrate_tolerance_ratio: float = DEFAULT_BITRATE_TOLERANCE_RATIO,
) -> SegmentValidation:
    """Validate one probed segment against duration and bitrate targets."""

    duration_delta = abs(probe.duration_seconds - expected_duration_seconds)
    bitrate_delta_ratio = abs(probe.bitrate_bps - expected_bitrate_bps) / float(expected_bitrate_bps)
    duration_ok = duration_delta <= duration_tolerance_seconds
    bitrate_ok = bitrate_delta_ratio <= bitrate_tolerance_ratio
    errors: list[str] = []
    if not duration_ok:
        errors.append(
            "duration "
            f"{probe.duration_seconds:.3f}s outside "
            f"{expected_duration_seconds:.3f}s +/- {duration_tolerance_seconds:.3f}s"
        )
    if not bitrate_ok:
        errors.append(
            "bitrate "
            f"{probe.bitrate_bps} bps outside "
            f"{expected_bitrate_bps} bps +/- {bitrate_tolerance_ratio:.0%}"
        )
    return SegmentValidation(
        path=probe.path,
        ok=duration_ok and bitrate_ok,
        duration_ok=duration_ok,
        bitrate_ok=bitrate_ok,
        duration_delta_seconds=duration_delta,
        bitrate_delta_ratio=bitrate_delta_ratio,
        errors=tuple(errors),
    )


def validate_segment_directory(
    directory: Path,
    *,
    expected_duration_seconds: float = float(DEFAULT_SEGMENT_SECONDS),
    duration_tolerance_seconds: float = DEFAULT_DURATION_TOLERANCE_SECONDS,
    expected_bitrate_bps: int = DEFAULT_BITRATE_KBPS * 1000,
    bitrate_tolerance_ratio: float = DEFAULT_BITRATE_TOLERANCE_RATIO,
    run_command: RunCommand = subprocess.run,
) -> tuple[SegmentValidation, ...]:
    segments = sorted(directory.glob("*.opus"))
    if not segments:
        raise RuntimeError(f"no .opus segments found in {directory}")
    validations: list[SegmentValidation] = []
    for segment in segments:
        probe = probe_segment(segment, run_command=run_command)
        validations.append(
            validate_segment_probe(
                probe,
                expected_duration_seconds=expected_duration_seconds,
                duration_tolerance_seconds=duration_tolerance_seconds,
                expected_bitrate_bps=expected_bitrate_bps,
                bitrate_tolerance_ratio=bitrate_tolerance_ratio,
            )
        )
    return tuple(validations)


def check_process_cpu(
    pid: int,
    *,
    max_cpu_percent: float = DEFAULT_MAX_CPU_PERCENT,
    run_command: RunCommand = subprocess.run,
) -> CpuCheck:
    """Return whether `pid` is currently under the configured CPU limit."""

    command = ["ps", "-p", str(pid), "-o", "%cpu="]
    completed = run_command(
        command,
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    errors: list[str] = []
    cpu_percent: float | None = None
    if completed.returncode != 0:
        errors.append("cpu check failed: ps returned nonzero")
    else:
        raw_cpu = (completed.stdout or "").strip().splitlines()
        if not raw_cpu:
            errors.append("cpu check failed: ps returned no cpu value")
        else:
            try:
                cpu_percent = float(raw_cpu[0].strip())
            except ValueError:
                errors.append(f"cpu check failed: unparsable cpu value {raw_cpu[0]!r}")
    if cpu_percent is not None and cpu_percent > max_cpu_percent:
        errors.append(f"cpu {cpu_percent:.1f}% exceeds {max_cpu_percent:.1f}%")
    return CpuCheck(
        pid=pid,
        ok=not errors,
        cpu_percent=cpu_percent,
        max_cpu_percent=max_cpu_percent,
        errors=tuple(errors),
    )


def _split_wrapper(raw: str) -> tuple[str, ...]:
    return tuple(part for part in raw.split() if part)


def _source_ports(values: list[str] | None) -> tuple[str, ...]:
    return tuple(values) if values else DEFAULT_SOURCE_PORTS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream JACK output to Opus segments")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--client-name", default=DEFAULT_CLIENT_NAME)
    parser.add_argument("--segment-seconds", type=int, default=DEFAULT_SEGMENT_SECONDS)
    parser.add_argument("--bitrate-kbps", type=int, default=DEFAULT_BITRATE_KBPS)
    parser.add_argument("--source-port", action="append", default=None)
    parser.add_argument("--jack-wrapper", default="")
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    parser.add_argument("--connect-timeout-seconds", type=float, default=DEFAULT_CONNECT_TIMEOUT_SECONDS)
    parser.add_argument("--verify-dir", type=Path)
    parser.add_argument("--check-cpu", type=int)
    parser.add_argument("--max-cpu", type=float, default=DEFAULT_MAX_CPU_PERCENT)
    parser.add_argument("--duration-tolerance", type=float, default=DEFAULT_DURATION_TOLERANCE_SECONDS)
    parser.add_argument("--bitrate-tolerance-ratio", type=float, default=DEFAULT_BITRATE_TOLERANCE_RATIO)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--identity-mode", choices=("standalone", "federated"), default="standalone")
    parser.add_argument("--identity-release", default="")
    parser.add_argument("--identity-parent-id")
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> StreamerConfig:
    return StreamerConfig(
        output_dir=args.output_dir,
        client_name=args.client_name,
        segment_seconds=args.segment_seconds,
        bitrate_kbps=args.bitrate_kbps,
        source_ports=_source_ports(args.source_port),
        jack_wrapper=_split_wrapper(args.jack_wrapper),
        pid_file=args.pid_file,
        connect_timeout_seconds=args.connect_timeout_seconds,
        identity_mode=args.identity_mode,
        identity_release=args.identity_release,
        identity_parent_id=args.identity_parent_id,
    )


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    # Ensure identity is bootstrapped on startup (before work or dry-run)
    _bootstrap_identity(
        mode=args.identity_mode,
        release=args.identity_release,
        parent_id=args.identity_parent_id,
    )

    if args.verify_dir is not None:
        validations = validate_segment_directory(
            args.verify_dir,
            expected_duration_seconds=float(args.segment_seconds),
            duration_tolerance_seconds=args.duration_tolerance,
            expected_bitrate_bps=args.bitrate_kbps * 1000,
            bitrate_tolerance_ratio=args.bitrate_tolerance_ratio,
        )
        payload = {
            "ok": all(validation.ok for validation in validations),
            "segments": [validation.to_dict() for validation in validations],
        }
        _print_json(payload)
        return 0 if payload["ok"] else 1

    if args.check_cpu is not None:
        check = check_process_cpu(args.check_cpu, max_cpu_percent=args.max_cpu)
        _print_json(check.to_dict())
        return 0 if check.ok else 1

    config = _config_from_args(args)
    if args.dry_run:
        _print_json(
            {
                "ffmpeg": build_ffmpeg_command(config),
                "jack_connect": build_jack_connect_commands(config),
                "output_dir": str(config.output_dir),
                "pid_file": str(config.pid_file) if config.pid_file else None,
            }
        )
        return 0

    process = start_streamer(config)
    try:
        while process.poll() is None:
            time.sleep(1.0)
    except KeyboardInterrupt:
        _terminate_process(process)
        return 130
    return process.wait()


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
