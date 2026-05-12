"""Tests for manifest-driven sample library imports."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from sample_library_import import main
from senseweave.sample_library import SampleLibrary


def _write_audio(path: Path, payload: bytes = b"audio-bytes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _write_manifest(manifest_path: Path) -> tuple[Path, Path, Path]:
    source_root = manifest_path.parent / "inputs"
    single = _write_audio(source_root / "field notes" / "single voice memo.wav")
    stem_dir = source_root / "song stems"
    drum = _write_audio(stem_dir / "tight kick.wav")
    pad = _write_audio(stem_dir / "warm pad.aif")
    _write_audio(stem_dir / "skip me.wav")
    (stem_dir / "notes.txt").write_text("ignore me")

    manifest_path.write_text(
        "\n".join(
            [
                'captured_by = "anthony"',
                "",
                "[[imports]]",
                'path = "inputs/field notes/single voice memo.wav"',
                'character_tags = ["voice", "noisy"]',
                'extras = { collection = "field-notes" }',
                "",
                "[[imports]]",
                'path = "inputs/song stems"',
                "recursive = true",
                'include = ["*.wav", "*.aif"]',
                'exclude = ["skip*"]',
                'captured_by = "anthony-worker-drive"',
                'character_tags = ["harmonic", "sustained"]',
                'extras = { collection = "song-stems" }',
                "",
            ]
        )
    )
    return single, drum, pad


def test_import_manifest_supports_single_file_and_directory_entries(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    single, drum, pad = _write_manifest(manifest)
    library_root = tmp_path / "samples"

    rc = main([str(manifest), "--library-root", str(library_root)])

    assert rc == 0
    library = SampleLibrary(library_root)
    records = library.find()
    library.close()

    assert len(records) == 3
    originals = {record.extras["original_path"] for record in records}
    assert originals == {str(single.resolve()), str(drum.resolve()), str(pad.resolve())}

    copied_paths = {record.path for record in records}
    assert all(path is not None and path.parent == library_root / "library" for path in copied_paths)
    assert {path.suffix for path in copied_paths} == {".wav", ".aif"}


def test_imported_records_preserve_provenance_extras(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    single, drum, pad = _write_manifest(manifest)
    library_root = tmp_path / "samples"

    rc = main([str(manifest), "--library-root", str(library_root)])

    assert rc == 0
    library = SampleLibrary(library_root)
    records = {record.extras["original_path"]: record for record in library.find()}
    library.close()

    single_record = records[str(single.resolve())]
    assert single_record.character_tags == frozenset({"voice", "noisy"})
    assert single_record.extras == {
        "collection": "field-notes",
        "original_path": str(single.resolve()),
        "captured_by": "anthony",
    }

    for source_path in (str(drum.resolve()), str(pad.resolve())):
        record = records[source_path]
        assert record.character_tags == frozenset({"harmonic", "sustained"})
        assert record.extras == {
            "collection": "song-stems",
            "original_path": source_path,
            "captured_by": "anthony-worker-drive",
        }


def test_main_imports_manifest_and_reports_count(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.toml"
    _write_manifest(manifest)
    library_root = tmp_path / "samples"

    rc = main([str(manifest), "--library-root", str(library_root)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Imported 3 samples" in out
    assert (library_root / "index.sqlite").exists()
    copied = sorted((library_root / "library").iterdir())
    assert len(copied) == 3
