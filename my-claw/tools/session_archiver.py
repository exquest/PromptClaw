"""Build CypherClaw public archive sessions from live Opus segments."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Literal, Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

try:
    from cypherclaw.first_boot import bootstrap_identity as _bootstrap_identity
except ImportError:  # pragma: no cover - runtime fallback for copied tool trees
    try:
        from first_boot import bootstrap_identity as _bootstrap_identity
    except ImportError:  # pragma: no cover - defensive fallback

        def _bootstrap_identity(**_kwargs: object) -> object:
            return None


IdentityMode = Literal["standalone", "federated"]
DEFAULT_SEGMENT_DIR = Path("/home/user/cypherclaw-data/streams")
DEFAULT_STATE_PATH = DEFAULT_SEGMENT_DIR / "session_archiver_state.json"
DEFAULT_ARCHIVE_PREFIX = "cypherclaw/archive"
DEFAULT_SESSION_SECONDS = 8 * 60
DEFAULT_SEGMENT_SECONDS = 6.0
DEFAULT_MAX_GAP_SECONDS = 120.0
DEFAULT_POLL_SECONDS = 30.0
DEFAULT_CONTENT_TYPE = "audio/ogg; codecs=opus"
METADATA_CONTENT_TYPE = "application/json"

HOUSE_IMAGERY = {
    "house_monastery": "Monastery-Stone",
    "monastery": "Monastery-Stone",
    "house_chamber": "Chamber-Glass",
    "chamber": "Chamber-Glass",
    "house_garden": "Garden-Dusk",
    "garden": "Garden-Dusk",
    "house_procession": "Procession-Road",
    "procession": "Procession-Road",
    "house_workshop": "Workshop-Circuit",
    "workshop": "Workshop-Circuit",
}

TUNING_CHARACTER = {
    "slendro": "Slendro-Drift",
    "gamelan_slendro": "Slendro-Drift",
    "gamelan-slendro": "Slendro-Drift",
    "just": "Just-Choir",
    "just_intonation": "Just-Choir",
    "just_intonation_5_limit": "Just-Choir",
    "5-limit-ji": "Just-Choir",
    "ji": "Just-Choir",
    "twelve_tet": "Equal-Grid",
    "12-tet": "Equal-Grid",
    "equal_temperament": "Equal-Grid",
}

BootstrapIdentityFn = Callable[..., object]


class R2ArchiveClient(Protocol):
    """Small upload surface used by the archiver and tests."""

    def put_object(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> object:
        ...


@dataclass(frozen=True)
class ArchiveConfig:
    segment_dir: Path = DEFAULT_SEGMENT_DIR
    state_path: Path = DEFAULT_STATE_PATH
    archive_prefix: str = DEFAULT_ARCHIVE_PREFIX
    min_session_seconds: float = float(DEFAULT_SESSION_SECONDS)
    default_segment_seconds: float = DEFAULT_SEGMENT_SECONDS
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS
    identity_mode: IdentityMode = "standalone"
    identity_release: str = ""
    identity_parent_id: str | None = None
    identity_path: Path | None = None


@dataclass(frozen=True)
class SegmentRecord:
    path: Path
    captured_at: datetime
    duration_seconds: float
    sequence: int | None
    scene: str
    patch_name: str
    tuning: str
    rms: float | None = None
    midi_fragments: tuple[str, ...] = ()

    @property
    def ended_at(self) -> datetime:
        return self.captured_at + timedelta(seconds=self.duration_seconds)


@dataclass(frozen=True)
class SessionArchive:
    session_id: str
    title: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    dominant_house: str
    primary_tuning: str
    segment_count: int
    audio_key: str
    metadata_key: str
    source_segment_paths: tuple[str, ...]
    scenes: tuple[str, ...]
    midi_fragments: tuple[str, ...]

    def to_metadata(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "started_at": _format_datetime(self.started_at),
            "ended_at": _format_datetime(self.ended_at),
            "duration_seconds": round(self.duration_seconds, 3),
            "dominant_house": self.dominant_house,
            "primary_tuning": self.primary_tuning,
            "segment_count": self.segment_count,
            "audio_key": self.audio_key,
            "metadata_key": self.metadata_key,
            "source_segment_paths": list(self.source_segment_paths),
            "scenes": list(self.scenes),
            "midi_fragments": list(self.midi_fragments),
        }

    def object_metadata(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "started_at": _format_datetime(self.started_at),
            "ended_at": _format_datetime(self.ended_at),
            "duration_seconds": f"{self.duration_seconds:.3f}",
            "dominant_house": self.dominant_house,
            "primary_tuning": self.primary_tuning,
            "segment_count": str(self.segment_count),
        }


@dataclass(frozen=True)
class R2ClientConfig:
    account_id: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str | None = None

    @classmethod
    def from_env(cls) -> R2ClientConfig:
        account_id = os.environ.get("CYPHERCLAW_R2_ACCOUNT_ID") or os.environ.get("R2_ACCOUNT_ID")
        bucket = os.environ.get("CYPHERCLAW_R2_BUCKET") or os.environ.get("R2_BUCKET")
        access_key_id = os.environ.get("CYPHERCLAW_R2_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY_ID")
        secret_access_key = os.environ.get("CYPHERCLAW_R2_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_ACCESS_KEY")
        missing = [
            name
            for name, value in (
                ("CYPHERCLAW_R2_ACCOUNT_ID", account_id),
                ("CYPHERCLAW_R2_BUCKET", bucket),
                ("CYPHERCLAW_R2_ACCESS_KEY_ID", access_key_id),
                ("CYPHERCLAW_R2_SECRET_ACCESS_KEY", secret_access_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"missing R2 configuration: {', '.join(missing)}")
        return cls(
            account_id=str(account_id),
            bucket=str(bucket),
            access_key_id=str(access_key_id),
            secret_access_key=str(secret_access_key),
            endpoint_url=os.environ.get("CYPHERCLAW_R2_ENDPOINT_URL") or None,
        )


class S3CompatibleR2Client:
    """Minimal Cloudflare R2 S3-compatible PUT client using SigV4."""

    def __init__(self, config: R2ClientConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> S3CompatibleR2Client:
        return cls(R2ClientConfig.from_env())

    def put_object(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> dict[str, object]:
        endpoint = self.config.endpoint_url or (
            f"https://{self.config.account_id}.r2.cloudflarestorage.com"
        )
        url = f"{endpoint.rstrip('/')}/{quote(self.config.bucket)}/{_quote_key(key)}"
        headers = _sign_put_request(
            url=url,
            body=body,
            content_type=content_type,
            metadata=metadata,
            access_key_id=self.config.access_key_id,
            secret_access_key=self.config.secret_access_key,
        )
        request = Request(url, data=body, method="PUT", headers=headers)
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                return {"status": response.status, "key": key}
        except HTTPError as exc:  # pragma: no cover - live R2 failure path
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"R2 upload failed for {key}: {exc.code} {detail}") from exc


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp_from_filename(path: Path) -> datetime | None:
    match = re.search(r"(\d{8}T\d{6})", path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _sequence_from_path(path: Path, sidecar: Mapping[str, object]) -> int | None:
    raw_sequence = sidecar.get("sequence")
    if isinstance(raw_sequence, int):
        return raw_sequence
    if isinstance(raw_sequence, str) and raw_sequence.isdigit():
        return int(raw_sequence)
    match = re.search(r"seg[-_]?(\d+)", path.stem)
    return int(match.group(1)) if match else None


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: object, fallback: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if result > 0 else fallback


def _string_from_fields(
    payload: Mapping[str, object],
    names: Sequence[str],
    fallback: str,
) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _string_list(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def discover_segments(
    segment_dir: Path,
    *,
    default_duration_seconds: float = DEFAULT_SEGMENT_SECONDS,
) -> tuple[SegmentRecord, ...]:
    """Read complete local `.opus` segments and optional JSON sidecars."""

    records: list[SegmentRecord] = []
    for path in sorted(segment_dir.glob("*.opus")):
        sidecar = _load_json(path.with_suffix(".json"))
        captured_at = (
            _parse_datetime(sidecar.get("captured_at"))
            or _parse_datetime(sidecar.get("start_time"))
            or _timestamp_from_filename(path)
            or datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        )
        duration = _number(
            sidecar.get("duration_seconds", sidecar.get("duration")),
            default_duration_seconds,
        )
        rms_value = sidecar.get("rms")
        rms = float(rms_value) if isinstance(rms_value, int | float) else None
        records.append(
            SegmentRecord(
                path=path,
                captured_at=captured_at,
                duration_seconds=duration,
                sequence=_sequence_from_path(path, sidecar),
                scene=_string_from_fields(sidecar, ("scene", "scene_name"), ""),
                patch_name=_string_from_fields(
                    sidecar,
                    ("dominant_house", "house", "patch_name", "instrument_patch"),
                    "house_chamber",
                ),
                tuning=_string_from_fields(
                    sidecar,
                    ("primary_tuning", "tuning", "tuning_system_name"),
                    "unknown",
                ),
                rms=rms,
                midi_fragments=_string_list(sidecar.get("midi_fragments")),
            )
        )
    return tuple(sorted(records, key=lambda item: (item.captured_at, item.sequence or -1)))


def _dominant_by_duration(
    records: Sequence[SegmentRecord],
    accessor: Callable[[SegmentRecord], str],
    fallback: str,
) -> str:
    totals: defaultdict[str, float] = defaultdict(float)
    order: list[str] = []
    for record in records:
        value = accessor(record).strip() or fallback
        if value not in totals:
            order.append(value)
        totals[value] += record.duration_seconds
    if not totals:
        return fallback
    return max(order, key=lambda value: (totals[value], -order.index(value)))


def _normalize_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def build_session_title(
    *,
    dominant_house: str,
    primary_tuning: str,
    date: datetime,
) -> str:
    """Return CypherClaw's `{House} / {Tuning} — {DD Month}` title."""

    house = HOUSE_IMAGERY.get(_normalize_token(dominant_house), "Room-Drift")
    tuning = TUNING_CHARACTER.get(_normalize_token(primary_tuning), "Tuning-Unknown")
    return f"{house} / {tuning} — {date.astimezone(UTC):%d %B}"


