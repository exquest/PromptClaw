import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))
import pytest

from types import SimpleNamespace

from senseweave.usage_journal import (
    JournalEntry,
    SamplePlay,
    SampleUsageTracker,
    append_to_journal,
    derive_arc_payoff_summary,
    post_piece_hook,
    read_journal,
    record_scheduled_sample_event,
)


def _sample_event(metadata=None, scene_metadata=None, row=0, scene_name="Scene"):
    return SimpleNamespace(
        role="sample",
        metadata=metadata or {},
        scene_metadata=scene_metadata or {},
        scene_name=scene_name,
        row=row,
        voice="sample",
    )

def test_journal_entry_serialization():
    # Arrange
    samples = [
        SamplePlay(
            sample_id="bd_808",
            source="kick_pack",
            transposition=0,
            fx_preset="punchy",
            played_at_row=0
        ),
        SamplePlay(
            sample_id="sn_909",
            source="snare_pack",
            transposition=-2,
            fx_preset="reverb_heavy",
            played_at_row=4
        )
    ]
    entry = JournalEntry(
        piece_id="piece-123",
        timestamp="2026-04-25T19:00:00Z",
        samples_played=samples,
        arc_payoff="Massive drop with double-time snare build"
    )

    # Act
    entry_dict = entry.to_dict()
    reconstructed_entry = JournalEntry.from_dict(entry_dict)

    # Assert
    assert reconstructed_entry.piece_id == "piece-123"
    assert reconstructed_entry.timestamp == "2026-04-25T19:00:00Z"
    assert reconstructed_entry.arc_payoff == "Massive drop with double-time snare build"
    assert len(reconstructed_entry.samples_played) == 2
    assert reconstructed_entry.samples_played[0].sample_id == "bd_808"
    assert reconstructed_entry.samples_played[0].played_at_row == 0
    assert reconstructed_entry.samples_played[1].sample_id == "sn_909"


def test_sample_play_round_trips_source_kind():
    sample = SamplePlay(
        sample_id="gesture_1",
        source="contact_mic",
        source_kind="gesture",
        transposition=7,
        fx_preset="grain_cloud",
        played_at_row=8,
        transformations=["slice_rearrange", "granular_cloud"],
    )

    payload = sample.to_dict()
    restored = SamplePlay.from_dict(payload)

    assert payload["source"] == "contact_mic"
    assert payload["source_kind"] == "gesture"
    assert restored == sample


