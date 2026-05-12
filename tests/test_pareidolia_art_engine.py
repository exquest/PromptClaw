"""Tests for PARE-005 pareidolia_art_engine module."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))


from senseweave.pareidolia_art_engine import (
    _read_organism_state,
    generate_art_piece,
)


# ---------------------------------------------------------------------------
# _read_organism_state
# ---------------------------------------------------------------------------


def test_read_organism_state_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(tmp_path / "no_such_file.json"),
    )
    state = _read_organism_state()
    assert "organism_mood" in state
    assert state["organism_mood"]["energy"] == pytest.approx(0.4)


def test_read_organism_state_returns_defaults_on_bad_json(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("NOT JSON{{{")
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(bad),
    )
    state = _read_organism_state()
    assert "organism_mood" in state


def test_read_organism_state_parses_valid_file(tmp_path, monkeypatch):
    good = tmp_path / "state.json"
    good.write_text(json.dumps({
        "organism_mood": {"energy": 0.9, "valence": 0.8, "arousal": 0.7},
    }))
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(good),
    )
    state = _read_organism_state()
    assert state["organism_mood"]["energy"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# generate_art_piece
# ---------------------------------------------------------------------------


def test_generate_art_piece_creates_png_and_sidecar(tmp_path, monkeypatch):
    """generate_art_piece should produce a .png and matching .json sidecar."""
    # Stub organism state to defaults (no file)
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(tmp_path / "missing.json"),
    )
    gallery = str(tmp_path / "gallery")
    path = generate_art_piece(gallery_dir=gallery)

    assert path.endswith(".png")
    assert os.path.isfile(path)

    # JSON sidecar should exist next to the PNG
    json_path = path.replace(".png", ".json")
    assert os.path.isfile(json_path)

    with open(json_path) as f:
        meta = json.load(f)
    assert "title" in meta
    assert "mood_tag" in meta


def test_generate_art_piece_uses_organism_mood(tmp_path, monkeypatch):
    """When organism state exists, the mood should flow through to scene composition."""
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "organism_mood": {"energy": 0.9, "valence": 0.9, "arousal": 0.8},
    }))
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(state_file),
    )
    gallery = str(tmp_path / "gallery2")
    path = generate_art_piece(gallery_dir=gallery)

    assert os.path.isfile(path)

    json_path = path.replace(".png", ".json")
    with open(json_path) as f:
        meta = json.load(f)
    # High-energy mood should produce multiple characters
    assert len(meta.get("characters", [])) >= 2


def test_generate_art_piece_creates_gallery_dir(tmp_path, monkeypatch):
    """Gallery directory should be created automatically if missing."""
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(tmp_path / "nope.json"),
    )
    gallery = str(tmp_path / "deep" / "nested" / "gallery")
    path = generate_art_piece(gallery_dir=gallery)
    assert os.path.isdir(gallery)
    assert os.path.isfile(path)


def test_generate_art_piece_calls_scene_composer(tmp_path, monkeypatch):
    """Verify the pipeline flows through compose_scene -> render -> save."""
    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.ORGANISM_STATE_PATH",
        str(tmp_path / "nope.json"),
    )

    from senseweave import scene_composer as sc
    original_compose = sc.compose_scene
    compose_called = []

    def tracking_compose(**kwargs):
        compose_called.append(kwargs)
        return original_compose(**kwargs)

    monkeypatch.setattr(
        "senseweave.pareidolia_art_engine.compose_scene",
        tracking_compose,
    )

    gallery = str(tmp_path / "gallery_track")
    generate_art_piece(gallery_dir=gallery)

    assert len(compose_called) == 1
    assert "mood" in compose_called[0]