def _session_id(started_at: datetime) -> str:
    return f"session-{started_at.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _archive_keys(config: ArchiveConfig, session_id: str) -> tuple[str, str]:
    prefix = config.archive_prefix.strip("/")
    return (
        f"{prefix}/{session_id}/session.opus",
        f"{prefix}/{session_id}/metadata.json",
    )


def _build_session(records: Sequence[SegmentRecord], config: ArchiveConfig) -> SessionArchive:
    first = records[0]
    last = records[-1]
    duration_seconds = sum(record.duration_seconds for record in records)
    dominant_house = _dominant_by_duration(records, lambda record: record.patch_name, "house_chamber")
    primary_tuning = _dominant_by_duration(records, lambda record: record.tuning, "unknown")
    session_id = _session_id(first.captured_at)
    audio_key, metadata_key = _archive_keys(config, session_id)
    scenes = tuple(dict.fromkeys(record.scene for record in records if record.scene))
    midi_fragments = tuple(
        dict.fromkeys(fragment for record in records for fragment in record.midi_fragments)
    )
    return SessionArchive(
        session_id=session_id,
        title=build_session_title(
            dominant_house=dominant_house,
            primary_tuning=primary_tuning,
            date=first.captured_at,
        ),
        started_at=first.captured_at,
        ended_at=last.ended_at,
        duration_seconds=duration_seconds,
        dominant_house=dominant_house,
        primary_tuning=primary_tuning,
        segment_count=len(records),
        audio_key=audio_key,
        metadata_key=metadata_key,
        source_segment_paths=tuple(str(record.path) for record in records),
        scenes=scenes,
        midi_fragments=midi_fragments,
    )