def test_append_and_read_journal(tmp_path):
    # Arrange
    journal_path = tmp_path / "usage_journal.jsonl"
    
    samples = [
        SamplePlay(
            sample_id="hihat",
            source="cymbals",
            transposition=0,
            fx_preset="none",
            played_at_row=2
        )
    ]
    entry1 = JournalEntry(
        piece_id="piece-1",
        timestamp="2026-04-25T19:01:00Z",
        samples_played=samples,
        arc_payoff="Light introduction"
    )
    
    entry2 = JournalEntry(
        piece_id="piece-2",
        timestamp="2026-04-25T19:05:00Z",
        samples_played=[],
        arc_payoff="Ambient section"
    )

    # Act
    append_to_journal(entry1, path=journal_path)
    append_to_journal(entry2, path=journal_path)
    
    entries = read_journal(path=journal_path)

    # Assert
    assert len(entries) == 2
    assert entries[0].piece_id == "piece-1"
    assert entries[0].arc_payoff == "Light introduction"
    assert len(entries[0].samples_played) == 1
    assert entries[0].samples_played[0].sample_id == "hihat"
    
    assert entries[1].piece_id == "piece-2"
    assert entries[1].arc_payoff == "Ambient section"
    assert len(entries[1].samples_played) == 0

    # Ensure it is written as valid JSONL
    with open(journal_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        data1 = json.loads(lines[0])
        assert data1["piece_id"] == "piece-1"
        data2 = json.loads(lines[1])
        assert data2["piece_id"] == "piece-2"


def test_tracker_accumulates_sample_plays_in_order():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-7", timestamp="2026-04-25T19:10:00Z")
    assert tracker.is_active
    assert tracker.samples_played == []

    tracker.record_play(
        sample_id="bd_808",
        source="kick_pack",
        transposition=0,
        fx_preset="punchy",
        played_at_row=0,
    )
    tracker.record_play(
        sample_id="sn_909",
        source="snare_pack",
        transposition=-2,
        fx_preset="reverb_heavy",
        played_at_row=4,
    )
    tracker.record_play(
        sample_id="hihat",
        source="cymbals",
        transposition=3,
        fx_preset="lp_filter",
        played_at_row=6,
    )

    assert len(tracker.samples_played) == 3
    assert tracker.samples_played[0].sample_id == "bd_808"
    assert tracker.samples_played[1].transposition == -2
    assert tracker.samples_played[2].fx_preset == "lp_filter"
    assert tracker.samples_played[2].played_at_row == 6


def test_tracker_finish_piece_returns_journal_entry_and_resets():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-8", timestamp="2026-04-25T19:11:00Z")
    tracker.record_play(
        sample_id="pad_lush",
        source="texture_pack",
        transposition=5,
        fx_preset="long_verb",
        played_at_row=0,
    )

    entry = tracker.finish_piece(arc_payoff="Slow build into pad bloom")

    assert isinstance(entry, JournalEntry)
    assert entry.piece_id == "piece-8"
    assert entry.timestamp == "2026-04-25T19:11:00Z"
    assert entry.arc_payoff == "Slow build into pad bloom"
    assert len(entry.samples_played) == 1
    assert entry.samples_played[0].sample_id == "pad_lush"
    assert entry.samples_played[0].transposition == 5

    # Tracker resets after finishing so the next piece starts clean.
    assert not tracker.is_active
    assert tracker.samples_played == []


def test_tracker_finish_piece_snapshot_independent_of_subsequent_recording():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-9", timestamp="2026-04-25T19:12:00Z")
    tracker.record_play(
        sample_id="bell",
        source="metallic",
        transposition=0,
        fx_preset="shimmer",
        played_at_row=2,
    )
    entry = tracker.finish_piece(arc_payoff="Single bell tone")

    tracker.start_piece(piece_id="piece-10", timestamp="2026-04-25T19:13:00Z")
    tracker.record_play(
        sample_id="rumble",
        source="lf_pack",
        transposition=-12,
        fx_preset="dark",
        played_at_row=0,
    )

    # The first entry's samples list must not be mutated by later activity.
    assert len(entry.samples_played) == 1
    assert entry.samples_played[0].sample_id == "bell"
    assert entry.piece_id == "piece-9"


def test_tracker_supports_multiple_pieces_back_to_back():
    tracker = SampleUsageTracker()

    tracker.start_piece(piece_id="piece-A", timestamp="2026-04-25T19:14:00Z")
    tracker.record_play(
        sample_id="a1",
        source="src_a",
        transposition=0,
        fx_preset="dry",
        played_at_row=0,
    )
    tracker.record_play(
        sample_id="a2",
        source="src_a",
        transposition=2,
        fx_preset="dry",
        played_at_row=4,
    )
    entry_a = tracker.finish_piece(arc_payoff="A done")

    tracker.start_piece(piece_id="piece-B", timestamp="2026-04-25T19:15:00Z")
    tracker.record_play(
        sample_id="b1",
        source="src_b",
        transposition=-1,
        fx_preset="wet",
        played_at_row=1,
    )
    entry_b = tracker.finish_piece(arc_payoff="B done")

    assert [sp.sample_id for sp in entry_a.samples_played] == ["a1", "a2"]
    assert [sp.sample_id for sp in entry_b.samples_played] == ["b1"]
    assert entry_a.arc_payoff == "A done"
    assert entry_b.arc_payoff == "B done"


def test_tracker_record_play_before_start_raises():
    tracker = SampleUsageTracker()
    with pytest.raises(RuntimeError):
        tracker.record_play(
            sample_id="x",
            source="y",
            transposition=0,
            fx_preset="none",
            played_at_row=0,
        )


def test_tracker_finish_piece_before_start_raises():
    tracker = SampleUsageTracker()
    with pytest.raises(RuntimeError):
        tracker.finish_piece(arc_payoff="never started")


def test_tracker_entry_round_trips_through_journal(tmp_path):
    journal_path = tmp_path / "usage_journal.jsonl"
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-rt", timestamp="2026-04-25T19:16:00Z")
    tracker.record_play(
        sample_id="kick",
        source="drum_kit",
        transposition=0,
        fx_preset="punchy",
        played_at_row=0,
    )
    tracker.record_play(
        sample_id="snare",
        source="drum_kit",
        source_kind="generated",
        transposition=-1,
        fx_preset="reverb",
        played_at_row=4,
    )
    entry = tracker.finish_piece(arc_payoff="Round trip")

    append_to_journal(entry, path=journal_path)
    read_back = read_journal(path=journal_path)

    assert len(read_back) == 1
    restored = read_back[0]
    assert restored.piece_id == "piece-rt"
    assert [sp.sample_id for sp in restored.samples_played] == ["kick", "snare"]
    assert restored.samples_played[1].transposition == -1
    assert restored.samples_played[1].fx_preset == "reverb"
    assert restored.samples_played[1].source_kind == "generated"


def test_derive_arc_payoff_summary_bands():
    assert derive_arc_payoff_summary(arc_payoff_score=0.0, sample_count=0).startswith("weak")
    assert derive_arc_payoff_summary(arc_payoff_score=0.29, sample_count=2).startswith("weak")
    assert derive_arc_payoff_summary(arc_payoff_score=0.3, sample_count=2).startswith("moderate")
    assert derive_arc_payoff_summary(arc_payoff_score=0.59, sample_count=4).startswith("moderate")
    assert derive_arc_payoff_summary(arc_payoff_score=0.6, sample_count=4).startswith("strong")
    assert derive_arc_payoff_summary(arc_payoff_score=1.0, sample_count=7).startswith("strong")
    summary = derive_arc_payoff_summary(arc_payoff_score=0.42, sample_count=3)
    assert "0.42" in summary
    assert "3 sample" in summary


def test_post_piece_hook_writes_journal_entry(tmp_path):
    journal_path = tmp_path / "usage_journal.jsonl"
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-hook", timestamp="2026-04-25T19:20:00Z")
    tracker.record_play(
        sample_id="bd",
        source="kick_pack",
        transposition=0,
        fx_preset="punchy",
        played_at_row=0,
    )
    tracker.record_play(
        sample_id="sn",
        source="snare_pack",
        transposition=-2,
        fx_preset="reverb",
        played_at_row=4,
    )

    entry = post_piece_hook(
        tracker,
        arc_payoff_score=0.75,
        journal_path=journal_path,
    )

    assert isinstance(entry, JournalEntry)
    assert entry.piece_id == "piece-hook"
    assert [sp.sample_id for sp in entry.samples_played] == ["bd", "sn"]
    assert entry.arc_payoff.startswith("strong")
    assert "0.75" in entry.arc_payoff
    assert "2 sample" in entry.arc_payoff

    # Tracker is reset after hook runs.
    assert not tracker.is_active
    assert tracker.samples_played == []

    # Entry was actually written to disk.
    on_disk = read_journal(path=journal_path)
    assert len(on_disk) == 1
    assert on_disk[0].piece_id == "piece-hook"
    assert on_disk[0].arc_payoff == entry.arc_payoff
    assert [sp.sample_id for sp in on_disk[0].samples_played] == ["bd", "sn"]


def test_post_piece_hook_appends_across_pieces(tmp_path):
    journal_path = tmp_path / "usage_journal.jsonl"
    tracker = SampleUsageTracker()

    tracker.start_piece(piece_id="piece-1", timestamp="2026-04-25T19:21:00Z")
    tracker.record_play(
        sample_id="a", source="src", transposition=0, fx_preset="dry", played_at_row=0,
    )
    post_piece_hook(tracker, arc_payoff_score=0.1, journal_path=journal_path)

    tracker.start_piece(piece_id="piece-2", timestamp="2026-04-25T19:22:00Z")
    post_piece_hook(tracker, arc_payoff_score=0.9, journal_path=journal_path)

    entries = read_journal(path=journal_path)
    assert [e.piece_id for e in entries] == ["piece-1", "piece-2"]
    assert entries[0].arc_payoff.startswith("weak")
    assert entries[1].arc_payoff.startswith("strong")
    assert len(entries[1].samples_played) == 0


def test_post_piece_hook_without_active_piece_raises(tmp_path):
    journal_path = tmp_path / "usage_journal.jsonl"
    tracker = SampleUsageTracker()
    with pytest.raises(RuntimeError):
        post_piece_hook(tracker, arc_payoff_score=0.5, journal_path=journal_path)
    assert not journal_path.exists()


def test_record_scheduled_sample_event_uses_explicit_sample_origin():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-origin", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(metadata={"sample_origin": "self_quote"})

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "self_quote"


def test_record_scheduled_sample_event_falls_back_to_scene_sample_origin():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-scene-origin", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(scene_metadata={"sample_origin": "field_recording"})

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "field_recording"


def test_record_scheduled_sample_event_marks_generated_from_generated_by():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-gen", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(metadata={"generated_by": "korsakov_composer"})

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "generated"


def test_record_scheduled_sample_event_marks_library_from_library_path():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-lib", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(metadata={"library_path": "samples/library/grain_a.wav"})

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "library"


def test_record_scheduled_sample_event_defaults_source_kind_to_gesture():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-default", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(metadata={"sample_gesture_source": "contact_mic"})

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "gesture"


def test_record_scheduled_sample_event_explicit_origin_beats_other_signals():
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id="piece-priority", timestamp="2026-04-27T00:00:00Z")
    event = _sample_event(
        metadata={
            "sample_origin": "self_quote",
            "generated_by": "korsakov_composer",
            "library_path": "samples/library/x.wav",
        }
    )

    play = record_scheduled_sample_event(tracker, event)

    assert play is not None
    assert play.source_kind == "self_quote"


