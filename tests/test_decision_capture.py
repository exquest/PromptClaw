"""Tests for decision auto-capture: the fenced ```decision block parser and the engine
wiring that records declared decisions during post_lead.

See docs/Shadowland2/promptclaw-integration-proposal.md (P2 — auto-capture decisions).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.decision_capture import parse_decision_blocks


class TestParseDecisionBlocks(unittest.TestCase):
    def test_no_fence_returns_empty(self):
        self.assertEqual(parse_decision_blocks("just some prose, Decision: nope"), [])

    def test_ignores_non_decision_fences(self):
        text = "```python\nprint('decision: not really')\n```"
        self.assertEqual(parse_decision_blocks(text), [])

    def test_full_block_parsed(self):
        text = (
            "Here is my plan.\n\n"
            "```decision\n"
            "title: Use Redis vector sets instead of ChromaDB\n"
            "what: Store embeddings in Redis vector sets.\n"
            "context: We need sub-ms similarity search.\n"
            "rationale: Already running Redis; one fewer dependency.\n"
            "unlocks: semantic decision search; retrieval cache\n"
            "constrains: must keep Redis >= 7.2; embeddings stay <= 1536d\n"
            "files: src/store.py, src/config.py\n"
            "tags: storage, embeddings\n"
            "```\n"
        )
        blocks = parse_decision_blocks(text)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["title"], "Use Redis vector sets instead of ChromaDB")
        self.assertEqual(b["decision_text"], "Store embeddings in Redis vector sets.")
        self.assertEqual(b["context"], "We need sub-ms similarity search.")
        self.assertEqual(b["rationale"], "Already running Redis; one fewer dependency.")
        self.assertEqual(b["unlocks"], ["semantic decision search", "retrieval cache"])
        self.assertEqual(b["constrains"], ["must keep Redis >= 7.2", "embeddings stay <= 1536d"])
        self.assertEqual(b["file_paths"], ["src/store.py", "src/config.py"])
        self.assertEqual(b["tags"], ["storage", "embeddings"])

    def test_minimal_block_defaults(self):
        text = "```decision\ntitle: Adopt held-tension primitive\n```"
        blocks = parse_decision_blocks(text)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["title"], "Adopt held-tension primitive")
        # decision_text defaults to the title when not given
        self.assertEqual(b["decision_text"], "Adopt held-tension primitive")
        self.assertEqual(b["context"], "")
        self.assertEqual(b["rationale"], "")
        self.assertEqual(b["unlocks"], [])
        self.assertEqual(b["constrains"], [])

    def test_block_without_title_is_skipped(self):
        text = "```decision\nwhat: no title here\nrationale: whatever\n```"
        self.assertEqual(parse_decision_blocks(text), [])

    def test_multiple_blocks(self):
        text = (
            "```decision\ntitle: First\n```\n"
            "noise\n"
            "```decision\ntitle: Second\nwhat: do second thing\n```\n"
        )
        blocks = parse_decision_blocks(text)
        self.assertEqual([b["title"] for b in blocks], ["First", "Second"])

    def test_keys_case_insensitive_and_trimmed(self):
        text = "```decision\nTITLE:   Spaced Title  \nWHY:  because reasons \n```"
        b = parse_decision_blocks(text)[0]
        self.assertEqual(b["title"], "Spaced Title")
        self.assertEqual(b["context"], "because reasons")

    def test_constrains_phrase_with_comma_kept_intact(self):
        # unlocks/constrains split on ';' (not ','), so a phrase containing a comma
        # stays a single item rather than fragmenting into bogus rules.
        text = "```decision\ntitle: T\nconstrains: never write to disk, even on retry\n```"
        b = parse_decision_blocks(text)[0]
        self.assertEqual(b["constrains"], ["never write to disk, even on retry"])

    def test_list_fields_accumulate_across_repeated_lines(self):
        text = (
            "```decision\n"
            "title: T\n"
            "constrains: must keep Redis >= 7.2\n"
            "constrains: embeddings stay <= 1536d\n"
            "files: a.py\n"
            "files: b.py, c.py\n"
            "```"
        )
        b = parse_decision_blocks(text)[0]
        self.assertEqual(b["constrains"], ["must keep Redis >= 7.2", "embeddings stay <= 1536d"])
        # files still comma-split (tokens, not phrases) and accumulate
        self.assertEqual(b["file_paths"], ["a.py", "b.py", "c.py"])

    def test_inline_backticks_do_not_truncate_block(self):
        # An inline ``` inside a field value must not close the fence early; fields
        # after it (constrains) must still be captured.
        text = (
            "```decision\n"
            "title: Use fenced output\n"
            "rationale: prefer the ```json``` form inline\n"
            "constrains: output must stay valid JSON\n"
            "```"
        )
        b = parse_decision_blocks(text)[0]
        self.assertEqual(b["constrains"], ["output must stay valid JSON"])


class TestEngineAutoCapture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-capture-"))
        from promptclaw.coherence.engine import CoherenceEngine
        from promptclaw.coherence.models import CoherenceConfig
        self.engine = CoherenceEngine(CoherenceConfig(), self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_post_lead_captures_declared_decision(self):
        output = (
            "Implemented the cache.\n\n"
            "```decision\n"
            "title: Use Redis for the cache\n"
            "what: Redis as primary cache.\n"
            "rationale: sub-ms latency.\n"
            "constrains: TTL must be set on every key\n"
            "```\n"
        )
        self.engine.post_lead("run-1", "claude", output)
        active = self.engine.decision_store.list_active()
        titles = [d.title for d in active]
        self.assertIn("Use Redis for the cache", titles)
        d = next(d for d in active if d.title == "Use Redis for the cache")
        self.assertEqual(d.constrains, ["TTL must be set on every key"])

    def test_post_lead_without_block_records_nothing(self):
        self.engine.post_lead("run-1", "claude", "Just did the work, no decisions.")
        self.assertEqual(self.engine.decision_store.list_active(), [])

    def test_duplicate_title_not_recorded_twice(self):
        output = "```decision\ntitle: Single decision\nwhat: once\n```"
        self.engine.post_lead("run-1", "claude", output)
        self.engine.post_lead("run-1", "claude", output)  # retry / re-emit
        active = [d for d in self.engine.decision_store.list_active() if d.title == "Single decision"]
        self.assertEqual(len(active), 1)

    def test_duplicate_title_dedup_is_case_and_whitespace_insensitive(self):
        self.engine.post_lead("run-1", "claude", "```decision\ntitle: Use Redis\n```")
        self.engine.post_lead("run-1", "claude", "```decision\ntitle:  use   redis \n```")
        active = self.engine.decision_store.list_active()
        self.assertEqual(len(active), 1)

    def test_no_decision_block_skips_active_query(self):
        # The hot path must not query/deserialize the decision store when there is no block.
        calls = []
        original = self.engine.decision_store.list_active

        def counting():
            calls.append(1)
            return original()

        self.engine.decision_store.list_active = counting  # type: ignore[assignment]
        self.engine.post_lead("run-1", "claude", "no decisions here")
        self.assertEqual(calls, [], "list_active must not be queried when output has no decision block")

    def test_capture_failure_emits_event_and_does_not_break_post_lead(self):
        # A malformed capture must never break the verdict, and must leave an observable trace.
        import promptclaw.coherence.engine as eng_mod

        original = eng_mod.parse_decision_blocks
        eng_mod.parse_decision_blocks = lambda *_a, **_k: (_ for _ in ()).throw(ValueError("boom"))
        try:
            verdict = self.engine.post_lead("run-1", "claude", "```decision\ntitle: x\n```")
            self.assertTrue(verdict.approved)
            events = [e.event_type for e in self.engine.replay("run-1")]
            self.assertIn("coherence.decision_capture_failed", events)
        finally:
            eng_mod.parse_decision_blocks = original


if __name__ == "__main__":
    unittest.main()
