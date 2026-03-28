"""Tests for the coherence event store."""

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.event_store import SqliteEventStore
from promptclaw.coherence.models import CoherenceEvent


class TestSqliteEventStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-test-"))
        self.db_path = self.temp_dir / "test.db"
        self.store = SqliteEventStore(self.db_path)
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir)

    def test_migrate_creates_table(self):
        self.assertTrue(self.db_path.exists())

    def test_append_and_replay(self):
        event = CoherenceEvent(
            event_id="evt-001",
            run_id="run-1",
            timestamp="2026-01-01T00:00:00Z",
            event_type="run_started",
            phase="routing",
            agent="claude",
            role="lead",
            payload={"message": "test"},
            sequence_number=0,
        )
        self.store.append(event)
        events = self.store.replay("run-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "evt-001")
        self.assertEqual(events[0].event_type, "run_started")
        self.assertEqual(events[0].payload, {"message": "test"})

    def test_replay_ordering(self):
        for i in range(5):
            self.store.append(CoherenceEvent(
                event_id=f"evt-{i}",
                run_id="run-1",
                timestamp=f"2026-01-01T00:00:0{i}Z",
                event_type=f"event_{i}",
                sequence_number=i,
            ))
        events = self.store.replay("run-1")
        self.assertEqual(len(events), 5)
        for i, event in enumerate(events):
            self.assertEqual(event.sequence_number, i)
            self.assertEqual(event.event_type, f"event_{i}")

    def test_run_isolation(self):
        self.store.append(CoherenceEvent(
            event_id="evt-a", run_id="run-a", timestamp="2026-01-01T00:00:00Z",
            event_type="test", sequence_number=0,
        ))
        self.store.append(CoherenceEvent(
            event_id="evt-b", run_id="run-b", timestamp="2026-01-01T00:00:01Z",
            event_type="test", sequence_number=0,
        ))
        self.assertEqual(len(self.store.replay("run-a")), 1)
        self.assertEqual(len(self.store.replay("run-b")), 1)
        self.assertEqual(len(self.store.replay_all()), 2)

    def test_count(self):
        for i in range(3):
            self.store.append(CoherenceEvent(
                event_id=f"evt-{i}", run_id="run-1",
                timestamp=f"2026-01-01T00:00:0{i}Z",
                event_type="test", sequence_number=i,
            ))
        self.assertEqual(self.store.count("run-1"), 3)
        self.assertEqual(self.store.count(), 3)
        self.assertEqual(self.store.count("run-nonexistent"), 0)

    def test_empty_replay(self):
        events = self.store.replay("nonexistent")
        self.assertEqual(events, [])

    def test_payload_roundtrip(self):
        payload = {"key": "value", "nested": {"a": 1}, "list": [1, 2, 3]}
        self.store.append(CoherenceEvent(
            event_id="evt-payload", run_id="run-1",
            timestamp="2026-01-01T00:00:00Z",
            event_type="test", payload=payload, sequence_number=0,
        ))
        events = self.store.replay("run-1")
        self.assertEqual(events[0].payload, payload)


if __name__ == "__main__":
    unittest.main()
