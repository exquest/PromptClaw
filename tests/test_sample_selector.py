"""Tests for the mood/mode/arc-aware deterministic SampleSelector."""
from __future__ import annotations

import os
import sys
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.artist_identity import COMPANION, EVENING_REFLECTION, SOLITARY, STORM, WORKING_AMBIENCE
from senseweave.sample_library import SampleLibrary, SampleRecord
from senseweave.sample_selector import SOURCE_PREFERENCES, SampleSelector


def _touch_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48_000)
        w.writeframes(b"\x00\x00")
    return path


def _add(
    library: SampleLibrary,
    tmp_path: Path,
    sample_id: str,
    *,
    source: str,
    tags: frozenset[str] = frozenset({"warm", "harmonic"}),
    arc_phase: str | None = "Emergence",
    mood: float | None = 0.3,
    pitch_hz: float | None = 220.0,
    captured_at: datetime | None = None,
) -> SampleRecord:
    wav = _touch_wav(tmp_path / "wavs" / f"{sample_id}.wav")
    record = SampleRecord(
        character_tags=tags,
        sample_id=sample_id,
        path=wav,
        source=source,
        pitch_hz=pitch_hz,
        arc_phase=arc_phase,
        mood=mood,
        captured_at=captured_at or datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
    )
    library.add(record)
    return record


def test_source_preference_constants_match_spec() -> None:
    assert SOURCE_PREFERENCES["solitary"] == (
        "self",
        "contact",
        "room",
        "generated",
        "library",
    )
    assert SOURCE_PREFERENCES["companion"] == (
        "library",
        "self",
        "room",
        "generated",
    )
    assert SOURCE_PREFERENCES["working_ambience"] == (
        "room",
        "library",
        "generated",
    )
    assert SOURCE_PREFERENCES["evening_reflection"] == (
        "self",
        "library",
        "generated",
        "theramini",
    )
    assert SOURCE_PREFERENCES["storm"] == (
        "contact",
        "library",
        "generated",
        "room",
    )