def _complete_before(records: Sequence[SegmentRecord], now: datetime) -> tuple[SegmentRecord, ...]:
    return tuple(record for record in records if record.ended_at <= now)


def plan_sessions(
    records: Sequence[SegmentRecord],
    config: ArchiveConfig,
    *,
    now: datetime,
    archived_session_ids: set[str] | None = None,
) -> tuple[SessionArchive, ...]:
    """Plan complete, not-yet-archived session windows."""

    archived = archived_session_ids or set()
    eligible = _complete_before(records, now.astimezone(UTC))
    sessions: list[SessionArchive] = []
    window: list[SegmentRecord] = []
    accumulated = 0.0
    last_end: datetime | None = None

    for record in eligible:
        if last_end is not None:
            gap = (record.captured_at - last_end).total_seconds()
            if gap > config.max_gap_seconds:
                window = []
                accumulated = 0.0

        window.append(record)
        accumulated += record.duration_seconds
        last_end = record.ended_at

        if accumulated >= config.min_session_seconds:
            session = _build_session(window, config)
            if session.session_id not in archived:
                sessions.append(session)
            window = []
            accumulated = 0.0
            last_end = None

    return tuple(sessions)


def _load_state(path: Path) -> list[str]:
    payload = _load_json(path)
    raw_ids = payload.get("archived_session_ids")
    if not isinstance(raw_ids, list):
        return []
    return [str(item) for item in raw_ids if str(item).strip()]


