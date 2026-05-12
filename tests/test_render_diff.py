"""Tests for the score diff / comparison utility."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generative_scores import Note, Phrase, Score
from senseweave.render.diff import diff_scores


def _phrase(
    notes: list[Note],
    *,
    dynamic: str = "mf",
    voice: str = "pluck",
    role: str = "melody",
) -> Phrase:
    return Phrase(notes=notes, voice=voice, dynamic=dynamic, role=role)


def _score(
    phrases: list[Phrase],
    *,
    key: str = "C",
    tempo: float = 120.0,
) -> Score:
    return Score(
        phrases=phrases,
        key=key,
        tempo_bpm=tempo,
        mood="neutral",
        created_at=0.0,
    )


class TestDiffIdentical:
    def test_identical_scores_produce_empty_delta(self) -> None:
        phrase = _phrase([Note(1, 1.0, False), Note(3, 0.5, True)])
        s = _score([phrase])
        delta = diff_scores(s, s)
        assert delta.empty
        assert delta.summary() == "no changes"


class TestNoteChanges:
    def test_scale_degree_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])])
        ablated = _score([_phrase([Note(5, 1.0, False)])])
        delta = diff_scores(orig, ablated)
        assert len(delta.note_changes) == 1
        nd = delta.note_changes[0]
        assert nd.field == "scale_degree"
        assert nd.original == 1
        assert nd.ablated == 5

    def test_duration_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])])
        ablated = _score([_phrase([Note(1, 2.0, False)])])
        delta = diff_scores(orig, ablated)
        assert len(delta.note_changes) == 1
        assert delta.note_changes[0].field == "duration_beats"

    def test_accent_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])])
        ablated = _score([_phrase([Note(1, 1.0, True)])])
        delta = diff_scores(orig, ablated)
        assert len(delta.note_changes) == 1
        assert delta.note_changes[0].field == "accent"

    def test_multiple_note_changes_across_phrases(self) -> None:
        orig = _score([
            _phrase([Note(1, 1.0, False), Note(2, 1.0, False)]),
            _phrase([Note(3, 1.0, True)]),
        ])
        ablated = _score([
            _phrase([Note(1, 1.0, False), Note(4, 1.0, False)]),
            _phrase([Note(3, 0.5, True)]),
        ])
        delta = diff_scores(orig, ablated)
        assert len(delta.note_changes) == 2
        assert delta.note_changes[0].phrase_index == 0
        assert delta.note_changes[0].note_index == 1
        assert delta.note_changes[1].phrase_index == 1
        assert delta.note_changes[1].field == "duration_beats"


class TestNoteCountMismatch:
    def test_removed_notes_reported(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False), Note(2, 1.0, True)])])
        ablated = _score([_phrase([Note(1, 1.0, False)])])
        delta = diff_scores(orig, ablated)
        removed = [nd for nd in delta.note_changes if nd.ablated is None]
        assert len(removed) == 3  # scale_degree, duration_beats, accent

    def test_added_notes_reported(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])])
        ablated = _score([_phrase([Note(1, 1.0, False), Note(5, 0.5, True)])])
        delta = diff_scores(orig, ablated)
        added = [nd for nd in delta.note_changes if nd.original is None]
        assert len(added) == 3


class TestPhraseChanges:
    def test_dynamic_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)], dynamic="pp")])
        ablated = _score([_phrase([Note(1, 1.0, False)], dynamic="ff")])
        delta = diff_scores(orig, ablated)
        assert len(delta.phrase_changes) == 1
        pd = delta.phrase_changes[0]
        assert pd.field == "dynamic"
        assert pd.original == "pp"
        assert pd.ablated == "ff"

    def test_voice_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)], voice="pluck")])
        ablated = _score([_phrase([Note(1, 1.0, False)], voice="pad")])
        delta = diff_scores(orig, ablated)
        assert any(pd.field == "voice" for pd in delta.phrase_changes)

    def test_role_change_detected(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)], role="melody")])
        ablated = _score([_phrase([Note(1, 1.0, False)], role="bass")])
        delta = diff_scores(orig, ablated)
        assert any(pd.field == "role" for pd in delta.phrase_changes)


class TestPhraseCountMismatch:
    def test_removed_phrases_indexed(self) -> None:
        orig = _score([
            _phrase([Note(1, 1.0, False)]),
            _phrase([Note(2, 1.0, False)]),
            _phrase([Note(3, 1.0, False)]),
        ])
        ablated = _score([_phrase([Note(1, 1.0, False)])])
        delta = diff_scores(orig, ablated)
        assert delta.removed_phrases == (1, 2)

    def test_added_phrases_indexed(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])])
        ablated = _score([
            _phrase([Note(1, 1.0, False)]),
            _phrase([Note(5, 1.0, True)]),
        ])
        delta = diff_scores(orig, ablated)
        assert delta.added_phrases == (1,)


class TestGlobalChanges:
    def test_tempo_delta(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])], tempo=120.0)
        ablated = _score([_phrase([Note(1, 1.0, False)])], tempo=130.0)
        delta = diff_scores(orig, ablated)
        assert delta.tempo_delta == 10.0
        assert not delta.empty

    def test_key_change(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])], key="C")
        ablated = _score([_phrase([Note(1, 1.0, False)])], key="Am")
        delta = diff_scores(orig, ablated)
        assert delta.key_changed
        assert not delta.empty


class TestSummary:
    def test_summary_includes_all_categories(self) -> None:
        orig = _score(
            [
                _phrase([Note(1, 1.0, False), Note(2, 0.5, True)], dynamic="mp"),
                _phrase([Note(3, 1.0, False)]),
            ],
            key="C",
            tempo=100.0,
        )
        ablated = _score(
            [_phrase([Note(1, 2.0, False), Note(4, 0.5, True)], dynamic="ff")],
            key="G",
            tempo=110.0,
        )
        delta = diff_scores(orig, ablated)
        s = delta.summary()
        assert "key changed" in s
        assert "tempo +10.0 bpm" in s
        assert "1 phrase(s) removed" in s
        assert "dynamic change" in s
        assert "note" in s

    def test_tempo_decrease_shows_negative(self) -> None:
        orig = _score([_phrase([Note(1, 1.0, False)])], tempo=120.0)
        ablated = _score([_phrase([Note(1, 1.0, False)])], tempo=100.0)
        delta = diff_scores(orig, ablated)
        assert "tempo -20.0 bpm" in delta.summary()