def test_read_journal_legacy_entries_default_source_kind_to_unknown(tmp_path):
    """Legacy journal entries written before the source_kind feature must
    still parse, with missing source_kind defaulted to 'unknown'."""
    journal_path = tmp_path / "usage_journal.jsonl"
    legacy_entry = {
        "piece_id": "legacy-piece",
        "timestamp": "2026-04-01T12:00:00Z",
        "started_at": "2026-04-01T12:00:00Z",
        "mode": "evening_reflection",
        "samples_played": [
            {
                "sample_id": "legacy-kick",
                "source": "drum_kit",
                "transposition": 0,
                "fx_preset": "punchy",
                "played_at_row": 0,
            },
            {
                "sample_id": "legacy-snare",
                "source": "drum_kit",
                "transposition": -1,
                "fx_preset": "reverb",
                "played_at_row": 4,
            },
        ],
        "transformations": [],
        "arc_payoff": "moderate payoff (score=0.40) over 2 sample(s)",
        "clicks": 0,
    }
    journal_path.write_text(json.dumps(legacy_entry) + "\n", encoding="utf-8")

    entries = read_journal(path=journal_path)

    assert len(entries) == 1
    restored = entries[0]
    assert restored.piece_id == "legacy-piece"
    assert [sp.sample_id for sp in restored.samples_played] == [
        "legacy-kick",
        "legacy-snare",
    ]
    assert all(sp.source_kind == "unknown" for sp in restored.samples_played)


