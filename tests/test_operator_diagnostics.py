"""Operator diagnostics for SenseWeave status output."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from glyphweave.scenes import CypherClawArt
from senseweave.operator_diagnostics import DiagnosticPaths, collect_operator_diagnostics


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_status_display_includes_senseweave_diagnostics(tmp_path: Path) -> None:
    score_tree_path = tmp_path / "current_score_tree.json"
    tracker_path = tmp_path / "tracker_runtime_state.json"
    composer_path = tmp_path / "composer_state.json"
    sample_activity_path = tmp_path / "sample_dsp_activity.json"
    sample_playback_path = tmp_path / "sample_playback_state.json"
    master_bus_path = tmp_path / "master_bus_state.json"
    self_listener_path = tmp_path / "self_listen.json"

    _write_json(
        score_tree_path,
        {
            "piece_id": "tree-123",
            "title": "Quiet Rooms",
            "commission": {"form_class": "suite", "composition_mode": "hybrid"},
            "sections": [{"scene_name": "Theme", "function": "statement"}],
        },
    )
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_name": "Theme",
            "automation_curve": "rise_release",
            "automation": {"density": 0.72, "master_amp": 0.65},
            "aggregate_intentions": {
                "global_energy": 0.714,
                "global_restraint": 0.2,
                "global_brightness": 0.55,
            },
            "scene_metadata": {"section_function": "arrival"},
        },
    )
    _write_json(
        composer_path,
        {
            "song_title": "Quiet Rooms",
            "ear_metrics": {
                "hook_clarity": 0.81,
                "cadence_strength": 0.73,
                "development_score": 0.62,
            },
            "master_bus": {"amp": 2.1, "drive": 0.12},
            "sample_source": "room_mic",
            "section_curve": "fallback_curve",
        },
    )
    _write_json(
        sample_activity_path,
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
    )
    _write_json(
        sample_playback_path,
        {
            "playing": True,
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "mode": "grain_cloud",
        },
    )
    _write_json(master_bus_path, {"timestamp": 99.0, "node_id": 99999})
    _write_json(
        self_listener_path,
        {
            "timestamp": 100.0,
            "rms": 0.08,
            "capture_backend": "jack",
            "capture_port": "SuperCollider:out_1",
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=score_tree_path,
            tracker_runtime=tracker_path,
            composer_state=composer_path,
            sample_activity=sample_activity_path,
            sample_playback=sample_playback_path,
            master_bus=master_bus_path,
            self_listener=self_listener_path,
        ),
        now=100.0,
    )

    status = CypherClawArt().status_display(
        memory=1,
        tasks=0,
        schedules=0,
        artifacts=0,
        senseweave=diagnostics.to_status_dict(),
    )

    lower = status.lower()
    assert "senseweave" in lower
    assert "score tree" in lower
    assert "quiet rooms" in lower
    assert "tree-123" in status
    assert "section function" in lower
    assert "arrival" in lower
    assert "arrangement curve" in lower
    assert "rise_release" in status
    assert "ear metrics" in lower
    assert "hook=0.81" in lower
    assert "aggregate intentions" in lower
    assert "energy=0.71" in lower
    assert "restraint=0.2" in lower
    assert "brightness=0.55" in lower
    assert "sample source" in lower
    assert "theramini in via room mic" in lower
    assert "master bus" in lower
    assert "alive" in lower
    assert "amp=2.1" in lower
    assert "self-listener" in lower
    assert "jack" in lower
    assert "rms=0.08" in lower
    assert "curriculum=on" in lower
    assert "preview=on" in lower
    assert "critique=on" in lower
    assert "suite=on" in lower


def test_status_display_includes_combined_sampler_plan_and_playback(tmp_path: Path) -> None:
    sample_activity_path = tmp_path / "sample_dsp_activity.json"
    sample_playback_path = tmp_path / "sample_playback_state.json"

    _write_json(
        sample_activity_path,
        {
            "requested_sample_source": "theramini_in",
            "sample_source": "room_mic",
            "activity_mode": "grain_cloud",
            "capture_ready": True,
            "trigger_now": True,
        },
    )
    _write_json(
        sample_playback_path,
        {
            "playing": True,
            "requested_sample_source": "self_bus",
            "sample_source": "self_bus",
            "mode": "freeze_bed",
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=tmp_path / "missing.json",
            sample_activity=sample_activity_path,
            sample_playback=sample_playback_path,
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    assert diagnostics.sample_source == (
        "currently sampling theramini in via room mic"
        " · playing sample freeze bed from source self bus"
    )

    status = CypherClawArt().status_display(
        memory=0,
        tasks=0,
        schedules=0,
        artifacts=0,
        senseweave=diagnostics.to_status_dict(),
    )

    lower = status.lower()
    assert "currently sampling theramini in via room mic" in lower
    assert "playing sample freeze bed from source self bus" in lower


def test_operator_diagnostics_tolerates_missing_and_corrupt_state(tmp_path: Path) -> None:
    corrupt_score_tree = tmp_path / "current_score_tree.json"
    corrupt_score_tree.write_text("{not json", encoding="utf-8")

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=corrupt_score_tree,
            tracker_runtime=tmp_path / "missing_tracker.json",
            composer_state=tmp_path / "missing_composer.json",
            sample_activity=tmp_path / "missing_sample_activity.json",
            sample_playback=tmp_path / "missing_sample_playback.json",
            master_bus=tmp_path / "missing_master_bus.json",
            self_listener=tmp_path / "missing_self_listener.json",
        ),
        now=200.0,
    )

    payload = diagnostics.to_status_dict()

    assert payload["score_tree"] == "unknown"
    assert payload["section_function"] == "unknown"
    assert payload["arrangement_curve"] == "unknown"
    assert payload["ear_metrics"] == "unavailable"
    assert payload["sample_source"] == "unavailable"
    assert payload["master_bus"] == "unknown"
    assert payload["self_listener"] == "unavailable"
    assert payload["production_course"] == "unavailable"
    assert payload["theramini_relation"] == "unavailable"
    assert payload["critique_notes"] == "unavailable"
    assert payload["aggregate_intentions"] == "unavailable"


def test_production_course_in_status(tmp_path: Path) -> None:
    """Production-course chapter values appear in diagnostics from scene_metadata."""
    tracker_path = tmp_path / "tracker_runtime_state.json"
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_name": "Arrival",
            "scene_metadata": {
                "section_function": "arrival",
                "production_phase_profile": "Convergence",
                "production_mode_scale": "modal",
                "production_harmonic_function": "dominant",
                "production_meter_groove": "groove",
                "production_genre_strategy": "rhythmic_pattern",
                "production_mix_role": "foreground",
                "production_spatial_intent": "wide",
                "production_counterpoint_relation": "contrary_motion",
            },
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tracker_path,
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    course = diagnostics.production_course
    assert "Convergence" in course
    assert "modal" in course
    assert "dominant" in course
    assert "groove" in course
    assert "rhythmic pattern" in course or "rhythmic_pattern" in course
    assert "foreground" in course
    assert "wide" in course

    payload = diagnostics.to_status_dict()
    assert "production_course" in payload
    assert payload["production_course"] != "unavailable"


def test_production_course_fallback_to_score_tree(tmp_path: Path) -> None:
    """Production-course data falls back to score_tree sections when tracker is empty."""
    score_tree_path = tmp_path / "current_score_tree.json"
    tracker_path = tmp_path / "tracker_runtime_state.json"
    _write_json(
        score_tree_path,
        {
            "piece_id": "tree-456",
            "title": "Fallback Test",
            "commission": {"form_class": "song"},
            "sections": [
                {
                    "scene_name": "Theme",
                    "function": "statement",
                    "production_course": {
                        "phase_profile": "Emergence",
                        "mode_scale": "functional",
                        "harmonic_function": "tonic",
                        "meter_groove": "pulse",
                        "genre_strategy": "minimalist_process",
                        "mix_role": "lead",
                        "spatial_intent": "clear",
                        "counterpoint_relation": "parallel_thirds",
                    },
                },
            ],
        },
    )
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_name": "Theme",
            "scene_metadata": {"section_function": "statement"},
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=score_tree_path,
            tracker_runtime=tracker_path,
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    course = diagnostics.production_course
    assert "Emergence" in course
    assert "functional" in course
    assert "tonic" in course


def test_theramini_relation_in_status(tmp_path: Path) -> None:
    """Theramini relation shows counterpoint relation and playing state."""
    tracker_path = tmp_path / "tracker_runtime_state.json"
    theramini_path = tmp_path / "theramini_state.json"
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_metadata": {
                "production_counterpoint_relation": "contrary_motion",
            },
        },
    )
    _write_json(
        theramini_path,
        {
            "is_playing": True,
            "note_name": "C4",
            "frequency_hz": 261.63,
            "timestamp": 100.0,
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tracker_path,
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=theramini_path,
        ),
        now=100.0,
    )

    relation = diagnostics.theramini_relation
    assert "contrary motion" in relation or "contrary_motion" in relation
    assert "playing" in relation.lower()
    assert "C4" in relation

    payload = diagnostics.to_status_dict()
    assert payload["theramini_relation"] != "unavailable"


def test_theramini_relation_without_playing(tmp_path: Path) -> None:
    """Theramini relation shows counterpoint only when Theramini is not playing."""
    tracker_path = tmp_path / "tracker_runtime_state.json"
    theramini_path = tmp_path / "theramini_state.json"
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_metadata": {
                "production_counterpoint_relation": "oblique_pedal",
            },
        },
    )
    _write_json(
        theramini_path,
        {"is_playing": False, "timestamp": 100.0},
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tracker_path,
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=theramini_path,
        ),
        now=100.0,
    )

    relation = diagnostics.theramini_relation
    assert "oblique pedal" in relation or "oblique_pedal" in relation
    assert "playing" not in relation.lower()


def test_critique_notes_in_status(tmp_path: Path) -> None:
    """Critique notes derived from ear_metrics thresholds."""
    composer_path = tmp_path / "composer_state.json"
    _write_json(
        composer_path,
        {
            "ear_metrics": {
                "hook_clarity": 0.12,
                "cadence_strength": 0.73,
                "development_score": 0.62,
                "static_score": 0.85,
            },
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=composer_path,
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    notes = diagnostics.critique_notes
    assert notes != "unavailable"
    assert "hook_clarity" in notes
    assert "static_score" in notes


def test_critique_notes_all_passing(tmp_path: Path) -> None:
    """When all metrics pass thresholds, critique notes show passing status."""
    composer_path = tmp_path / "composer_state.json"
    _write_json(
        composer_path,
        {
            "ear_metrics": {
                "hook_clarity": 0.81,
                "cadence_strength": 0.73,
                "development_score": 0.62,
                "static_score": 0.22,
            },
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=composer_path,
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    notes = diagnostics.critique_notes
    assert "pass" in notes.lower()


def test_aggregate_intentions_exclude_raw_pairings(tmp_path: Path) -> None:
    """Aggregate-intention telemetry is surfaced without raw sensor mappings."""
    tracker_path = tmp_path / "tracker_runtime_state.json"
    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "automation_curve": "rise_release",
            "automation": {"density": 0.72, "master_amp": 0.65},
            "aggregate_intentions": {
                "global_energy": 0.7139,
                "global_restraint": 0.2,
                "global_brightness": 0.55,
                "theramini_active": 1.0,
                "outdoor_brightness": 0.9,
                "sensor_brightness": 0.4,
                "cutoff_hz": 14_000,
            },
            "raw_sensor_values": {
                "theramini_active": 1.0,
                "outdoor_brightness": 0.9,
            },
            "sensor_to_parameter_mappings": {
                "outdoor_brightness": "cutoff_hz",
            },
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tracker_path,
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    payload = diagnostics.to_status_dict()

    assert payload["aggregate_intentions"] == {
        "global_energy": 0.714,
        "global_restraint": 0.2,
        "global_brightness": 0.55,
    }
    payload_text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "theramini_active",
        "outdoor_brightness",
        "sensor_brightness",
        "raw_sensor_values",
        "sensor_to_parameter_mappings",
        "cutoff_hz",
    ):
        assert forbidden not in payload_text

    status = CypherClawArt().status_display(
        memory=1,
        tasks=0,
        schedules=0,
        artifacts=0,
        senseweave=payload,
    )

    lower = status.lower()
    assert "aggregate intentions" in lower
    assert "energy=0.71" in lower
    assert "restraint=0.2" in lower
    assert "brightness=0.55" in lower
    for forbidden in ("theramini_active", "outdoor_brightness", "sensor_brightness", "cutoff_hz"):
        assert forbidden not in status


def test_no_hallucinated_fields(tmp_path: Path) -> None:
    """New fields never contain fabricated data when authority files are absent."""
    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=200.0,
    )

    payload = diagnostics.to_status_dict()

    assert payload["production_course"] == "unavailable"
    assert payload["theramini_relation"] == "unavailable"
    assert payload["critique_notes"] == "unavailable"
    assert payload["aggregate_intentions"] == "unavailable"

    for key in ("production_course", "theramini_relation", "critique_notes"):
        value = str(payload[key])
        assert value in ("unavailable", "unknown") or value.startswith("pass"), (
            f"{key} should be explicit sentinel, got: {value!r}"
        )


def test_status_display_renders_new_fields(tmp_path: Path) -> None:
    """CypherClawArt.status_display renders production course, Theramini, critique."""
    tracker_path = tmp_path / "tracker_runtime_state.json"
    theramini_path = tmp_path / "theramini_state.json"
    composer_path = tmp_path / "composer_state.json"

    _write_json(
        tracker_path,
        {
            "timestamp": 100.0,
            "scene_metadata": {
                "section_function": "arrival",
                "production_phase_profile": "Convergence",
                "production_mode_scale": "modal",
                "production_harmonic_function": "dominant",
                "production_meter_groove": "groove",
                "production_genre_strategy": "rhythmic_pattern",
                "production_mix_role": "foreground",
                "production_spatial_intent": "wide",
                "production_counterpoint_relation": "contrary_motion",
            },
        },
    )
    _write_json(
        theramini_path,
        {"is_playing": True, "note_name": "E4", "timestamp": 100.0},
    )
    _write_json(
        composer_path,
        {
            "ear_metrics": {
                "hook_clarity": 0.12,
                "static_score": 0.85,
                "development_score": 0.62,
            },
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tracker_path,
            composer_state=composer_path,
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=theramini_path,
        ),
        now=100.0,
    )

    status = CypherClawArt().status_display(
        memory=1,
        tasks=0,
        schedules=0,
        artifacts=0,
        senseweave=diagnostics.to_status_dict(),
    )

    lower = status.lower()
    assert "production course" in lower
    assert "convergence" in lower
    assert "modal" in lower
    assert "theramini" in lower
    assert "critique" in lower


def test_sampler_metrics_in_status(tmp_path: Path) -> None:
    """Sampler CI metrics surface from composer_state for operator review."""
    composer_path = tmp_path / "composer_state.json"
    _write_json(
        composer_path,
        {
            "sampler_event_count_per_piece": 14,
            "sampler_library_vs_self_ratio": 2.1,
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=composer_path,
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    surface = diagnostics.sampler_metrics
    assert "events/piece=14" in surface
    assert "library:self=2.10" in surface
    assert "ok" in surface

    payload = diagnostics.to_status_dict()
    assert payload["sampler_metrics"] == surface


def test_sampler_metrics_flags_out_of_band_ratio(tmp_path: Path) -> None:
    composer_path = tmp_path / "composer_state.json"
    _write_json(
        composer_path,
        {
            "sampler_event_count_per_piece": 4,
            "sampler_library_vs_self_ratio": 0.5,
        },
    )

    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=composer_path,
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    assert "out-of-band" in diagnostics.sampler_metrics


def test_sampler_metrics_unavailable_when_composer_silent(tmp_path: Path) -> None:
    diagnostics = collect_operator_diagnostics(
        paths=DiagnosticPaths(
            score_tree=tmp_path / "missing.json",
            tracker_runtime=tmp_path / "missing.json",
            composer_state=tmp_path / "missing.json",
            sample_activity=tmp_path / "missing.json",
            sample_playback=tmp_path / "missing.json",
            master_bus=tmp_path / "missing.json",
            self_listener=tmp_path / "missing.json",
            theramini=tmp_path / "missing.json",
        ),
        now=100.0,
    )

    assert diagnostics.sampler_metrics == "unavailable"

def test_generation_status_reads_file(tmp_path: Path) -> None:
    from senseweave.operator_diagnostics import generation_status
    status_file = tmp_path / "generation_status.json"
    _write_json(status_file, {"queue_depth": 2, "is_generating": True})
    
    result = generation_status(path=status_file)
    assert result["queue_depth"] == 2
    assert result["is_generating"] is True


def test_generation_status_returns_dict(tmp_path: Path) -> None:
    from senseweave.operator_diagnostics import generation_status
    result = generation_status(path=tmp_path / "missing.json")
    assert isinstance(result, dict)
    assert "queue_depth" in result
    assert "is_generating" in result
    assert "caption" in result


def test_generation_status_captions(tmp_path: Path) -> None:
    from senseweave.operator_diagnostics import generation_status
    status_file = tmp_path / "generation_status.json"
    
    # queue depth > 1
    _write_json(status_file, {"queue_depth": 3, "is_generating": True})
    assert generation_status(path=status_file)["caption"] == "♫ queued: 3"
    
    # queue depth == 1
    _write_json(status_file, {"queue_depth": 1, "is_generating": False})
    assert generation_status(path=status_file)["caption"] == "♫ generating"
    
    # is_generating == True
    _write_json(status_file, {"queue_depth": 0, "is_generating": True})
    assert generation_status(path=status_file)["caption"] == "♫ generating"
    
    # ready
    _write_json(status_file, {"queue_depth": 0, "is_generating": False})
    assert generation_status(path=status_file)["caption"] == "♫ ready"


def test_generation_status_handles_errors(tmp_path: Path) -> None:
    from senseweave.operator_diagnostics import generation_status
    status_file = tmp_path / "generation_status.json"
    
    # Invalid JSON
    status_file.write_text("invalid json")
    result = generation_status(path=status_file)
    assert result["queue_depth"] == 0
    assert result["caption"] == "♫ ready"
    
    # Missing file
    missing_file = tmp_path / "does_not_exist.json"
    result2 = generation_status(path=missing_file)
    assert result2["queue_depth"] == 0
    assert result2["caption"] == "♫ ready"
