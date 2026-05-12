"""Runtime-safe voice aliases for CypherClaw playback.

This keeps the musical role metadata intact while allowing the live runtime
to substitute safer or available voices when a SynthDef is known to leak or
is missing from the deployed bundle.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

RUNTIME_VOICE_ALIAS: dict[str, str] = {
    "gong": "bowed",
    "sw_gong": "sw_bowed",
    "bell": "bowed",
    "sw_bell": "sw_bowed",
    "sw_bell_warm": "sw_bowed",
    "metal": "choir",
    "sw_metal": "sw_choir",
    "grain": "breath",
    "sw_grain": "sw_breath",
    "tabla_ge": "tabla_tin",
    "sw_tabla_ge": "sw_tabla_tin",
}

_SENSEWEAVE_PREFIX = "sw_"

_FAMILY_BY_CANONICAL: dict[str, str] = {
    "gong": "struck_tonal",
    "bell": "struck_tonal",
    "bell_warm": "struck_tonal",
    "metal": "metallic",
    "grain": "granular",
    "tabla_ge": "drum",
}


def resolve_runtime_voice_name(voice_name: str) -> str:
    """Map a requested voice to the runtime-safe playback voice."""

    return RUNTIME_VOICE_ALIAS.get(voice_name, voice_name)


def voice_namespace(voice_name: str) -> str:
    """Return the namespace band for a voice name."""

    if voice_name.startswith(_SENSEWEAVE_PREFIX):
        return "senseweave"
    return "core"


def voice_alias_family(voice_name: str) -> str:
    """Return the canonical alias family band for a voice name."""

    canonical = voice_name
    if canonical.startswith(_SENSEWEAVE_PREFIX):
        canonical = canonical[len(_SENSEWEAVE_PREFIX):]
    return _FAMILY_BY_CANONICAL.get(canonical, "other")


def is_aliased_voice(voice_name: str) -> bool:
    """Return True when the voice name has a registered runtime alias."""

    return voice_name in RUNTIME_VOICE_ALIAS


def iter_alias_pairs() -> Iterator[tuple[str, str]]:
    """Yield ``(source, target)`` alias pairs in declaration order."""

    for source, target in RUNTIME_VOICE_ALIAS.items():
        yield source, target


def aliases_for_target(target: str) -> tuple[str, ...]:
    """Return the source voices whose alias resolves to ``target``."""

    sources: list[str] = []
    for source, mapped in RUNTIME_VOICE_ALIAS.items():
        if mapped == target:
            sources.append(source)
    return tuple(sources)


def alias_chain(voice_name: str) -> tuple[str, ...]:
    """Return the resolved alias chain starting from ``voice_name``."""

    chain: list[str] = [voice_name]
    seen: set[str] = {voice_name}
    current = voice_name
    while current in RUNTIME_VOICE_ALIAS:
        nxt = RUNTIME_VOICE_ALIAS[current]
        if nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
        current = nxt
    return tuple(chain)


@dataclass(frozen=True)
class VoiceAliasEntry:
    """Resolved diagnostic view for one alias entry."""

    source: str
    target: str
    namespace: str
    family: str
    is_senseweave_variant: bool
    is_changed: bool


@dataclass(frozen=True)
class VoiceAliasReport:
    """Resolved diagnostic view for the full alias table."""

    total_aliases: int
    source_voices: tuple[str, ...]
    target_voices: tuple[str, ...]
    namespace_counts: dict[str, int]
    family_counts: dict[str, int]
    senseweave_variant_count: int
    core_alias_count: int
    unique_target_count: int
    target_to_sources: dict[str, tuple[str, ...]]
    entries: tuple[VoiceAliasEntry, ...]


def build_voice_alias_entry(source: str, target: str) -> VoiceAliasEntry:
    """Resolve a single alias pair into a frozen diagnostic record."""

    return VoiceAliasEntry(
        source=source,
        target=target,
        namespace=voice_namespace(source),
        family=voice_alias_family(source),
        is_senseweave_variant=source.startswith(_SENSEWEAVE_PREFIX),
        is_changed=source != target,
    )


def build_voice_alias_report() -> VoiceAliasReport:
    """Resolve the full alias table into a frozen diagnostic report."""

    entries: list[VoiceAliasEntry] = []
    namespace_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    target_to_sources: dict[str, list[str]] = {}
    senseweave_variant_count = 0
    core_alias_count = 0

    for source, target in RUNTIME_VOICE_ALIAS.items():
        entry = build_voice_alias_entry(source, target)
        entries.append(entry)
        namespace_counts[entry.namespace] = namespace_counts.get(entry.namespace, 0) + 1
        family_counts[entry.family] = family_counts.get(entry.family, 0) + 1
        target_to_sources.setdefault(target, []).append(source)
        if entry.is_senseweave_variant:
            senseweave_variant_count += 1
        else:
            core_alias_count += 1

    target_to_sources_tuple = {
        target: tuple(sources) for target, sources in target_to_sources.items()
    }

    return VoiceAliasReport(
        total_aliases=len(RUNTIME_VOICE_ALIAS),
        source_voices=tuple(RUNTIME_VOICE_ALIAS.keys()),
        target_voices=tuple(RUNTIME_VOICE_ALIAS.values()),
        namespace_counts=namespace_counts,
        family_counts=family_counts,
        senseweave_variant_count=senseweave_variant_count,
        core_alias_count=core_alias_count,
        unique_target_count=len(target_to_sources_tuple),
        target_to_sources=target_to_sources_tuple,
        entries=tuple(entries),
    )


def summarize_voice_alias_report(report: VoiceAliasReport) -> dict[str, Any]:
    """Return a JSON-safe operator summary of a voice alias report."""

    return {
        "total_aliases": report.total_aliases,
        "source_voices": list(report.source_voices),
        "target_voices": list(report.target_voices),
        "namespace_counts": dict(report.namespace_counts),
        "family_counts": dict(report.family_counts),
        "senseweave_variant_count": report.senseweave_variant_count,
        "core_alias_count": report.core_alias_count,
        "unique_target_count": report.unique_target_count,
        "target_to_sources": {
            target: list(sources) for target, sources in report.target_to_sources.items()
        },
        "entries": [
            {
                "source": entry.source,
                "target": entry.target,
                "namespace": entry.namespace,
                "family": entry.family,
                "is_senseweave_variant": entry.is_senseweave_variant,
                "is_changed": entry.is_changed,
            }
            for entry in report.entries
        ],
    }
