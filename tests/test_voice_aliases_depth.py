"""Depth-2 voice_aliases report helpers - locked test surface for frac-0032."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.voice_aliases import (  # noqa: E402
    RUNTIME_VOICE_ALIAS,
    VoiceAliasEntry,
    VoiceAliasReport,
    alias_chain,
    aliases_for_target,
    build_voice_alias_entry,
    build_voice_alias_report,
    is_aliased_voice,
    iter_alias_pairs,
    resolve_runtime_voice_name,
    summarize_voice_alias_report,
    voice_alias_family,
    voice_namespace,
)


def _assert_json_safe(value: Any) -> None:
    assert not isinstance(value, tuple), f"tuple leaked into JSON summary: {value!r}"
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_json_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_json_safe(child)


def test_voice_alias_helpers_are_stable() -> None:
    assert voice_namespace("gong") == "core"
    assert voice_namespace("sw_gong") == "senseweave"
    assert voice_namespace("") == "core"
    assert voice_namespace("bowed") == "core"

    assert voice_alias_family("gong") == "struck_tonal"
    assert voice_alias_family("bell") == "struck_tonal"
    assert voice_alias_family("sw_gong") == "struck_tonal"
    assert voice_alias_family("metal") == "metallic"
    assert voice_alias_family("sw_metal") == "metallic"
    assert voice_alias_family("grain") == "granular"
    assert voice_alias_family("sw_grain") == "granular"
    assert voice_alias_family("tabla_ge") == "drum"
    assert voice_alias_family("sw_tabla_ge") == "drum"
    assert voice_alias_family("bowed") == "other"
    assert voice_alias_family("unknown_voice") == "other"

    assert is_aliased_voice("gong") is True
    assert is_aliased_voice("sw_grain") is True
    assert is_aliased_voice("bowed") is False
    assert is_aliased_voice("never_seen") is False

    pairs = tuple(iter_alias_pairs())
    assert pairs == tuple(RUNTIME_VOICE_ALIAS.items())
    assert pairs[0] == ("gong", "bowed")

    assert aliases_for_target("bowed") == ("gong", "bell")
    assert aliases_for_target("sw_bowed") == ("sw_gong", "sw_bell", "sw_bell_warm")
    assert aliases_for_target("choir") == ("metal",)
    assert aliases_for_target("nonexistent_target") == ()

    assert alias_chain("gong") == ("gong", "bowed")
    assert alias_chain("sw_bell_warm") == ("sw_bell_warm", "sw_bowed")
    assert alias_chain("bowed") == ("bowed",)
    assert alias_chain("never_seen") == ("never_seen",)


def test_build_voice_alias_entry_resolves_alias_diagnostics() -> None:
    entry = build_voice_alias_entry("sw_grain", "sw_breath")

    assert isinstance(entry, VoiceAliasEntry)
    assert dataclasses.is_dataclass(entry)
    assert getattr(entry, "__dataclass_params__").frozen

    assert entry.source == "sw_grain"
    assert entry.target == "sw_breath"
    assert entry.namespace == "senseweave"
    assert entry.family == "granular"
    assert entry.is_senseweave_variant is True
    assert entry.is_changed is True

    core_entry = build_voice_alias_entry("gong", "bowed")
    assert core_entry.namespace == "core"
    assert core_entry.family == "struck_tonal"
    assert core_entry.is_senseweave_variant is False
    assert core_entry.is_changed is True


def test_build_voice_alias_report_resolves_full_table() -> None:
    report = build_voice_alias_report()

    assert isinstance(report, VoiceAliasReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen

    assert report.total_aliases == len(RUNTIME_VOICE_ALIAS)
    assert report.source_voices == tuple(RUNTIME_VOICE_ALIAS.keys())
    assert report.source_voices == (
        "gong",
        "sw_gong",
        "bell",
        "sw_bell",
        "sw_bell_warm",
        "metal",
        "sw_metal",
        "grain",
        "sw_grain",
        "tabla_ge",
        "sw_tabla_ge",
    )
    assert report.target_voices == tuple(RUNTIME_VOICE_ALIAS.values())

    assert report.namespace_counts == {"core": 5, "senseweave": 6}
    assert report.family_counts == {
        "struck_tonal": 5,
        "metallic": 2,
        "granular": 2,
        "drum": 2,
    }
    assert report.senseweave_variant_count == 6
    assert report.core_alias_count == 5
    assert report.unique_target_count == len(set(RUNTIME_VOICE_ALIAS.values()))
    assert report.unique_target_count == 8

    assert report.target_to_sources == {
        "bowed": ("gong", "bell"),
        "sw_bowed": ("sw_gong", "sw_bell", "sw_bell_warm"),
        "choir": ("metal",),
        "sw_choir": ("sw_metal",),
        "breath": ("grain",),
        "sw_breath": ("sw_grain",),
        "tabla_tin": ("tabla_ge",),
        "sw_tabla_tin": ("sw_tabla_ge",),
    }

    assert len(report.entries) == report.total_aliases
    assert tuple(entry.source for entry in report.entries) == report.source_voices
    for entry in report.entries:
        assert isinstance(entry, VoiceAliasEntry)
        assert entry.is_changed is True


def test_summarize_voice_alias_report_returns_json_safe_summary() -> None:
    report = build_voice_alias_report()
    summary = summarize_voice_alias_report(report)

    assert summary["total_aliases"] == report.total_aliases
    assert summary["source_voices"] == list(report.source_voices)
    assert summary["target_voices"] == list(report.target_voices)
    assert summary["namespace_counts"] == dict(report.namespace_counts)
    assert summary["family_counts"] == dict(report.family_counts)
    assert summary["senseweave_variant_count"] == report.senseweave_variant_count
    assert summary["core_alias_count"] == report.core_alias_count
    assert summary["unique_target_count"] == report.unique_target_count
    assert summary["target_to_sources"] == {
        target: list(sources) for target, sources in report.target_to_sources.items()
    }

    assert isinstance(summary["entries"], list)
    assert len(summary["entries"]) == len(report.entries)
    first = summary["entries"][0]
    first_entry = report.entries[0]
    assert first["source"] == first_entry.source  # type: ignore[index]
    assert first["target"] == first_entry.target  # type: ignore[index]
    assert first["namespace"] == first_entry.namespace  # type: ignore[index]
    assert first["family"] == first_entry.family  # type: ignore[index]
    assert first["is_senseweave_variant"] == first_entry.is_senseweave_variant  # type: ignore[index]
    assert first["is_changed"] == first_entry.is_changed  # type: ignore[index]

    _assert_json_safe(summary)
    encoded = json.dumps(summary)
    decoded = json.loads(encoded)
    assert decoded["total_aliases"] == report.total_aliases


def test_voice_alias_report_agrees_with_existing_lookups() -> None:
    report = build_voice_alias_report()

    for entry in report.entries:
        assert resolve_runtime_voice_name(entry.source) == entry.target
        assert is_aliased_voice(entry.source) is True

    for source, target in iter_alias_pairs():
        assert resolve_runtime_voice_name(source) == target
        chain = alias_chain(source)
        assert chain[0] == source
        assert chain[-1] == target

    for target, sources in report.target_to_sources.items():
        assert sources == aliases_for_target(target)
        for source in sources:
            assert resolve_runtime_voice_name(source) == target

    assert resolve_runtime_voice_name("never_seen") == "never_seen"
    assert is_aliased_voice("never_seen") is False


def test_voice_aliases_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/voice_aliases.py")
    assert result.depth >= 2, result.reason
