"""Tests for the controlled CHARACTER_TAGS vocabulary, SampleRecord validation, and SampleLibrary store."""
from __future__ import annotations

import os
import sys
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_library import (
    CHARACTER_TAGS,
    SAMPLE_SUBDIRS,
    SOURCE_VALUES,
    SampleLibrary,
    SampleLibraryLayout,
    SampleRecord,
    bootstrap_sample_index,
    create_sample_library_layout,
    init_sample_storage,
)


CANONICAL_TAGS = frozenset(
    {
        "warm",
        "metallic",
        "wind",
        "pulse",
        "voice",
        "mechanical",
        "water",
        "sustained",
        "transient",
        "percussive",
        "harmonic",
        "noisy",
    }
)


def test_character_tags_is_canonical_twelve_tag_frozenset() -> None:
    assert isinstance(CHARACTER_TAGS, frozenset)
    assert len(CHARACTER_TAGS) == 12
    assert CHARACTER_TAGS == CANONICAL_TAGS


def test_sample_record_accepts_known_tags() -> None:
    record = SampleRecord(character_tags=frozenset({"warm", "harmonic"}))
    assert record.character_tags == frozenset({"warm", "harmonic"})


def test_sample_record_rejects_unknown_tag() -> None:
    with pytest.raises(ValueError, match="unknown character_tags"):
        SampleRecord(character_tags=frozenset({"warm", "sparkly"}))


def test_sample_record_rejects_all_unknown_tags() -> None:
    with pytest.raises(ValueError, match="unknown character_tags"):
        SampleRecord(character_tags=frozenset({"sparkly", "buzzy"}))


# ---------------------------------------------------------------------------
# SampleLibrary on-disk store
# ---------------------------------------------------------------------------


def _touch_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48_000)
        w.writeframes(b"\x00\x00")
    return path


def _make_record(
    path: Path,
    *,
    sample_id: str,
    source: str = "human",
    tags: frozenset[str] = frozenset({"warm", "harmonic"}),
    pitch_hz: float | None = 220.0,
    arc_phase: str | None = "Emergence",
    mood: float | None = 0.2,
    captured_at: datetime | None = None,
) -> SampleRecord:
    return SampleRecord(
        character_tags=tags,
        sample_id=sample_id,
        path=path,
        source=source,
        pitch_hz=pitch_hz,
        arc_phase=arc_phase,
        mood=mood,
        captured_at=captured_at or datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
    )


def test_library_creates_index_and_persists_record(tmp_path: Path) -> None:
    wav = _touch_wav(tmp_path / "samples" / "human" / "phrase.wav")
    library = SampleLibrary(tmp_path)
    assert (tmp_path / "index.sqlite").exists()

    sid = library.add(_make_record(wav, sample_id="s1"))
    assert sid == "s1"

    rows = library.find()
    assert len(rows) == 1
    assert rows[0].sample_id == "s1"
    assert rows[0].path == wav
    assert rows[0].character_tags == frozenset({"warm", "harmonic"})
    library.close()


def test_library_add_rejects_missing_file(tmp_path: Path) -> None:
    library = SampleLibrary(tmp_path)
    ghost = tmp_path / "samples" / "human" / "ghost.wav"
    with pytest.raises(FileNotFoundError):
        library.add(_make_record(ghost, sample_id="ghost"))
    library.close()


def test_library_filters_by_each_field(tmp_path: Path) -> None:
    wavs = [_touch_wav(tmp_path / "samples" / f"s{i}.wav") for i in range(4)]
    library = SampleLibrary(tmp_path)
    base = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)

    library.add(_make_record(
        wavs[0], sample_id="a", source="human",
        tags=frozenset({"warm", "harmonic"}),
        pitch_hz=220.0, arc_phase="Emergence", mood=0.4,
        captured_at=base,
    ))
    library.add(_make_record(
        wavs[1], sample_id="b", source="library",
        tags=frozenset({"metallic", "transient"}),
        pitch_hz=880.0, arc_phase="Convergence", mood=-0.3,
        captured_at=base + timedelta(seconds=1),
    ))
    library.add(_make_record(
        wavs[2], sample_id="c", source="human",
        tags=frozenset({"warm", "voice"}),
        pitch_hz=440.0, arc_phase="Convergence", mood=0.1,
        captured_at=base + timedelta(seconds=2),
    ))
    library.add(_make_record(
        wavs[3], sample_id="d", source="self",
        tags=frozenset({"pulse", "percussive", "noisy"}),
        pitch_hz=110.0, arc_phase="Emergence", mood=0.8,
        captured_at=base + timedelta(seconds=3),
    ))

    by_source = [r.sample_id for r in library.find(source="human")]
    assert by_source == ["c", "a"]  # most-recent-first

    any_warm = {r.sample_id for r in library.find(character_any=["warm"])}
    assert any_warm == {"a", "c"}

    all_pulse_perc = [r.sample_id for r in library.find(character_all=["pulse", "percussive"])]
    assert all_pulse_perc == ["d"]

    pitch_mid = [r.sample_id for r in library.find(pitch_band=(200.0, 500.0))]
    assert pitch_mid == ["c", "a"]

    by_phase = [r.sample_id for r in library.find(arc_phase="Convergence")]
    assert by_phase == ["c", "b"]

    by_mood = [r.sample_id for r in library.find(mood_range=(0.0, 0.5))]
    assert by_mood == ["c", "a"]

    limited = [r.sample_id for r in library.find(limit=2)]
    assert limited == ["d", "c"]

    library.close()