def test_read_journal_treats_empty_source_kind_as_unknown(tmp_path):
    """An entry with an explicit empty string source_kind is also treated as
    unknown — no in-memory SamplePlay should carry an empty source_kind once
    it's been through the journal."""
    journal_path = tmp_path / "usage_journal.jsonl"
    entry_with_empty = {
        "piece_id": "empty-piece",
        "timestamp": "2026-04-02T12:00:00Z",
        "samples_played": [
            {
                "sample_id": "blank",
                "source": "drum_kit",
                "source_kind": "",
                "transposition": 0,
                "fx_preset": "dry",
                "played_at_row": 0,
            }
        ],
        "arc_payoff": "weak payoff (score=0.10) over 1 sample(s)",
    }
    journal_path.write_text(json.dumps(entry_with_empty) + "\n", encoding="utf-8")

    entries = read_journal(path=journal_path)

    assert len(entries) == 1
    assert entries[0].samples_played[0].source_kind == "unknown"


def test_journal_entry_serializes_ccs028_fields_with_legacy_aliases():
    sample = SamplePlay(
        sample_id="self-quote-1",
        source="self",
        transposition=-2,
        fx_preset="evening_reflection",
        played_at_row=12,
    )
    entry = JournalEntry(
        piece_id="piece-ccs028",
        timestamp="2026-04-25T19:30:00Z",
        samples_played=[sample],
        arc_payoff="strong payoff (score=0.72) over 1 sample(s)",
        mode="evening_reflection",
        transformations=["slice_rearrange", "pitch_window"],
        clicks=1,
    )

    payload = entry.to_dict()

    assert payload["timestamp"] == "2026-04-25T19:30:00Z"
    assert payload["started_at"] == "2026-04-25T19:30:00Z"
    assert payload["mode"] == "evening_reflection"
    assert payload["clicks"] == 1
    assert payload["transformations"] == ["slice_rearrange", "pitch_window"]
    assert payload["samples_played"][0]["sample_id"] == "self-quote-1"
    assert payload["samples_used"][0]["sample_id"] == "self-quote-1"

    round_tripped = JournalEntry.from_dict(
        {
            "piece_id": "piece-ccs028",
            "started_at": "2026-04-25T19:30:00Z",
            "mode": "evening_reflection",
            "samples_used": [
                {
                    "sample_id": "self-quote-1",
                    "source": "self",
                    "transposition": -2,
                    "fx_preset": "evening_reflection",
                    "played_at_row": 12,
                }
            ],
            "transformations": ["slice_rearrange", "pitch_window"],
            "arc_payoff": "strong payoff (score=0.72) over 1 sample(s)",
            "clicks": 1,
        }
    )

    assert round_tripped.timestamp == "2026-04-25T19:30:00Z"
    assert round_tripped.mode == "evening_reflection"
    assert round_tripped.clicks == 1
    assert round_tripped.transformations == ["slice_rearrange", "pitch_window"]
    assert [sp.sample_id for sp in round_tripped.samples_played] == ["self-quote-1"]
