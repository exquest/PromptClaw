"""Tests for cast_planner.py -- keep CypherClaw's instrument cast broad."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.cast_planner import (
    CORE_ROLES,
    SAMPLER_METADATA_KEY,
    SUPPORT_ROLES,
    assemble_cast,
    select_cast_ids,
)


def _chars() -> dict[str, dict]:
    return {
        "mel": {"voice": {"role": "melody", "synth": "sw_bowed"}},
        "rhythm": {"voice": {"role": "rhythm", "synth": "sw_tabla_ge"}},
        "harm": {"voice": {"role": "harmony", "synth": "sw_choir"}},
        "color": {"voice": {"role": "color", "synth": "sw_bell"}},
        "texture": {"voice": {"role": "texture", "synth": "sw_grain"}},
        "accent": {"voice": {"role": "accent", "synth": "sw_kotekan"}},
    }


def test_select_cast_keeps_core_roles_and_one_support_role() -> None:
    cast = select_cast_ids(_chars(), [], mood_energy=0.1, max_chars=6)

    assert cast[:3] == ["mel", "rhythm", "harm"]
    assert len(cast) >= 4
    assert cast[3] in {"color", "texture", "accent"}


def test_select_cast_rotates_toward_less_recent_support_roles() -> None:
    cast = select_cast_ids(
        _chars(),
        ["color", "harm", "rhythm", "mel", "texture"],
        mood_energy=0.2,
        max_chars=6,
    )

    assert cast[3] == "accent"


def test_select_cast_respects_max_chars() -> None:
    cast = select_cast_ids(_chars(), [], mood_energy=0.9, max_chars=4)
    assert len(cast) == 4


def test_voice_count_target_overrides_energy() -> None:
    # ArtistMode forces an exact voice count regardless of energy.
    cast = select_cast_ids(_chars(), [], mood_energy=0.95, max_chars=6, voice_count_target=2)
    assert len(cast) == 2


def test_voice_count_target_can_request_three_voice_base() -> None:
    cast = select_cast_ids(_chars(), [], mood_energy=0.5, max_chars=6, voice_count_target=3)
    assert len(cast) == 3


def test_preferred_synths_promotes_signature_voices() -> None:
    # When sw_bowed and sw_choir are preferred, characters carrying those
    # synths should be ranked higher and thus picked first when slots are tight.
    cast = select_cast_ids(
        _chars(),
        [],
        mood_energy=0.5,
        max_chars=4,
        preferred_synths=("sw_bowed", "sw_choir"),
        voice_count_target=4,
    )
    # mel uses sw_bowed, harm uses sw_choir → both must be in cast
    assert "mel" in cast
    assert "harm" in cast


class _StubSample:
    def __init__(self) -> None:
        self.sample_id = "smp-001"
        self.path = "/tmp/samples/contact/abc.wav"
        self.source = "contact"
        self.duration_sec = 3.4


class _StubSelector:
    def __init__(self, sample: object | None) -> None:
        self._sample = sample
        self.calls: list[dict] = []

    def select(self, **kwargs: object) -> object | None:
        self.calls.append(dict(kwargs))
        return self._sample


def _chars_with_sampler() -> dict[str, dict]:
    chars = _chars()
    chars["sampler_voice"] = {"voice": {"role": "texture", "synth": "sw_sampler"}}
    return chars


def test_sampler_in_cast_attaches_sample_metadata() -> None:
    selector = _StubSelector(_StubSample())
    metadata: dict = {}

    cast = select_cast_ids(
        _chars_with_sampler(),
        [],
        mood_energy=0.5,
        max_chars=6,
        preferred_synths=("sw_sampler",),
        voice_count_target=4,
        sample_selector=selector,
        sample_select_kwargs={"arc_phase": "intro", "mode": "solitary"},
        cast_metadata=metadata,
    )

    assert "sampler_voice" in cast
    assert metadata["sampler_sample"] == {
        "id": "smp-001",
        "path": "/tmp/samples/contact/abc.wav",
        "source": "contact",
        "duration_sec": 3.4,
    }
    assert selector.calls == [{"arc_phase": "intro", "mode": "solitary"}]


def test_no_sampler_in_cast_leaves_metadata_untouched() -> None:
    selector = _StubSelector(_StubSample())
    metadata: dict = {"prior": "value"}

    select_cast_ids(
        _chars(),  # no sampler character
        [],
        mood_energy=0.5,
        max_chars=4,
        voice_count_target=4,
        sample_selector=selector,
        cast_metadata=metadata,
    )

    assert metadata == {"prior": "value"}
    assert selector.calls == []


def test_sampler_selector_returning_none_skips_metadata_attach() -> None:
    selector = _StubSelector(None)
    metadata: dict = {}

    select_cast_ids(
        _chars_with_sampler(),
        [],
        mood_energy=0.5,
        max_chars=6,
        preferred_synths=("sw_sampler",),
        voice_count_target=4,
        sample_selector=selector,
        cast_metadata=metadata,
    )

    assert "sampler_sample" not in metadata
    assert selector.calls == [{}]


def test_sampler_in_cast_without_selector_or_metadata_is_noop() -> None:
    cast = select_cast_ids(
        _chars_with_sampler(),
        [],
        mood_energy=0.5,
        max_chars=6,
        preferred_synths=("sw_sampler",),
        voice_count_target=4,
    )
    # Behavior unchanged when caller doesn't opt in to sampler wiring.
    assert "sampler_voice" in cast


class _SeededStubSelector:
    """A stub simulating a SampleSelector that selects deterministically based on a seed."""
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.calls: list[dict] = []

    def select(self, **kwargs: object) -> object | None:
        self.calls.append(dict(kwargs))
        # Simulate deterministic choice dependent on the seed
        sample = _StubSample()
        sample.sample_id = f"smp-{self.seed}"
        return sample


def test_deterministic_selection_given_seeded_selector() -> None:
    """Verify that a seeded selector yields deterministic sample attachment."""
    selector_a = _SeededStubSelector(seed=42)
    metadata_a: dict = {}
    select_cast_ids(
        _chars_with_sampler(),
        [],
        preferred_synths=("sw_sampler",),
        sample_selector=selector_a,
        cast_metadata=metadata_a,
    )

    selector_b = _SeededStubSelector(seed=42)
    metadata_b: dict = {}
    select_cast_ids(
        _chars_with_sampler(),
        [],
        preferred_synths=("sw_sampler",),
        sample_selector=selector_b,
        cast_metadata=metadata_b,
    )

    # Both seeded selectors should attach identical sample data
    assert metadata_a == metadata_b
    assert metadata_a["sampler_sample"]["id"] == "smp-42"


class _CaptureShapedSample:
    def __init__(self) -> None:
        self.sample_id = "cap-001"
        self.path = "/tmp/samples/room/cap.wav"
        self.source = "room"
        self.sample_rate = 48_000
        self.frame_count = 96_000


def test_sampler_summary_derives_duration_from_capture_shape() -> None:
    selector = _StubSelector(_CaptureShapedSample())
    metadata: dict = {}

    select_cast_ids(
        _chars_with_sampler(),
        [],
        mood_energy=0.4,
        max_chars=6,
        preferred_synths=("sw_sampler",),
        voice_count_target=4,
        sample_selector=selector,
        cast_metadata=metadata,
    )

    assert metadata["sampler_sample"] == {
        "id": "cap-001",
        "path": "/tmp/samples/room/cap.wav",
        "source": "room",
        "duration_sec": 2.0,
    }


def test_assemble_cast_plans_piece_with_sampler_metadata() -> None:
    selector = _StubSelector(_StubSample())
    piece = {
        "artist_mode": "evening_reflection",
        "arc_phase": "recap",
        "mood": {"energy": 0.22, "valence": 0.34, "arousal": 0.18},
        "patch_name": "house_monastery",
        "preferred_synths": ("sw_sampler", "sw_bowed"),
        "voice_count_target": 4,
    }

    cast, metadata = assemble_cast(
        _chars_with_sampler(),
        [],
        piece=piece,
        sample_selector=selector,
    )

    sampler_entry = next(entry for entry in cast if entry["id"] == "sampler_voice")
    assert sampler_entry["sample_record"] == metadata["sampler_sample"] == {
        "id": "smp-001",
        "path": "/tmp/samples/contact/abc.wav",
        "source": "contact",
        "duration_sec": 3.4,
    }
    assert selector.calls == [
        {
            "mode": "evening_reflection",
            "arc_phase": "recap",
            "mood": {"energy": 0.22, "valence": 0.34, "arousal": 0.18},
            "target_character": ("house_monastery",),
        }
    ]


class TestCastPlannerEndToEnd:
    """End-to-end checks for the public cast-planner surface."""

    def _full_chars(self) -> dict[str, dict]:
        chars = _chars_with_sampler()
        chars["foundation_voice"] = {
            "voice": {"role": "foundation", "synth": "sw_drone"}
        }
        chars["counter_voice"] = {
            "voice": {"role": "counter_melody", "synth": "sw_recorder"}
        }
        chars["punctuation_voice"] = {
            "voice": {"role": "punctuation", "synth": "sw_woodblock"}
        }
        return chars

    def test_canonical_core_roles_lead_with_support_across_history_table(self) -> None:
        chars = self._full_chars()
        scenarios = [
            ([], 0.1, 4),
            (["mel", "rhythm"], 0.4, 5),
            (["color", "harm", "rhythm", "mel", "texture"], 0.2, 6),
            (["accent", "color", "texture"], 0.6, 6),
        ]

        seen_supports: set[str] = set()
        for history, energy, max_chars in scenarios:
            cast = select_cast_ids(
                chars,
                history,
                mood_energy=energy,
                max_chars=max_chars,
            )
            assert cast[:3] == ["mel", "rhythm", "harm"]
            assert len(cast) >= 4
            assert len(cast) <= max_chars
            assert len(set(cast)) == len(cast)
            support_pick = cast[3]
            support_role = chars[support_pick]["voice"]["role"]
            assert support_role in SUPPORT_ROLES
            seen_supports.add(support_role)
        assert len(seen_supports) >= 2

    def test_voice_count_target_table_clamps_to_max_chars(self) -> None:
        chars = self._full_chars()
        cases = [
            (1, 6, 1),
            (2, 6, 2),
            (3, 6, 3),
            (4, 6, 4),
            (10, 6, 6),
            (5, 4, 4),
        ]

        for target, max_chars, expected in cases:
            cast = select_cast_ids(
                chars,
                [],
                mood_energy=0.95,
                max_chars=max_chars,
                voice_count_target=target,
            )
            assert len(cast) == expected, (target, max_chars, expected, cast)
            assert len(set(cast)) == len(cast)
            for cid in cast[: min(expected, len(CORE_ROLES))]:
                assert chars[cid]["voice"]["role"] == CORE_ROLES[cast.index(cid)]

    def test_preferred_synths_promote_matching_characters_across_palettes(self) -> None:
        chars = self._full_chars()
        palettes = [
            (("sw_bowed", "sw_choir"), {"mel", "harm"}),
            (("sw_sampler", "sw_bell"), {"sampler_voice", "color"}),
            (("sw_drone", "sw_recorder"), {"foundation_voice", "counter_voice"}),
        ]

        for preferred, must_include in palettes:
            cast = select_cast_ids(
                chars,
                [],
                mood_energy=0.5,
                max_chars=6,
                preferred_synths=preferred,
                voice_count_target=5,
            )
            assert len(cast) == 5
            for required in must_include:
                assert required in cast, (preferred, required, cast)

    def test_cast_history_rotation_pushes_recent_characters_to_lower_priority(
        self,
    ) -> None:
        chars = self._full_chars()
        history: list[str] = []
        observed_supports: list[str] = []

        for _ in range(4):
            cast = select_cast_ids(
                chars,
                history,
                mood_energy=0.2,
                max_chars=6,
                voice_count_target=4,
            )
            assert cast[:3] == ["mel", "rhythm", "harm"]
            support_pick = cast[3]
            observed_supports.append(support_pick)
            history.insert(0, support_pick)

        assert len(observed_supports) == 4
        assert len(set(observed_supports)) >= 2

        recent_first = observed_supports[0]
        next_cast = select_cast_ids(
            chars,
            [recent_first] + history,
            mood_energy=0.2,
            max_chars=6,
            voice_count_target=4,
        )
        assert next_cast[3] != recent_first

    def test_assemble_cast_pipeline_propagates_piece_kwargs_and_sampler_metadata(
        self,
    ) -> None:
        chars = self._full_chars()
        pieces = [
            {
                "artist_mode": "evening_reflection",
                "arc_phase": "recap",
                "mood": {"energy": 0.2, "valence": 0.3, "arousal": 0.1},
                "patch_name": "house_monastery",
                "preferred_synths": ("sw_sampler", "sw_bowed"),
                "voice_count_target": 4,
            },
            {
                "mode": "morning_arrival",
                "arc_phase": "intro",
                "mood": {"energy": 0.6, "valence": 0.5, "arousal": 0.4},
                "target_character": "house_garden",
                "preferred_synths": ("sw_sampler",),
                "voice_count_target": 5,
            },
        ]

        for piece in pieces:
            selector = _StubSelector(_StubSample())
            entries, metadata = assemble_cast(
                chars,
                [],
                piece=piece,
                sample_selector=selector,
            )
            expected_size = piece["voice_count_target"]
            assert len(entries) == expected_size
            ids = [entry["id"] for entry in entries]
            assert ids[:3] == ["mel", "rhythm", "harm"]
            assert "sampler_voice" in ids
            sampler_entry = next(e for e in entries if e["id"] == "sampler_voice")
            assert sampler_entry["sample_record"] == metadata[SAMPLER_METADATA_KEY]
            assert metadata[SAMPLER_METADATA_KEY]["id"] == "smp-001"
            assert len(selector.calls) == 1
            call = selector.calls[0]
            assert call["mood"] == piece["mood"]
            mode_value = piece.get("artist_mode") or piece.get("mode")
            assert call["mode"] == mode_value
            assert call["arc_phase"] == piece["arc_phase"]
            target_source = piece.get("target_character") or piece.get("patch_name")
            assert call["target_character"] == (target_source,)

    def test_assembled_cast_entries_are_json_safe_diagnostics(self) -> None:
        chars = self._full_chars()
        selector = _StubSelector(_StubSample())
        piece = {
            "mode": "evening_reflection",
            "arc_phase": "recap",
            "mood": {"energy": 0.4, "valence": 0.5, "arousal": 0.2},
            "patch_name": "house_monastery",
            "preferred_synths": ("sw_sampler",),
            "voice_count_target": 4,
        }

        entries, metadata = assemble_cast(
            chars,
            [],
            piece=piece,
            sample_selector=selector,
        )

        diagnostics: list[dict[str, object]] = []
        for entry in entries:
            payload: dict[str, object] = {
                "id": entry["id"],
                "role": entry.get("role"),
                "synth": entry.get("synth"),
            }
            sample_record = entry.get("sample_record")
            if isinstance(sample_record, dict):
                payload["sample_record"] = dict(sample_record)
            diagnostics.append(payload)

        rendered = json.dumps(
            {
                "entries": diagnostics,
                "sampler_summary": metadata.get(SAMPLER_METADATA_KEY),
            },
            sort_keys=True,
        )
        decoded = json.loads(rendered)
        assert [item["id"] for item in decoded["entries"]] == [
            entry["id"] for entry in entries
        ]
        assert decoded["sampler_summary"] == metadata[SAMPLER_METADATA_KEY]
        for diag in diagnostics:
            if diag["id"] == "sampler_voice":
                assert "sample_record" in diag
            else:
                assert "sample_record" not in diag

    def test_sampler_attachment_handles_selector_results_across_returns(self) -> None:
        chars = self._full_chars()
        sample_payload = _StubSample()
        results: list[object | None] = [sample_payload, None, sample_payload]

        for outcome in results:
            selector = _StubSelector(outcome)
            metadata: dict = {}
            cast = select_cast_ids(
                chars,
                [],
                mood_energy=0.5,
                max_chars=6,
                preferred_synths=("sw_sampler",),
                voice_count_target=4,
                sample_selector=selector,
                sample_select_kwargs={"arc_phase": "intro"},
                cast_metadata=metadata,
            )
            assert "sampler_voice" in cast
            assert selector.calls == [{"arc_phase": "intro"}]
            if outcome is None:
                assert SAMPLER_METADATA_KEY not in metadata
            else:
                assert metadata[SAMPLER_METADATA_KEY]["id"] == "smp-001"