def test_per_mode_source_preference_first_match_wins(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    # Companion order: library, self, room. Add one sample to each.
    _add(library, tmp_path, "lib", source="library", mood=0.4)
    _add(library, tmp_path, "self", source="self", mood=0.4)
    _add(library, tmp_path, "room", source="room", mood=0.4)

    selector = SampleSelector(library, rng_seed=7)
    chosen = selector.select(
        mode=COMPANION,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert chosen is not None
    assert chosen.sample_id == "lib"

    # Solitary order: self first
    chosen2 = SampleSelector(library, rng_seed=7).select(
        mode=SOLITARY,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert chosen2 is not None
    assert chosen2.sample_id == "self"
    library.close()


def test_mood_overlap_ranking_within_source(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    # All same source, same arc_phase; mood scalar varies. Target mood is positive.
    _add(library, tmp_path, "low", source="library", mood=0.1)
    _add(library, tmp_path, "high", source="library", mood=0.9)
    _add(library, tmp_path, "mid", source="library", mood=0.5)

    selector = SampleSelector(library, rng_seed=11)
    chosen = selector.select(
        mode=COMPANION,
        arc_phase="Emergence",
        mood={"energy": 0.6, "valence": 0.6, "arousal": 0.6},
    )
    assert chosen is not None
    assert chosen.sample_id == "high"

    # Negative target mood should flip the ranking.
    chosen_neg = SampleSelector(library, rng_seed=11).select(
        mode=COMPANION,
        arc_phase="Emergence",
        mood={"energy": -0.6, "valence": -0.6, "arousal": -0.6},
    )
    assert chosen_neg is not None
    assert chosen_neg.sample_id == "low"
    library.close()


def test_arc_phase_mismatch_falls_back_to_character_tags(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    # No "Convergence" samples, but "voice"-tagged candidate exists.
    _add(library, tmp_path, "warm_a", source="library", arc_phase="Emergence",
         tags=frozenset({"warm"}), mood=0.5)
    _add(library, tmp_path, "voicey", source="library", arc_phase="Emergence",
         tags=frozenset({"voice", "harmonic"}), mood=0.5)

    selector = SampleSelector(library, rng_seed=3)
    chosen = selector.select(
        mode=COMPANION,
        arc_phase="Convergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        target_character=("voice",),
    )
    assert chosen is not None
    assert chosen.sample_id == "voicey"
    library.close()


def test_no_arc_no_tags_falls_back_to_random_within_source_preference(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    # Only `room` source samples; arc_phase mismatch; no target_character.
    _add(library, tmp_path, "r1", source="room", arc_phase="Emergence", mood=0.5)
    _add(library, tmp_path, "r2", source="room", arc_phase="Emergence", mood=0.5)

    selector = SampleSelector(library, rng_seed=5)
    chosen = selector.select(
        mode=WORKING_AMBIENCE,
        arc_phase="Crystallization",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert chosen is not None
    assert chosen.sample_id in {"r1", "r2"}
    library.close()


def test_avoid_recent_excludes_last_n_per_mode(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    base = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    # Three indistinguishable samples in the same source with identical mood/arc.
    for i, sid in enumerate(("a", "b", "c")):
        _add(library, tmp_path, sid, source="library", mood=0.5,
             captured_at=base + timedelta(seconds=i))

    selector = SampleSelector(library, rng_seed=42)
    picks: list[str] = []
    for _ in range(3):
        chosen = selector.select(
            mode=COMPANION,
            arc_phase="Emergence",
            mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
            avoid_recent=5,
        )
        assert chosen is not None
        picks.append(chosen.sample_id)
    # All three picks must be distinct since avoid_recent excludes recent picks.
    assert sorted(picks) == ["a", "b", "c"]

    # Recent window is per-mode: a different mode is unaffected.
    storm_pick = selector.select(
        mode=STORM,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        avoid_recent=5,
    )
    assert storm_pick is not None
    assert storm_pick.sample_id in {"a", "b", "c"}
    library.close()


def test_avoid_recent_zero_allows_repeats(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(library, tmp_path, "only", source="library", mood=0.5)

    selector = SampleSelector(library, rng_seed=1)
    picks = [
        selector.select(
            mode=COMPANION,
            arc_phase="Emergence",
            mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
            avoid_recent=0,
        )
        for _ in range(3)
    ]
    assert all(p is not None and p.sample_id == "only" for p in picks)
    library.close()


def test_deterministic_replay_same_seed_and_inputs(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    base = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    # Two samples tied on mood overlap → rng_seed breaks the tie deterministically.
    _add(library, tmp_path, "tieA", source="library", mood=0.5,
         captured_at=base)
    _add(library, tmp_path, "tieB", source="library", mood=0.5,
         captured_at=base + timedelta(seconds=1))

    sel1 = SampleSelector(library, rng_seed=1234)
    sel2 = SampleSelector(library, rng_seed=1234)
    pick1 = sel1.select(
        mode=COMPANION, arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    pick2 = sel2.select(
        mode=COMPANION, arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert pick1 is not None and pick2 is not None
    assert pick1.sample_id == pick2.sample_id

    # Different seeds may pick differently; if they do, they're still each deterministic.
    sel_other = SampleSelector(library, rng_seed=9999)
    pick_other = sel_other.select(
        mode=COMPANION, arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert pick_other is not None
    pick_other2 = SampleSelector(library, rng_seed=9999).select(
        mode=COMPANION, arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert pick_other.sample_id == pick_other2.sample_id
    library.close()


def test_returns_none_when_library_empty(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    selector = SampleSelector(library, rng_seed=1)
    assert selector.select(
        mode=COMPANION,
        arc_phase="Emergence",
        mood={"energy": 0.0, "valence": 0.0, "arousal": 0.0},
    ) is None
    library.close()


def test_returns_none_when_no_source_in_mode_preference(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    # working_ambience preference is [room, library]; theramini is not in the list.
    _add(library, tmp_path, "th", source="theramini", mood=0.5)
    selector = SampleSelector(library, rng_seed=1)
    assert selector.select(
        mode=WORKING_AMBIENCE,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    ) is None
    library.close()


def test_evening_reflection_includes_theramini(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(library, tmp_path, "th", source="theramini", mood=0.5)
    selector = SampleSelector(library, rng_seed=1)
    chosen = selector.select(
        mode=EVENING_REFLECTION,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert chosen is not None
    assert chosen.sample_id == "th"
    library.close()


def test_generated_source_can_be_selected_by_arc_phase(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(
        library,
        tmp_path,
        "gen",
        source="generated",
        arc_phase="E2E-Emergence",
        mood=0.5,
    )
    _add(library, tmp_path, "lib", source="library", arc_phase="Other", mood=0.5)

    chosen = SampleSelector(library, rng_seed=1).select(
        mode=EVENING_REFLECTION,
        arc_phase="E2E-Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )

    assert chosen is not None
    assert chosen.sample_id == "gen"
    library.close()


def test_mode_accepted_as_string_name(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(library, tmp_path, "lib", source="library", mood=0.5)
    selector = SampleSelector(library, rng_seed=1)
    chosen = selector.select(
        mode="companion",
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    )
    assert chosen is not None
    assert chosen.sample_id == "lib"
    library.close()


def test_unknown_mode_returns_none(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(library, tmp_path, "lib", source="library", mood=0.5)
    selector = SampleSelector(library, rng_seed=1)
    assert selector.select(
        mode="not_a_mode",
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
    ) is None
    library.close()


def test_target_character_filters_to_tag_matches(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    _add(library, tmp_path, "warm", source="library",
         tags=frozenset({"warm", "harmonic"}), mood=0.5)
    _add(library, tmp_path, "metallic", source="library",
         tags=frozenset({"metallic", "transient"}), mood=0.5)

    selector = SampleSelector(library, rng_seed=1)
    chosen = selector.select(
        mode=COMPANION,
        arc_phase="Emergence",
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        target_character=("metallic",),
    )
    assert chosen is not None
    assert chosen.sample_id == "metallic"
    library.close()


@pytest.mark.parametrize("avoid_recent", [1, 3, 5])
def test_recent_window_size_scales(tmp_path: Path, avoid_recent: int) -> None:
    library = SampleLibrary(tmp_path)
    base = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
    for i in range(avoid_recent + 2):
        _add(library, tmp_path, f"s{i}", source="library", mood=0.5,
             captured_at=base + timedelta(seconds=i))

    selector = SampleSelector(library, rng_seed=2026)
    seen: list[str] = []
    for _ in range(avoid_recent + 1):
        chosen = selector.select(
            mode=COMPANION,
            arc_phase="Emergence",
            mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
            avoid_recent=avoid_recent,
        )
        assert chosen is not None
        seen.append(chosen.sample_id)
    # Within the window (the first avoid_recent picks), no repeats.
    assert len(set(seen[:avoid_recent])) == avoid_recent
    library.close()
