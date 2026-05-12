"""Depth-2 rollout controls helpers - locked test surface for frac-0021."""
from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.piece_commission import commission_piece  # noqa: E402
from senseweave.practice_curriculum import select_practice_block  # noqa: E402
from senseweave.rollout_controls import (  # noqa: E402
    CURRICULUM_EXERCISE_ENV,
    LONG_FORM_SUITE_ENV,
    PREVIEW_RENDER_ENV,
    SELF_CRITIQUE_ENV,
    RolloutControlReport,
    RolloutFlagState,
    flag_state,
    load_feature_flags,
    rollout_control_report,
    summarize_rollout_controls,
)
from senseweave.self_critique import revise_score  # noqa: E402


def test_flag_state_reports_env_value() -> None:
    state = flag_state("preview", PREVIEW_RENDER_ENV, "off")

    assert isinstance(state, RolloutFlagState)
    assert dataclasses.is_dataclass(state)
    assert getattr(state, "__dataclass_params__").frozen
    assert state.name == "preview"
    assert state.env_var == PREVIEW_RENDER_ENV
    assert state.enabled is False
    assert state.raw_value == "off"
    assert state.default_enabled is True
    assert state.source == "env"


def test_flag_state_reports_default_and_defaulted_sources() -> None:
    missing = flag_state("suite", LONG_FORM_SUITE_ENV, None)
    typo = flag_state("critique", SELF_CRITIQUE_ENV, "sometimes")

    assert missing.enabled is True
    assert missing.raw_value is None
    assert missing.source == "default"
    assert typo.enabled is True
    assert typo.raw_value == "sometimes"
    assert typo.source == "defaulted"


def test_rollout_control_report_matches_loaded_flags() -> None:
    env = {
        CURRICULUM_EXERCISE_ENV: "1",
        PREVIEW_RENDER_ENV: "0",
        SELF_CRITIQUE_ENV: "yes",
        LONG_FORM_SUITE_ENV: "sometimes",
    }

    report = rollout_control_report(env)

    assert isinstance(report, RolloutControlReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.flags == load_feature_flags(env)
    assert tuple(state.name for state in report.flag_states) == (
        "curriculum",
        "preview",
        "critique",
        "suite",
    )
    assert report.enabled_count == 3
    assert report.disabled_count == 1
    assert report.effective_self_critique is False
    assert report.flag_states[-1].source == "defaulted"


def test_summarize_rollout_controls_returns_json_safe_summary() -> None:
    report = rollout_control_report(
        {
            CURRICULUM_EXERCISE_ENV: "0",
            PREVIEW_RENDER_ENV: "1",
            SELF_CRITIQUE_ENV: "0",
            LONG_FORM_SUITE_ENV: "on",
        }
    )

    summary = summarize_rollout_controls(report)

    assert summary == {
        "flags": {
            "curriculum": "off",
            "preview": "on",
            "critique": "off",
            "suite": "on",
            "effective_critique": "off",
        },
        "enabled_count": 2,
        "disabled_count": 2,
        "effective_self_critique": False,
        "states": [
            {
                "name": "curriculum",
                "env_var": CURRICULUM_EXERCISE_ENV,
                "enabled": False,
                "raw_value": "0",
                "default_enabled": True,
                "source": "env",
            },
            {
                "name": "preview",
                "env_var": PREVIEW_RENDER_ENV,
                "enabled": True,
                "raw_value": "1",
                "default_enabled": True,
                "source": "env",
            },
            {
                "name": "critique",
                "env_var": SELF_CRITIQUE_ENV,
                "enabled": False,
                "raw_value": "0",
                "default_enabled": True,
                "source": "env",
            },
            {
                "name": "suite",
                "env_var": LONG_FORM_SUITE_ENV,
                "enabled": True,
                "raw_value": "on",
                "default_enabled": True,
                "source": "env",
            },
        ],
    }


def test_rollout_report_flags_drive_existing_behavior() -> None:
    report = rollout_control_report(
        {
            CURRICULUM_EXERCISE_ENV: "0",
            PREVIEW_RENDER_ENV: "0",
            SELF_CRITIQUE_ENV: "1",
            LONG_FORM_SUITE_ENV: "0",
        }
    )
    flags = report.flags

    practice = select_practice_block(
        cadence_state="away_practice",
        family="forge",
        progression_profile="open_day",
        song_num=1,
        flags=flags,
    )
    revision = revise_score(
        {"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        song_num=5,
        thresholds={"development_score": ("min", 0.99)},
        flags=flags,
    )
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="evening_settling",
        weekly_phase="weekend",
        attention_score=1.0,
        narrative_pressure=1.0,
        occupancy_state="occupied_active",
        repertoire_entries=[{"ear_metrics": {"hook_clarity": 0.8}}] * 20,
        song_num=4,
        hour=22,
        flags=flags,
    )

    assert practice.name == "Performance Weave"
    assert revision.original_metrics == {}
    assert revision.revision_used is False
    assert commission.form_class == "extended"


def test_rollout_controls_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/rollout_controls.py")
    assert result.depth >= 2, result.reason
