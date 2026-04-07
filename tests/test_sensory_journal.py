"""Tests for sensory_journal.py — sensory event journal for CypherClaw narrative engine."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from sensory_journal import (
    JournalEntry,
    log_event,
    read_recent,
    read_since,
    summarize_period,
    is_novel_event,
)


# === JournalEntry ===


class TestJournalEntry:
    def test_dataclass_fields(self):
        entry = JournalEntry(
            timestamp=1000.0,
            event_type="sound",
            description="loud noise detected",
            sensor_source="contact_mic",
            mood_snapshot={"energy": 0.5},
            metadata={},
        )
        assert entry.timestamp == 1000.0
        assert entry.event_type == "sound"
        assert entry.description == "loud noise detected"
        assert entry.sensor_source == "contact_mic"
        assert entry.mood_snapshot == {"energy": 0.5}
        assert entry.metadata == {}

    def test_mood_snapshot_optional(self):
        entry = JournalEntry(
            timestamp=1000.0,
            event_type="motion",
            description="door opened",
            sensor_source="porch_eye",
            mood_snapshot=None,
            metadata={},
        )
        assert entry.mood_snapshot is None


# === log_event ===


class TestLogEvent:
    def test_creates_journal_file(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        entry = log_event("sound", "a loud bang", "contact_mic", journal_path=path)
        assert Path(path).exists()
        assert isinstance(entry, JournalEntry)

    def test_appends_valid_jsonl(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        log_event("sound", "bang", "mic", journal_path=path)
        log_event("motion", "door", "camera", journal_path=path)

        lines = Path(path).read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "event_type" in data
            assert "timestamp" in data

    def test_returns_journal_entry(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        entry = log_event("sound", "click", "mic", journal_path=path)
        assert entry.event_type == "sound"
        assert entry.description == "click"
        assert entry.sensor_source == "mic"

    def test_sets_timestamp_automatically(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        before = time.time()
        entry = log_event("sound", "beep", "mic", journal_path=path)
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_mood_is_optional(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        entry = log_event("sound", "beep", "mic", journal_path=path)
        assert entry.mood_snapshot is None

    def test_mood_is_stored(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        mood = {"energy": 0.7, "valence": 0.3}
        entry = log_event("sound", "beep", "mic", mood=mood, journal_path=path)
        assert entry.mood_snapshot == mood

        # Also verify it's in the file
        data = json.loads(Path(path).read_text().strip())
        assert data["mood_snapshot"] == mood

    def test_creates_parent_directories(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "journal.jsonl")
        log_event("sound", "test", "mic", journal_path=path)
        assert Path(path).exists()


# === read_recent ===


class TestReadRecent:
    def test_read_empty_file(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        Path(path).write_text("")
        entries = read_recent(count=10, journal_path=path)
        assert entries == []

    def test_read_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.jsonl")
        entries = read_recent(count=10, journal_path=path)
        assert entries == []

    def test_read_returns_last_n(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        for i in range(10):
            log_event("sound", f"event_{i}", "mic", journal_path=path)
        entries = read_recent(count=3, journal_path=path)
        assert len(entries) == 3
        assert entries[-1].description == "event_9"

    def test_read_fewer_than_count(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        log_event("sound", "only_one", "mic", journal_path=path)
        entries = read_recent(count=10, journal_path=path)
        assert len(entries) == 1

    def test_returns_journal_entries(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        log_event("motion", "door", "camera", journal_path=path)
        entries = read_recent(count=5, journal_path=path)
        assert all(isinstance(e, JournalEntry) for e in entries)


# === read_since ===


class TestReadSince:
    def test_read_since_filters_by_timestamp(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        # Write entries with known timestamps
        for i in range(5):
            entry_data = {
                "timestamp": 1000.0 + i,
                "event_type": "sound",
                "description": f"event_{i}",
                "sensor_source": "mic",
                "mood_snapshot": None,
                "metadata": {},
            }
            with open(path, "a") as f:
                f.write(json.dumps(entry_data) + "\n")

        entries = read_since(since_timestamp=1003.0, journal_path=path)
        assert len(entries) == 2
        assert entries[0].description == "event_3"
        assert entries[1].description == "event_4"

    def test_read_since_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.jsonl")
        entries = read_since(since_timestamp=0.0, journal_path=path)
        assert entries == []

    def test_read_since_no_matches(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        entry_data = {
            "timestamp": 1000.0,
            "event_type": "sound",
            "description": "old",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry_data) + "\n")
        entries = read_since(since_timestamp=2000.0, journal_path=path)
        assert entries == []


# === summarize_period ===


class TestSummarizePeriod:
    def test_summarize_empty(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        Path(path).write_text("")
        summary = summarize_period(hours=24.0, journal_path=path)
        assert summary["total_events"] == 0

    def test_summarize_counts_by_type(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        for event_type, count in [("sound", 3), ("motion", 2), ("touch", 1)]:
            for i in range(count):
                entry_data = {
                    "timestamp": now - 60 + i,
                    "event_type": event_type,
                    "description": f"{event_type}_{i}",
                    "sensor_source": "mic",
                    "mood_snapshot": None,
                    "metadata": {},
                }
                with open(path, "a") as f:
                    f.write(json.dumps(entry_data) + "\n")

        summary = summarize_period(hours=1.0, journal_path=path)
        assert summary["total_events"] == 6
        assert summary["events_by_type"]["sound"] == 3
        assert summary["events_by_type"]["motion"] == 2
        assert summary["events_by_type"]["touch"] == 1

    def test_summarize_most_common_sensor(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        for sensor in ["mic", "mic", "mic", "camera", "camera"]:
            entry_data = {
                "timestamp": now - 30,
                "event_type": "sound",
                "description": "beep",
                "sensor_source": sensor,
                "mood_snapshot": None,
                "metadata": {},
            }
            with open(path, "a") as f:
                f.write(json.dumps(entry_data) + "\n")

        summary = summarize_period(hours=1.0, journal_path=path)
        assert "sensors_by_count" in summary
        assert summary["sensors_by_count"]["mic"] == 3

    def test_summarize_returns_expected_keys(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        Path(path).write_text("")
        summary = summarize_period(hours=24.0, journal_path=path)
        assert "total_events" in summary
        assert "events_by_type" in summary
        assert "sensors_by_count" in summary

    def test_summarize_excludes_old_events(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        # Old event
        old = {
            "timestamp": now - 7200,  # 2 hours ago
            "event_type": "sound",
            "description": "old",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        # Recent event
        recent = {
            "timestamp": now - 60,
            "event_type": "motion",
            "description": "new",
            "sensor_source": "camera",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(old) + "\n")
            f.write(json.dumps(recent) + "\n")

        summary = summarize_period(hours=1.0, journal_path=path)
        assert summary["total_events"] == 1
        assert summary["events_by_type"].get("sound", 0) == 0
        assert summary["events_by_type"]["motion"] == 1


# === is_novel_event ===


class TestIsNovelEvent:
    def test_novel_on_empty_journal(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        Path(path).write_text("")
        assert is_novel_event("sound", "big bang", journal_path=path) is True

    def test_novel_on_missing_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.jsonl")
        assert is_novel_event("sound", "boom", journal_path=path) is True

    def test_not_novel_if_same_event_recent(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        entry_data = {
            "timestamp": now - 30,  # 30 seconds ago
            "event_type": "sound",
            "description": "loud bang",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry_data) + "\n")

        assert is_novel_event("sound", "loud bang", lookback_hours=1.0, journal_path=path) is False

    def test_novel_if_same_event_old(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        entry_data = {
            "timestamp": now - 7200,  # 2 hours ago
            "event_type": "sound",
            "description": "loud bang",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry_data) + "\n")

        assert is_novel_event("sound", "loud bang", lookback_hours=1.0, journal_path=path) is True

    def test_novel_if_different_type(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        entry_data = {
            "timestamp": now - 30,
            "event_type": "motion",
            "description": "loud bang",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry_data) + "\n")

        # Different event type => novel
        assert is_novel_event("sound", "loud bang", lookback_hours=1.0, journal_path=path) is True

    def test_novel_if_different_description(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        now = time.time()
        entry_data = {
            "timestamp": now - 30,
            "event_type": "sound",
            "description": "soft click",
            "sensor_source": "mic",
            "mood_snapshot": None,
            "metadata": {},
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry_data) + "\n")

        # Different description => novel
        assert is_novel_event("sound", "loud bang", lookback_hours=1.0, journal_path=path) is True
