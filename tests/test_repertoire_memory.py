"""Tests for repertoire_memory.py -- long-term song memory and hints."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.repertoire_memory import RepertoireMemory


def test_store_and_recall_family_hint(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Quiet Machines",
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        key="C",
        hook_text="hold the light",
        hook_class="contour",
        practice_block="",
        ear_metrics={"hook_clarity": 0.8},
    )

    hint = memory.recall_hint(family="ember", cadence_state="occupied_day")
    assert hint is not None
    assert hint["title"] == "Quiet Machines"
    assert hint["hook_text"] == "hold the light"
    assert "feedback_scores" in hint


def test_promotes_high_scoring_song(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Night Procession",
        family="drift",
        progression_profile="settling",
        cadence_state="wind_down",
        key="Am",
        hook_text="slow return",
        hook_class="rhythmic",
        practice_block="Ear Lab",
        ear_metrics={"hook_clarity": 0.91, "cadence_strength": 0.88},
    )

    promoted = memory.promoted_entries()
    assert promoted
    assert promoted[0]["title"] == "Night Procession"


def test_influence_for_song_biases_future_material(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Quiet Machines",
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        key="C",
        hook_text="hold the light",
        hook_class="contour",
        practice_block="",
        ear_metrics={"hook_clarity": 0.86, "cadence_strength": 0.74},
    )

    influence = memory.influence_for_song(
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=8,
    )

    assert influence is not None
    assert influence["source_title"] == "Quiet Machines"
    assert influence["progression_profile"] == "open_day"
    assert influence["hook_text"]
    assert influence["mode"] in {"recall", "answer"}
    assert influence["form_variant"] in {"base", "bridge", "concise", "afterglow"}
    assert -0.2 <= influence["density_bias"] <= 0.2
    assert influence["payoff_scene"] in {
        "Theme",
        "Bridge",
        "Recap",
        "Resolution",
        "Release",
        "Afterglow",
    }
    assert 0.0 <= influence["payoff_bias"] <= 0.2


def test_influence_for_song_surfaces_ear_feedback_corrections(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Static Low Room",
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        key="C",
        hook_text="hold the light",
        hook_class="contour",
        practice_block="",
        ear_metrics={
            "interval_variety": 0.05,
            "pitch_range_semitones": 2.0,
            "onset_density": 0.2,
            "repetition_score": 0.9,
            "spectral_centroid_hz": 420.0,
            "spectral_flatness": 0.12,
            "roughness": 0.1,
            "hook_clarity": 0.2,
            "cadence_strength": 0.25,
            "development_score": 0.1,
        },
    )

    influence = memory.influence_for_song(
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=9,
    )

    assert influence is not None
    assert {"static", "muddy", "underdeveloped"} <= set(
        influence["correction_tags"]
    )
    assert influence["feedback_scores"]["static_score"] >= 0.55


def test_load_repairs_legacy_hook_text(tmp_path: Path) -> None:
    path = tmp_path / "repertoire.json"
    path.write_text(
        """
        {
          "songs": [
            {
              "title": "Soft Rooms",
              "family": "drift",
              "progression_profile": "open_day",
              "cadence_state": "occupied_day",
              "key": "D",
              "hook_text": "answer the again",
              "hook_class": "lyric",
              "practice_block": "",
              "ear_metrics": {"hook_clarity": 0.82},
              "stored_at": 1.0
            }
          ]
        }
        """.strip()
    )
    memory = RepertoireMemory(path=str(path))

    hint = memory.recall_hint(family="drift", cadence_state="occupied_day")

    assert hint is not None
    assert hint["hook_text"] == "keep the room open"
    repaired = path.read_text()
    assert "answer the again" not in repaired


def test_all_songs_returns_patch_name_and_copy(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Quiet Rooms",
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        key="C",
        hook_text="keep the room open",
        hook_class="lyric",
        practice_block="",
        patch_name="house_chamber",
        ear_metrics={"hook_clarity": 0.81},
    )

    songs = memory.all_songs()

    assert songs[0]["patch_name"] == "house_chamber"
    songs[0]["patch_name"] = "mutated"
    assert memory.all_songs()[0]["patch_name"] == "house_chamber"


# ---------------------------------------------------------------------------
# audio_render_ref and source_samples fields
# ---------------------------------------------------------------------------


def test_store_song_records_audio_render_ref_and_source_samples(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Rendered Room",
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        key="C",
        hook_text="hear the room",
        hook_class="contour",
        practice_block="",
        ear_metrics={"hook_clarity": 0.85},
        audio_render_ref="/mnt/archive/cypherclaw/archive/music/performance_20260416_120000.wav",
        source_samples=["pad_warm.wav", "pluck_bright.wav"],
    )

    songs = memory.all_songs()
    assert len(songs) == 1
    assert songs[0]["audio_render_ref"] == "/mnt/archive/cypherclaw/archive/music/performance_20260416_120000.wav"
    assert songs[0]["source_samples"] == ["pad_warm.wav", "pluck_bright.wav"]


def test_store_song_omits_empty_audio_render_ref(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="No Render",
        family="drift",
        progression_profile="settling",
        cadence_state="wind_down",
        key="Am",
        hook_text="quiet",
        hook_class="contour",
        practice_block="",
        ear_metrics={"hook_clarity": 0.5},
    )

    songs = memory.all_songs()
    assert "audio_render_ref" not in songs[0]
    assert "source_samples" not in songs[0]


# ---------------------------------------------------------------------------
# House repertoire promotion
# ---------------------------------------------------------------------------


def _store_with_metrics(
    memory: RepertoireMemory,
    title: str,
    hook_text: str,
    hook_clarity: float = 0.5,
    cadence_strength: float = 0.5,
    **kwargs: object,
) -> None:
    defaults = {
        "family": "ember",
        "progression_profile": "open_day",
        "cadence_state": "occupied_day",
        "key": "C",
        "hook_class": "contour",
        "practice_block": "",
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    memory.store_song(
        title=title,
        hook_text=hook_text,
        ear_metrics={"hook_clarity": hook_clarity, "cadence_strength": cadence_strength},
        **defaults,  # type: ignore[arg-type]
    )


def test_promote_to_house_writes_to_archive_root(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive-10tb"
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    _store_with_metrics(memory, "Strong Room", "hold the light", hook_clarity=0.9)

    promoted = memory.promote_to_house(archive_root=str(archive_root))

    assert len(promoted) == 1
    assert promoted[0]["title"] == "Strong Room"
    house_path = archive_root / "house_repertoire.json"
    assert house_path.exists()


def test_promote_to_house_defaults_to_repertoire_parent(tmp_path: Path) -> None:
    subdir = tmp_path / "state"
    subdir.mkdir()
    memory = RepertoireMemory(path=str(subdir / "repertoire.json"))
    _store_with_metrics(memory, "Local Room", "stay open", hook_clarity=0.85)

    memory.promote_to_house()

    house_path = subdir / "house_repertoire.json"
    assert house_path.exists()


def test_promote_to_house_applies_promotion_rules(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    # Below threshold — should NOT be promoted
    _store_with_metrics(memory, "Weak Room", "faint echo", hook_clarity=0.3, cadence_strength=0.2)
    # hook_clarity >= 0.8 — should be promoted
    _store_with_metrics(memory, "Hook Room", "strong hook", hook_clarity=0.82)
    # cadence_strength >= 0.85 — should be promoted
    _store_with_metrics(memory, "Cadence Room", "resolved ending", cadence_strength=0.88)

    promoted = memory.promote_to_house(archive_root=str(tmp_path / "archive"))
    titles = {p["title"] for p in promoted}

    assert "Hook Room" in titles
    assert "Cadence Room" in titles
    assert "Weak Room" not in titles


def test_promote_skips_exact_duplicate_title_when_alternatives_exist(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    _store_with_metrics(memory, "First Light", "dawn melody", hook_clarity=0.9)
    _store_with_metrics(memory, "Second Light", "evening resolve", hook_clarity=0.88)

    archive_root = tmp_path / "archive"
    # First promotion
    memory.promote_to_house(archive_root=str(archive_root))

    # Store another song with the same title
    _store_with_metrics(memory, "First Light", "dawn melody v2", hook_clarity=0.92)
    _store_with_metrics(memory, "Third Light", "night bloom", cadence_strength=0.9)

    # Second promotion — "First Light" should be skipped (duplicate title,
    # alternatives exist), "Third Light" should be promoted
    promoted = memory.promote_to_house(archive_root=str(archive_root))
    titles = {p["title"] for p in promoted}

    assert "Third Light" in titles
    assert "First Light" not in titles


def test_promote_skips_exact_duplicate_hook_when_alternatives_exist(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    _store_with_metrics(memory, "Room A", "hold the line", hook_clarity=0.84)
    _store_with_metrics(memory, "Room B", "open the door", hook_clarity=0.91)

    archive_root = tmp_path / "archive"
    memory.promote_to_house(archive_root=str(archive_root))

    # New song with same hook text as Room A, different title
    _store_with_metrics(memory, "Room C", "hold the line", hook_clarity=0.88)
    _store_with_metrics(memory, "Room D", "close the window", cadence_strength=0.87)

    promoted = memory.promote_to_house(archive_root=str(archive_root))
    titles = {p["title"] for p in promoted}

    assert "Room D" in titles
    assert "Room C" not in titles


def test_promote_allows_sole_candidate_even_if_duplicate(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    _store_with_metrics(memory, "Only Song", "the only hook", hook_clarity=0.9)

    archive_root = tmp_path / "archive"
    memory.promote_to_house(archive_root=str(archive_root))

    # Clear and add same song again as the only candidate
    memory2 = RepertoireMemory(path=str(tmp_path / "repertoire2.json"))
    _store_with_metrics(memory2, "Only Song", "the only hook", hook_clarity=0.95)

    # Only one candidate — duplicate title but no alternatives, still skip
    # (already in house by title)
    promoted = memory2.promote_to_house(archive_root=str(archive_root))
    assert len(promoted) == 0


def test_house_repertoire_reads_back_promoted_entries(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    _store_with_metrics(memory, "Strong Room", "hold the light", hook_clarity=0.9)
    memory.promote_to_house(archive_root=str(archive_root))

    house = memory.house_repertoire(archive_root=str(archive_root))
    assert len(house) == 1
    assert house[0]["title"] == "Strong Room"
    assert house[0]["ear_metrics"]["hook_clarity"] == 0.9


def test_promoted_entry_includes_score_tree_and_render_refs(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    memory.store_song(
        title="Full Record",
        family="ember",
        progression_profile="lift",
        cadence_state="occupied_day",
        key="C",
        hook_text="complete entry",
        hook_class="contour",
        practice_block="",
        form_class="bridge",
        ending_family="resolve",
        ear_metrics={"hook_clarity": 0.92, "cadence_strength": 0.88},
        audio_render_ref="/mnt/archive/music/perf_001.wav",
        source_samples=["pad.wav", "pluck.wav"],
    )

    archive_root = tmp_path / "archive"
    promoted = memory.promote_to_house(archive_root=str(archive_root))

    assert len(promoted) == 1
    entry = promoted[0]
    assert entry["form_class"] == "bridge"
    assert entry["ending_family"] == "resolve"
    assert entry["audio_render_ref"] == "/mnt/archive/music/perf_001.wav"
    assert entry["source_samples"] == ["pad.wav", "pluck.wav"]
    assert "promoted_at" in entry


def test_promote_to_house_archive_path_resolution(tmp_path: Path) -> None:
    """House repertoire file lands inside the archive root, not beside repertoire."""
    archive_root = tmp_path / "mnt" / "archive" / "cypherclaw"
    archive_root.mkdir(parents=True)
    state_dir = tmp_path / "local" / "state"
    state_dir.mkdir(parents=True)

    memory = RepertoireMemory(path=str(state_dir / "repertoire.json"))
    _store_with_metrics(memory, "Archive Song", "stored far away", hook_clarity=0.85)
    memory.promote_to_house(archive_root=str(archive_root))

    # File should be in archive root, not in state_dir
    assert (archive_root / "house_repertoire.json").exists()
    assert not (state_dir / "house_repertoire.json").exists()
