"""Tests for the coherence re-entry digest (the 'Prints' artifact).

Covers the pure formatter (build_reentry_digest) and the engine integration that
auto-writes the digest on finalize. See docs/Shadowland2/promptclaw-integration-proposal.md
(P3 — generated re-entry digest).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.decision_store import Decision
from promptclaw.coherence.models import CoherenceEvent
from promptclaw.coherence.reentry import build_reentry_digest


def _evt(seq, event_type, phase="", agent="", role="", payload=None, run_id="run-1"):
    return CoherenceEvent(
        event_id=f"evt-{seq}",
        run_id=run_id,
        timestamp=f"2026-06-23T00:00:{seq:02d}Z",
        event_type=event_type,
        phase=phase,
        agent=agent,
        role=role,
        payload=payload or {},
        sequence_number=seq,
    )


def _dec(decision_id, title, created_at, decision_text="Do the thing.", file_paths=None,
         status="active", unlocks=None, constrains=None):
    return Decision(
        decision_id=decision_id,
        created_at=created_at,
        title=title,
        context="ctx",
        decision_text=decision_text,
        rationale="because",
        status=status,
        superseded_by=None,
        tags=[],
        file_paths=file_paths or [],
        unlocks=unlocks or [],
        constrains=constrains or [],
    )


class TestBuildReentryDigest(unittest.TestCase):
    # --- Empty / degenerate ---

    def test_empty_inputs_produce_valid_digest(self):
        text = build_reentry_digest([], [], generated_at="2026-06-23T00:00:00Z")
        self.assertIn("# Re-entry Digest", text)
        self.assertIn("No active decisions", text)
        self.assertTrue(text.endswith("\n"))

    # --- Decisions ---

    def test_renders_constrains_and_unlocks(self):
        decs = [_dec("d1", "Big call", "2026-06-22T00:00:00Z",
                     constrains=["keep it pure"], unlocks=["fast resume"])]
        text = build_reentry_digest([], decs, generated_at="2026-06-23T00:00:00Z")
        self.assertIn("keep it pure", text)
        self.assertIn("fast resume", text)

    def test_includes_active_decisions_newest_first(self):
        decs = [
            _dec("d-old", "Older decision", "2026-06-20T00:00:00Z"),
            _dec("d-new", "Newer decision", "2026-06-22T00:00:00Z"),
        ]
        text = build_reentry_digest([], decs, generated_at="2026-06-23T00:00:00Z")
        self.assertIn("Older decision", text)
        self.assertIn("Newer decision", text)
        # newest first
        self.assertLess(text.index("Newer decision"), text.index("Older decision"))

    def test_superseded_decisions_excluded(self):
        decs = [
            _dec("d-active", "Live decision", "2026-06-22T00:00:00Z", status="active"),
            _dec("d-dead", "Retired decision", "2026-06-21T00:00:00Z", status="superseded"),
        ]
        text = build_reentry_digest([], decs, generated_at="2026-06-23T00:00:00Z")
        self.assertIn("Live decision", text)
        self.assertNotIn("Retired decision", text)

    def test_max_decisions_caps_and_notes_remainder(self):
        decs = [
            _dec(f"d-{i}", f"Decision {i:02d}", f"2026-06-{10 + i:02d}T00:00:00Z")
            for i in range(10)
        ]
        text = build_reentry_digest([], decs, generated_at="2026-06-23T00:00:00Z", max_decisions=3)
        self.assertIn("Decision 09", text)  # newest shown
        self.assertNotIn("Decision 00", text)  # oldest not shown
        self.assertIn("+7 more", text)

    # --- Where it ended ---

    def test_where_it_ended_reflects_last_event_and_verdict(self):
        events = [
            _evt(0, "coherence.pre_routing", phase="routing"),
            _evt(1, "coherence.post_verify", phase="verify", agent="codex", payload={"verdict": "PASS"}),
            _evt(2, "coherence.finalize", phase="complete"),
        ]
        text = build_reentry_digest(events, [], generated_at="2026-06-23T00:00:00Z")
        self.assertIn("Where it ended", text)
        self.assertIn("coherence.finalize", text)
        self.assertIn("PASS", text)

    def test_phases_listed_in_order_deduplicated(self):
        events = [
            _evt(0, "coherence.pre_routing", phase="routing"),
            _evt(1, "coherence.pre_lead", phase="lead", agent="claude"),
            _evt(2, "coherence.post_lead", phase="lead", agent="claude"),
            _evt(3, "coherence.pre_verify", phase="verify", agent="codex"),
            _evt(4, "coherence.finalize", phase="complete"),
        ]
        text = build_reentry_digest(events, [], generated_at="2026-06-23T00:00:00Z")
        self.assertIn("routing → lead → verify → complete", text)

    # --- Held tensions (forward-compat hook for P1) ---

    def test_tensions_section_absent_when_empty(self):
        text = build_reentry_digest([], [], generated_at="2026-06-23T00:00:00Z", tensions=[])
        self.assertNotIn("Held tensions", text)

    def test_tensions_section_present_when_provided(self):
        tensions = [{"statement": "Simplicity vs. horizontal scale", "dialectic_state": "open"}]
        text = build_reentry_digest([], [], generated_at="2026-06-23T00:00:00Z", tensions=tensions)
        self.assertIn("Held tensions", text)
        self.assertIn("Simplicity vs. horizontal scale", text)
        self.assertIn("open", text)


class TestEngineReentryIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-reentry-"))
        from promptclaw.coherence.engine import CoherenceEngine
        from promptclaw.coherence.models import CoherenceConfig
        self.engine = CoherenceEngine(CoherenceConfig(), self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_reentry_digest_creates_file(self):
        self.engine.emit("run-x", "coherence.pre_routing", phase="routing")
        path = self.engine.write_reentry_digest()
        self.assertTrue(path.exists())
        self.assertIn("# Re-entry Digest", path.read_text())

    def test_finalize_auto_writes_digest(self):
        self.engine.emit("run-x", "coherence.pre_lead", phase="lead", agent="claude")
        self.engine.finalize("run-x")
        digest_path = self.temp_dir / ".promptclaw" / "reentry.md"
        self.assertTrue(digest_path.exists())
        self.assertIn("run-x", digest_path.read_text())

    def test_digest_reflects_recorded_decision(self):
        self.engine.record_decision(
            title="Adopt held-tension primitive",
            context="ctx",
            decision_text="Add a tensions store.",
            rationale="why",
        )
        self.engine.emit("run-y", "coherence.finalize", phase="complete")
        text = self.engine.build_reentry_digest_text(run_id="run-y")
        self.assertIn("Adopt held-tension primitive", text)

    def test_default_run_id_uses_last_emitted_run(self):
        self.engine.emit("run-a", "coherence.pre_routing", phase="routing")
        self.engine.emit("run-b", "coherence.pre_routing", phase="routing")
        text = self.engine.build_reentry_digest_text()  # no run_id → most recently touched run
        self.assertIn("run-b", text)

    def test_finalize_resilient_if_digest_write_fails(self):
        # finalize must never break because the best-effort digest could not be written —
        # but the failure must leave an observable event, not vanish silently.
        def boom(*args, **kwargs):
            raise OSError("disk full")

        self.engine.write_reentry_digest = boom  # type: ignore[assignment]
        self.engine.emit("run-z", "coherence.pre_routing", phase="routing")
        verdict = self.engine.finalize("run-z")
        self.assertTrue(verdict.approved)
        events = [e.event_type for e in self.engine.replay("run-z")]
        self.assertIn("coherence.reentry_digest_failed", events)


if __name__ == "__main__":
    unittest.main()