def test_source_values_includes_generated() -> None:
    assert "generated" in SOURCE_VALUES


def test_library_round_trip_with_generated_source(tmp_path: Path) -> None:
    wav = _touch_wav(tmp_path / "samples" / "generated" / "g1.wav")
    library = SampleLibrary(tmp_path)
    library.add(_make_record(
        wav, sample_id="gen1", source="generated",
        tags=frozenset({"warm"}),
    ))
    library.add(_make_record(
        wav, sample_id="hum1", source="human",
        tags=frozenset({"warm"}),
    ))

    found = library.find(source="generated")
    assert [r.sample_id for r in found] == ["gen1"]
    assert found[0].source == "generated"
    assert found[0].path == wav
    library.close()


def test_sample_record_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        SampleRecord(character_tags=frozenset({"warm"}), source="bogus")


def test_library_find_empty_result(tmp_path: Path) -> None:
    wav = _touch_wav(tmp_path / "s.wav")
    library = SampleLibrary(tmp_path)
    library.add(_make_record(wav, sample_id="only", source="human"))

    assert library.find(source="theramini") == []
    assert library.find(arc_phase="Crystallization") == []
    assert library.find(character_all=["wind", "water"]) == []
    assert library.find(pitch_band=(2000.0, 3000.0)) == []
    assert library.find(mood_range=(-1.0, -0.9)) == []
    library.close()


# ---------------------------------------------------------------------------
# create_sample_library_layout
# ---------------------------------------------------------------------------


EXPECTED_SUBDIRS = ("library", "self", "room", "contact", "theramini", "keyboard")


def test_sample_subdirs_constant_matches_spec() -> None:
    assert SAMPLE_SUBDIRS == EXPECTED_SUBDIRS


def test_create_sample_library_layout_creates_all_six_subdirs(tmp_path: Path) -> None:
    base = tmp_path / "samples"
    layout = create_sample_library_layout(base)

    assert isinstance(layout, SampleLibraryLayout)
    assert layout.base == base
    assert base.is_dir()
    for name in EXPECTED_SUBDIRS:
        assert (base / name).is_dir()
    assert layout.as_dict() == {name: base / name for name in EXPECTED_SUBDIRS}


def test_create_sample_library_layout_accepts_str_base(tmp_path: Path) -> None:
    base = tmp_path / "samples"
    layout = create_sample_library_layout(str(base))
    assert layout.base == Path(str(base))
    assert layout.library == base / "library"


def test_create_sample_library_layout_is_idempotent(tmp_path: Path) -> None:
    base = tmp_path / "samples"
    first = create_sample_library_layout(base)
    sentinel = first.library / "keep.txt"
    sentinel.write_text("preserved")

    second = create_sample_library_layout(base)
    assert second == first
    assert sentinel.read_text() == "preserved"


def test_create_sample_library_layout_creates_missing_parents(tmp_path: Path) -> None:
    base = tmp_path / "deep" / "nested" / "samples"
    layout = create_sample_library_layout(base)
    assert base.is_dir()
    assert layout.theramini.is_dir()


def test_create_sample_library_layout_rejects_file_at_subdir_path(tmp_path: Path) -> None:
    base = tmp_path / "samples"
    base.mkdir()
    (base / "room").write_text("oops")
    with pytest.raises(NotADirectoryError):
        create_sample_library_layout(base)


def test_create_sample_library_layout_rejects_file_at_base(tmp_path: Path) -> None:
    base = tmp_path / "samples"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text("not a dir")
    with pytest.raises((NotADirectoryError, FileExistsError)):
        create_sample_library_layout(base)


def test_library_rebuilds_corrupted_index(tmp_path: Path) -> None:
    wav = _touch_wav(tmp_path / "x.wav")
    library = SampleLibrary(tmp_path)
    library.add(_make_record(wav, sample_id="pre"))
    library.close()

    db = tmp_path / "index.sqlite"
    db.write_bytes(b"this is not a sqlite database")

    rebuilt = SampleLibrary(tmp_path)
    assert rebuilt.find() == []
    rebuilt.add(_make_record(wav, sample_id="post"))
    assert [r.sample_id for r in rebuilt.find()] == ["post"]
    rebuilt.close()


def test_bootstrap_sample_index(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    bootstrap_sample_index(db_path)
    
    assert db_path.exists()
    
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "schema_version" in tables
        assert "samples" in tables
        
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 1


def test_bootstrap_sample_index_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    bootstrap_sample_index(db_path)
    bootstrap_sample_index(db_path)
    
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert count == 1


def test_init_sample_storage_bootstraps_layout_and_index(tmp_path: Path) -> None:
    layout = init_sample_storage(tmp_path / "samples")

    assert isinstance(layout, SampleLibraryLayout)
    assert layout.base == tmp_path / "samples"
    for name in EXPECTED_SUBDIRS:
        assert (layout.base / name).is_dir()

    db_path = layout.base / "index.sqlite"
    assert db_path.exists()

    import sqlite3
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "schema_version" in tables
        assert "samples" in tables