def _save_state(path: Path, archived_session_ids: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "archived_session_ids": list(dict.fromkeys(archived_session_ids)),
        "updated_at": _format_datetime(datetime.now(tz=UTC)),
    }
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _concat_segments(records: Sequence[SegmentRecord]) -> bytes:
    chunks: list[bytes] = []
    for record in records:
        chunks.append(record.path.read_bytes())
    return b"".join(chunks)


def _records_for_session(
    records: Sequence[SegmentRecord],
    session: SessionArchive,
) -> tuple[SegmentRecord, ...]:
    wanted = set(session.source_segment_paths)
    return tuple(record for record in records if str(record.path) in wanted)


def _bootstrap_startup(
    config: ArchiveConfig,
    bootstrap_identity_fn: BootstrapIdentityFn,
) -> None:
    kwargs: dict[str, object] = {
        "mode": config.identity_mode,
        "release": config.identity_release,
        "parent_id": config.identity_parent_id,
    }
    if config.identity_path is not None:
        kwargs["identity_path"] = config.identity_path
    bootstrap_identity_fn(**kwargs)


def archive_due_sessions(
    config: ArchiveConfig,
    client: R2ArchiveClient,
    *,
    now: datetime | None = None,
    bootstrap_identity_fn: BootstrapIdentityFn = _bootstrap_identity,
) -> list[SessionArchive]:
    """Archive all complete session windows that have not been uploaded."""

    _bootstrap_startup(config, bootstrap_identity_fn)
    now = now or datetime.now(tz=UTC)
    records = discover_segments(
        config.segment_dir,
        default_duration_seconds=config.default_segment_seconds,
    )
    archived_ids = _load_state(config.state_path)
    planned = plan_sessions(
        records,
        config,
        now=now,
        archived_session_ids=set(archived_ids),
    )
    archived_now: list[SessionArchive] = []
    for session in planned:
        session_records = _records_for_session(records, session)
        audio_body = _concat_segments(session_records)
        metadata_body = json.dumps(
            session.to_metadata(),
            indent=2,
            sort_keys=True,
        ).encode()
        client.put_object(
            key=session.audio_key,
            body=audio_body,
            content_type=DEFAULT_CONTENT_TYPE,
            metadata=session.object_metadata(),
        )
        client.put_object(
            key=session.metadata_key,
            body=metadata_body,
            content_type=METADATA_CONTENT_TYPE,
            metadata=session.object_metadata(),
        )
        archived_ids.append(session.session_id)
        _save_state(config.state_path, archived_ids)
        archived_now.append(session)
    return archived_now


def run_once(
    config: ArchiveConfig,
    client: R2ArchiveClient,
    *,
    now: datetime | None = None,
    bootstrap_identity_fn: BootstrapIdentityFn = _bootstrap_identity,
) -> list[SessionArchive]:
    """Run one archiver pass."""

    return archive_due_sessions(
        config,
        client,
        now=now,
        bootstrap_identity_fn=bootstrap_identity_fn,
    )


def _quote_key(key: str) -> str:
    return "/".join(quote(part, safe="") for part in key.split("/"))


