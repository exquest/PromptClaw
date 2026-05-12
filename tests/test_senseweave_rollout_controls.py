"""Rollout controls for SenseWeave SDP features."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import commission_piece
from senseweave.practice_curriculum import select_practice_block
from senseweave.rollout_controls import SenseWeaveFeatureFlags, load_feature_flags
from senseweave.self_critique import revise_score


def test_feature_flags_can_be_enabled_independently() -> None:
    flags = load_feature_flags(
        {
            "CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE": "1",
            "CYPHERCLAW_ENABLE_PREVIEW_RENDER": "0",
            "CYPHERCLAW_ENABLE_SELF_CRITIQUE": "1",
            "CYPHERCLAW_ENABLE_LONG_FORM_SUITE": "0",
        }
    )

    assert flags.curriculum_exercise is True
    assert flags.preview_render is False
    assert flags.self_critique is True
    assert flags.long_form_suite is False
    assert flags.effective_self_critique is False
    assert flags.to_status_dict() == {
        "curriculum": "on",
        "preview": "off",
        "critique": "on",
        "suite": "off",
        "effective_critique": "off",
    }


def test_curriculum_flag_gates_away_practice_block() -> None:
    enabled = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=True,
        self_critique=True,
        long_form_suite=True,
    )
    disabled = SenseWeaveFeatureFlags(
        curriculum_exercise=False,
        preview_render=True,
        self_critique=True,
        long_form_suite=True,
    )

    active = select_practice_block(
        cadence_state="away_practice",
        family="forge",
        progression_profile="open_day",
        song_num=1,
        flags=enabled,
    )
    rolled_back = select_practice_block(
        cadence_state="away_practice",
        family="forge",
        progression_profile="open_day",
        song_num=1,
        flags=disabled,
    )

    assert active.name == "Harmony Lab"
    assert rolled_back.name == "Performance Weave"
    assert disabled.preview_render is True
    assert disabled.self_critique is True
    assert disabled.long_form_suite is True


def test_preview_and_self_critique_flags_gate_revision_behavior() -> None:
    mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
    strict_thresholds = {"development_score": ("min", 0.99)}

    preview_off = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=False,
        self_critique=True,
        long_form_suite=True,
    )
    critique_off = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=True,
        self_critique=False,
        long_form_suite=True,
    )
    both_on = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=True,
        self_critique=True,
        long_form_suite=True,
    )

    no_preview = revise_score(mood, song_num=5, thresholds=strict_thresholds, flags=preview_off)
    no_critique = revise_score(mood, song_num=5, thresholds=strict_thresholds, flags=critique_off)
    active = revise_score(mood, song_num=5, thresholds=strict_thresholds, flags=both_on)

    assert no_preview.original_metrics == {}
    assert no_preview.revised_score is None
    assert no_preview.revision_used is False
    assert "development_score" in no_critique.original_metrics
    assert no_critique.revised_score is None
    assert no_critique.revision_used is False
    assert active.revised_metrics is not None


def test_long_form_suite_flag_downshifts_suite_only() -> None:
    enabled = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=True,
        self_critique=True,
        long_form_suite=True,
    )
    suite_disabled = SenseWeaveFeatureFlags(
        curriculum_exercise=True,
        preview_render=True,
        self_critique=True,
        long_form_suite=False,
    )

    high_pressure_kwargs = dict(
        cadence_state="occupied_day",
        day_phase="evening_settling",
        weekly_phase="weekend",
        attention_score=1.0,
        narrative_pressure=1.0,
        occupancy_state="occupied_active",
        repertoire_entries=[{"ear_metrics": {"hook_clarity": 0.8}}] * 20,
        song_num=4,
        hour=22,
    )
    ordinary_kwargs = dict(
        cadence_state="occupied_day",
        day_phase="midday",
        attention_score=0.1,
        narrative_pressure=0.3,
        occupancy_state="occupied_quiet",
        repertoire_entries=(),
        song_num=2,
        hour=12,
    )

    assert commission_piece(**high_pressure_kwargs, flags=enabled).form_class == "suite"
    assert commission_piece(**high_pressure_kwargs, flags=suite_disabled).form_class == "extended"
    assert commission_piece(**ordinary_kwargs, flags=suite_disabled).form_class == "song"


def test_docs_name_rollout_order_and_rollback_files() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_text = "\n".join(
        [
            (root / "docs" / "command-reference.md").read_text(encoding="utf-8"),
            (root / "docs" / "startup-wizard.md").read_text(encoding="utf-8"),
            (root / "docs" / "architecture.md").read_text(encoding="utf-8"),
            (root / "docs" / "handoff-protocol.md").read_text(encoding="utf-8"),
            (root / "docs" / "cypherclaw-upgrade-checklist.md").read_text(encoding="utf-8"),
            (root / "CHANGELOG.md").read_text(encoding="utf-8"),
        ]
    )

    assert "Safe rollout order" in docs_text
    assert "Rollback files" in docs_text
    for env_name in (
        "CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE",
        "CYPHERCLAW_ENABLE_PREVIEW_RENDER",
        "CYPHERCLAW_ENABLE_SELF_CRITIQUE",
        "CYPHERCLAW_ENABLE_LONG_FORM_SUITE",
    ):
        assert env_name in docs_text
    for path in (
        "my-claw/tools/senseweave/operator_diagnostics.py",
        "my-claw/tools/senseweave/rollout_controls.py",
        "my-claw/tools/cypherclaw_daemon.py",
        "my-claw/tools/glyphweave/scenes.py",
    ):
        assert path in docs_text
