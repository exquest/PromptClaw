"""Tests for runtime-safe voice aliases.

depth: 2
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.voice_aliases import (
    RUNTIME_VOICE_ALIAS,
    alias_chain,
    aliases_for_target,
    build_voice_alias_report,
    resolve_runtime_voice_name,
    summarize_voice_alias_report,
)


def test_resolve_runtime_voice_name_quarantines_grain() -> None:
    assert resolve_runtime_voice_name("grain") == "breath"


def test_resolve_runtime_voice_name_maps_missing_tabla_ge_to_tabla_tin() -> None:
    assert resolve_runtime_voice_name("tabla_ge") == "tabla_tin"
    assert resolve_runtime_voice_name("sw_tabla_ge") == "sw_tabla_tin"


def test_resolve_runtime_voice_name_maps_gong_to_tuned_bowed_voice() -> None:
    assert resolve_runtime_voice_name("gong") == "bowed"
    assert resolve_runtime_voice_name("sw_gong") == "sw_bowed"


def test_resolve_runtime_voice_name_retires_bell_to_tuned_bowed_voice() -> None:
    assert resolve_runtime_voice_name("bell") == "bowed"
    assert resolve_runtime_voice_name("sw_bell") == "sw_bowed"
    assert resolve_runtime_voice_name("sw_bell_warm") == "sw_bowed"


def test_resolve_runtime_voice_name_retires_metal_to_choir() -> None:
    assert resolve_runtime_voice_name("metal") == "choir"
    assert resolve_runtime_voice_name("sw_metal") == "sw_choir"


def test_resolve_runtime_voice_name_preserves_normal_voice() -> None:
    assert resolve_runtime_voice_name("bowed") == "bowed"


def test_resolve_runtime_voice_name_maps_raw_grain_synth_to_breath_synth() -> None:
    assert resolve_runtime_voice_name("sw_grain") == "sw_breath"


class VoiceAliasesEndToEndTests:
    """End-to-end diagnostic coverage for runtime voice aliases."""

    __test__ = True

    def test_runtime_alias_report_round_trips_json_diagnostic(self) -> None:
        requested_voices = ("gong", "sw_grain", "tabla_ge", "bowed")

        resolved_voices = {
            voice: resolve_runtime_voice_name(voice) for voice in requested_voices
        }
        assert resolved_voices == {
            "gong": "bowed",
            "sw_grain": "sw_breath",
            "tabla_ge": "tabla_tin",
            "bowed": "bowed",
        }

        report = build_voice_alias_report()
        summary = summarize_voice_alias_report(report)

        assert report.total_aliases == len(RUNTIME_VOICE_ALIAS)
        assert summary["total_aliases"] == len(RUNTIME_VOICE_ALIAS)
        assert summary["namespace_counts"] == {"core": 5, "senseweave": 6}
        assert summary["family_counts"] == {
            "struck_tonal": 5,
            "metallic": 2,
            "granular": 2,
            "drum": 2,
        }

        target_to_sources = summary["target_to_sources"]
        assert isinstance(target_to_sources, dict)
        assert target_to_sources["bowed"] == ["gong", "bell"]
        assert target_to_sources["sw_breath"] == ["sw_grain"]
        assert aliases_for_target("bowed") == ("gong", "bell")
        assert aliases_for_target("sw_breath") == ("sw_grain",)

        source_to_target = {
            entry["source"]: entry["target"] for entry in summary["entries"]
        }
        assert len(source_to_target) == len(RUNTIME_VOICE_ALIAS)
        assert source_to_target["gong"] == "bowed"
        assert source_to_target["sw_grain"] == "sw_breath"
        assert source_to_target["tabla_ge"] == "tabla_tin"

        chains = {voice: list(alias_chain(voice)) for voice in requested_voices}
        assert chains == {
            "gong": ["gong", "bowed"],
            "sw_grain": ["sw_grain", "sw_breath"],
            "tabla_ge": ["tabla_ge", "tabla_tin"],
            "bowed": ["bowed"],
        }

        diagnostic = {
            "requested_voices": list(requested_voices),
            "resolved_voices": resolved_voices,
            "chains": chains,
            "report": {
                "total_aliases": summary["total_aliases"],
                "namespace_counts": summary["namespace_counts"],
                "family_counts": summary["family_counts"],
                "target_to_sources": {
                    "bowed": target_to_sources["bowed"],
                    "sw_breath": target_to_sources["sw_breath"],
                },
                "source_to_target": {
                    source: source_to_target[source]
                    for source in ("gong", "sw_grain", "tabla_ge")
                },
            },
        }

        round_trip = json.loads(json.dumps(diagnostic, sort_keys=True))
        assert round_trip == diagnostic