def _sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _signing_key(secret_access_key: str, date_stamp: str) -> bytes:
    key_date = hmac.new(f"AWS4{secret_access_key}".encode(), date_stamp.encode(), hashlib.sha256).digest()
    key_region = hmac.new(key_date, b"auto", hashlib.sha256).digest()
    key_service = hmac.new(key_region, b"s3", hashlib.sha256).digest()
    return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


def _metadata_headers(metadata: Mapping[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in metadata.items():
        safe_key = re.sub(r"[^a-z0-9-]", "-", key.lower()).strip("-")
        if not safe_key:
            continue
        headers[f"x-amz-meta-{safe_key}"] = quote(value, safe="")
    return headers


def _canonical_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    normalized = {
        key.lower(): " ".join(value.strip().split())
        for key, value in headers.items()
    }
    names = sorted(normalized)
    canonical = "".join(f"{name}:{normalized[name]}\n" for name in names)
    return canonical, ";".join(names)


def _sign_put_request(
    *,
    url: str,
    body: bytes,
    content_type: str,
    metadata: Mapping[str, str],
    access_key_id: str,
    secret_access_key: str,
) -> dict[str, str]:
    parsed = urlparse(url)
    now = datetime.now(tz=UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = _sha256_hex(body)
    headers = {
        "host": parsed.netloc,
        "content-type": content_type,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        **_metadata_headers(metadata),
    }
    canonical_headers, signed_headers = _canonical_headers(headers)
    canonical_uri = parsed.path or "/"
    canonical_request = "\n".join(
        (
            "PUT",
            canonical_uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        )
    )
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join(
        (
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode()),
        )
    )
    signature = hmac.new(
        _signing_key(secret_access_key, date_stamp),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return {
        "Content-Type": content_type,
        "Authorization": authorization,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        **{key: value for key, value in headers.items() if key.startswith("x-amz-meta-")},
    }


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive CypherClaw Opus sessions to R2")
    parser.add_argument("--segment-dir", type=Path, default=DEFAULT_SEGMENT_DIR)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--archive-prefix", default=DEFAULT_ARCHIVE_PREFIX)
    parser.add_argument("--min-session-seconds", type=float, default=float(DEFAULT_SESSION_SECONDS))
    parser.add_argument("--default-segment-seconds", type=float, default=DEFAULT_SEGMENT_SECONDS)
    parser.add_argument("--max-gap-seconds", type=float, default=DEFAULT_MAX_GAP_SECONDS)
    parser.add_argument("--identity-mode", choices=("standalone", "federated"), default="standalone")
    parser.add_argument("--identity-release", default="")
    parser.add_argument("--identity-parent-id")
    parser.add_argument("--identity-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> ArchiveConfig:
    return ArchiveConfig(
        segment_dir=args.segment_dir,
        state_path=args.state_path,
        archive_prefix=args.archive_prefix,
        min_session_seconds=args.min_session_seconds,
        default_segment_seconds=args.default_segment_seconds,
        max_gap_seconds=args.max_gap_seconds,
        identity_mode=args.identity_mode,
        identity_release=args.identity_release,
        identity_parent_id=args.identity_parent_id,
        identity_path=args.identity_path,
    )


def _dry_run(config: ArchiveConfig) -> int:
    _bootstrap_startup(config, _bootstrap_identity)
    records = discover_segments(
        config.segment_dir,
        default_duration_seconds=config.default_segment_seconds,
    )
    sessions = plan_sessions(
        records,
        config,
        now=datetime.now(tz=UTC),
        archived_session_ids=set(_load_state(config.state_path)),
    )
    _print_json(
        {
            "ok": True,
            "planned_sessions": [session.to_metadata() for session in sessions],
            "segment_count": len(records),
        }
    )
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = _config_from_args(args)
    if args.dry_run:
        return _dry_run(config)

    client = S3CompatibleR2Client.from_env()
    while True:
        sessions = run_once(config, client)
        _print_json(
            {
                "ok": True,
                "archived_sessions": [session.to_metadata() for session in sessions],
            }
        )
        if not args.loop:
            return 0
        time.sleep(args.poll_seconds)


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
