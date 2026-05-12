"""JSON sidecar writer for exported render audio."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .pass_ import PerformedPart

SCHEMA_VERSION = "render-audio-sidecar/v1"


def audio_metadata_sidecar_path(audio_path: str | Path) -> Path:
    """Return the default ``.meta.json`` sidecar path for an audio export."""
    path = Path(audio_path)
    if path.suffix:
        return path.with_suffix(".meta.json")
    return path.with_name(f"{path.name}.meta.json")


def audio_delta_track_path(audio_path: str | Path) -> Path:
    """Return the default ``.delta.json`` path for an audio export."""
    path = Path(audio_path)
    if path.suffix:
        return path.with_suffix(".delta.json")
    return path.with_name(f"{path.name}.delta.json")


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _provenance(
    *,
    performed_part: PerformedPart | None,
    rule_stack: Sequence[str] | None,
    rule_quantities: Mapping[str, float] | None,
    rule_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if performed_part is not None:
        applied_rules = list(performed_part.applied_rules)
        quantities = {str(key): float(value) for key, value in performed_part.quantities.items()}
        metadata = _json_safe(performed_part.metadata)
    else:
        applied_rules = [str(rule_id) for rule_id in (rule_stack or ())]
        quantities = {str(key): float(value) for key, value in dict(rule_quantities or {}).items()}
        metadata = _json_safe(rule_metadata or {})
    return {
        "applied_rules": applied_rules,
        "quantities": quantities,
        "metadata": metadata,
    }


def _event_payload(event: Any, fallback_rule_stack: Sequence[str]) -> dict[str, Any]:
    payload = _json_safe(event)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    if "rule_stack" not in payload:
        payload["rule_stack"] = list(fallback_rule_stack)
    else:
        rule_stack = payload["rule_stack"]
        if isinstance(rule_stack, str):
            payload["rule_stack"] = [rule_stack]
        else:
            payload["rule_stack"] = list(_json_safe(rule_stack))
    return payload


def write_audio_metadata_sidecar(
    audio_path: str | Path,
    *,
    performed_part: PerformedPart | None = None,
    rule_stack: Sequence[str] | None = None,
    rule_quantities: Mapping[str, float] | None = None,
    rule_metadata: Mapping[str, Any] | None = None,
    events: Sequence[Any] | None = None,
    performance_intents: Mapping[str, Any] | Sequence[Any] | None = None,
    section_envelopes: Mapping[str, Any] | Sequence[Any] | None = None,
    seeds: Mapping[str, int] | None = None,
    delta_track: Sequence[Any] | Mapping[str, Any] | None = None,
    delta_track_path: str | Path = "",
    extra_metadata: Mapping[str, Any] | None = None,
    sidecar_path: str | Path | None = None,
) -> Path:
    """Write a JSON sidecar preserving render rule-stack provenance."""
    audio = Path(audio_path)
    sidecar = Path(sidecar_path) if sidecar_path is not None else audio_metadata_sidecar_path(audio)
    delta_path = Path(delta_track_path) if delta_track_path else None
    if delta_track is not None:
        delta_path = delta_path or audio_delta_track_path(audio)
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        delta_tmp_path = delta_path.with_suffix(f"{delta_path.suffix}.tmp")
        delta_tmp_path.write_text(
            json.dumps(_json_safe(delta_track), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(delta_tmp_path, delta_path)
    provenance = _provenance(
        performed_part=performed_part,
        rule_stack=rule_stack,
        rule_quantities=rule_quantities,
        rule_metadata=rule_metadata,
    )
    applied_rules = list(provenance["applied_rules"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "audio_path": str(audio),
        "rule_stack": applied_rules,
        "rule_quantities": dict(provenance["quantities"]),
        "rule_stack_provenance": provenance,
        "events": [_event_payload(event, applied_rules) for event in (events or ())],
        "performance_intents": _json_safe(performance_intents or {}),
        "section_envelopes": _json_safe(section_envelopes or {}),
        "seeds": {str(key): int(value) for key, value in dict(seeds or {}).items()},
        "delta_track_path": str(delta_path) if delta_path is not None else "",
        "metadata": _json_safe(extra_metadata or {}),
    }

    sidecar.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = sidecar.with_suffix(f"{sidecar.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp_path, sidecar)
    return sidecar


def read_audio_metadata_sidecar(audio_path: str | Path) -> dict[str, Any]:
    """Read the default ``.meta.json`` sidecar for an audio export."""
    path = Path(audio_path)
    sidecar = path if path.name.endswith(".meta.json") else audio_metadata_sidecar_path(path)
    return dict(json.loads(sidecar.read_text()))
