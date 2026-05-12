"""Audio export with integrated provenance capture.

Collects rule-stack context at export time and passes it to both the
iXML chunk writer (embedded in WAV) and the JSON sidecar writer.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ixml_chunk_writer import write_ixml
from .audio_sidecar import write_audio_metadata_sidecar
from .pass_ import PerformedPart


@dataclass(frozen=True)
class ExportResult:
    audio_path: Path
    sidecar_path: Path
    ixml_keys: dict[str, str]


def _provenance_to_ixml(
    performed_part: PerformedPart | None,
    rule_stack: Sequence[str] | None,
    rule_quantities: Mapping[str, float] | None,
) -> dict[str, str]:
    if performed_part is not None:
        applied = list(performed_part.applied_rules)
        quantities = performed_part.quantities
    else:
        applied = list(rule_stack or ())
        quantities = dict(rule_quantities or {})

    meta: dict[str, str] = {}
    if applied:
        meta["rule_stack"] = ",".join(applied)
    if quantities:
        meta["rule_quantities"] = json.dumps(
            {str(k): float(v) for k, v in quantities.items()},
            separators=(",", ":"),
            sort_keys=True,
        )
    return meta


def export_audio(
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
    ixml_extra: Mapping[str, str] | None = None,
) -> ExportResult:
    """Export provenance for an audio file to both iXML and JSON sidecar.

    The WAV at *audio_path* must already exist.  This function:
    1. Extracts rule-stack context from *performed_part* (or explicit params).
    2. Writes a JSON ``.meta.json`` sidecar via :func:`write_audio_metadata_sidecar`.
    3. Embeds rule-stack provenance as iXML metadata in the WAV via :func:`write_ixml`.

    Returns an :class:`ExportResult` with paths and the iXML keys that were written.
    """
    wav = Path(audio_path)

    sidecar_path = write_audio_metadata_sidecar(
        wav,
        performed_part=performed_part,
        rule_stack=rule_stack,
        rule_quantities=rule_quantities,
        rule_metadata=rule_metadata,
        events=events,
        performance_intents=performance_intents,
        section_envelopes=section_envelopes,
        seeds=seeds,
        delta_track=delta_track,
        delta_track_path=delta_track_path,
        extra_metadata=extra_metadata,
    )

    ixml_meta = _provenance_to_ixml(performed_part, rule_stack, rule_quantities)
    if ixml_extra:
        ixml_meta.update(ixml_extra)

    write_ixml(wav, ixml_meta)

    return ExportResult(
        audio_path=wav,
        sidecar_path=sidecar_path,
        ixml_keys=ixml_meta,
    )
