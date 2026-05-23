from __future__ import annotations

from pathlib import Path

from cypherclaw import midi_vocabulary_store as store
from cypherclaw.composer_vocabulary_bridge import (
    load_vocabulary_fragments,
    plan_vocabulary_citations,
    scene_vocabulary_log_suffix,
)


def _populate_vocabulary_db(tmp_path: Path) -> tuple[Path, int]:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        fragment_id = store.insert_fragment(
            conn,
            source_file="seed.mid",
            kind="melodic_motif",
            interval_pattern=[2, 2, 3],
            duration_pattern=[1.0, 0.5, 0.5, 2.0],
            source_key="C major",
            source_tempo=120.0,
            harmonic_context={"pitch_classes": [0, 2, 4, 7]},
        )
        store.insert_fragment(
            conn,
            source_file="groove.mid",
            kind="rhythm_cell",
            interval_pattern=[1.0, 0.5, 0.5, 2.0],
            duration_pattern=[1.0, 0.5, 0.5, 2.0],
            source_key="C major",
            source_tempo=118.0,
        )
    finally:
        conn.close()
    return db_path, fragment_id


def test_load_vocabulary_fragments_derives_composer_material(tmp_path: Path) -> None:
    db_path, fragment_id = _populate_vocabulary_db(tmp_path)

    fragments = load_vocabulary_fragments(db_path)

    motif = next(fragment for fragment in fragments if fragment.kind == "melodic_motif")
    assert motif.fragment_id == fragment_id
    assert motif.source_file == "seed.mid"
    assert motif.degree_pattern == (1, 2, 3, 5)
    assert motif.duration_pattern == (1.0, 0.5, 0.5, 2.0)
    assert motif.source_key == "C major"


def test_plan_vocabulary_citations_rate_tracks_curiosity(tmp_path: Path) -> None:
    db_path, fragment_id = _populate_vocabulary_db(tmp_path)
    fragments = load_vocabulary_fragments(db_path)
    scene_names = tuple(f"Scene-{index:03d}" for index in range(1000))

    none = plan_vocabulary_citations(
        scene_names,
        fragments,
        curiosity=0.0,
        seed="t-016-rate",
    )
    all_cited = plan_vocabulary_citations(
        scene_names,
        fragments,
        curiosity=1.0,
        seed="t-016-rate",
    )
    quarter = plan_vocabulary_citations(
        scene_names,
        fragments,
        curiosity=0.25,
        seed="t-016-rate",
    )

    assert none == {}
    assert set(all_cited) == set(scene_names)
    assert all_cited[scene_names[0]].fragment_id in {fragment.fragment_id for fragment in fragments}
    assert all_cited[scene_names[0]].to_scene_metadata()["vocabulary_fragment_id"]
    assert any(citation.fragment_id == fragment_id for citation in all_cited.values())
    assert 0.20 <= len(quarter) / len(scene_names) <= 0.30


def test_scene_vocabulary_log_suffix_names_cited_fragment(tmp_path: Path) -> None:
    db_path, _fragment_id = _populate_vocabulary_db(tmp_path)
    fragments = load_vocabulary_fragments(db_path)
    citations = plan_vocabulary_citations(
        ("Theme",),
        fragments,
        curiosity=1.0,
        seed="t-016-log",
    )
    metadata = citations["Theme"].to_scene_metadata()

    suffix = scene_vocabulary_log_suffix(metadata)

    assert f"vocabulary_fragment_id={metadata['vocabulary_fragment_id']}" in suffix
    assert "vocabulary_fragment_kind=melodic_motif" in suffix
